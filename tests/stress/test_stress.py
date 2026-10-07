from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.conftest import upload


def large_point_kml(count: int) -> bytes:
    placemarks = "".join(
        f"<Placemark><name>P{index}</name><Point><coordinates>"
        f"{77 + index / 1_000_000},{12 + index / 1_000_000},0"
        "</coordinates></Point></Placemark>"
        for index in range(count)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"{placemarks}</Document></kml>"
    ).encode()


@pytest.mark.stress
def test_large_dataset_upload_and_full_pagination(client, tmp_path):
    path = tmp_path / "large.kml"
    path.write_bytes(large_point_kml(2_000))
    response = upload(client, path)
    assert response.status_code == 201, response.text
    assert response.json()["feature_count"] == 2_000

    file_id = response.json()["id"]
    pages = [
        client.get(f"/api/files/{file_id}/features/?limit=500&offset={offset}").json()
        for offset in range(0, 2_000, 500)
    ]
    assert sum(len(page["features"]) for page in pages) == 2_000
    assert [feature["feature_index"] for page in pages for feature in page["features"]] == list(
        range(2_000)
    )


@pytest.mark.stress
def test_concurrent_read_burst(client, kml_file):
    file_id = upload(client, kml_file).json()["id"]
    urls = [
        f"/api/files/{file_id}/{suffix}"
        for _ in range(40)
        for suffix in ("", "features/", "measurements/")
    ]
    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(client.get, urls))
    assert len(responses) == 120
    assert {response.status_code for response in responses} == {200}
