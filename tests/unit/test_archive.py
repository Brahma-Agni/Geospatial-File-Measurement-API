import zipfile
from pathlib import Path
from zipfile import ZipInfo

import pytest

from app.exceptions import AppError
from app.utils.archive import extract_shapefile


def make_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def test_malformed_zip(tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(b"not zip")
    with pytest.raises(AppError, match="malformed"):
        extract_shapefile(archive, tmp_path / "out", 10, 1000)


def test_zip_slip_is_rejected(tmp_path):
    archive = make_zip(tmp_path / "bad.zip", {"../escape.shp": b"x"})
    with pytest.raises(AppError, match="unsafe"):
        extract_shapefile(archive, tmp_path / "out", 10, 1000)


@pytest.mark.parametrize("name", ["/absolute/file.shp", "..\\escape.shp", "a/../../escape.shp"])
def test_absolute_and_cross_platform_traversal_paths_are_rejected(tmp_path, name):
    archive = make_zip(tmp_path / "bad.zip", {name: b"x"})
    with pytest.raises(AppError, match="unsafe"):
        extract_shapefile(archive, tmp_path / "out", 10, 1000)


def test_symbolic_link_entry_is_rejected(tmp_path):
    archive = tmp_path / "symlink.zip"
    entry = ZipInfo("survey.shp")
    entry.create_system = 3
    entry.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(entry, "target")
    with pytest.raises(AppError, match="unsafe"):
        extract_shapefile(archive, tmp_path / "out", 10, 1000)


def test_archive_entry_limit(tmp_path):
    archive = make_zip(tmp_path / "many.zip", {f"file-{index}.txt": b"x" for index in range(3)})
    with pytest.raises(AppError) as error:
        extract_shapefile(archive, tmp_path / "out", 2, 1000)
    assert error.value.code == "INVALID_ARCHIVE"
    assert error.value.details == {"maximum_entries": 2}


def test_extracted_size_limit(tmp_path):
    archive = make_zip(tmp_path / "large.zip", {"large.txt": b"x" * 11})
    with pytest.raises(AppError) as error:
        extract_shapefile(archive, tmp_path / "out", 10, 10)
    assert error.value.code == "INVALID_ARCHIVE"
    assert error.value.details == {"maximum_bytes": 10}


def test_multiple_primary_shapefiles_are_rejected(tmp_path):
    files = {
        f"{stem}.{suffix}": b"x" for stem in ("first", "second") for suffix in ("shp", "shx", "dbf")
    }
    archive = make_zip(tmp_path / "multiple.zip", files)
    with pytest.raises(AppError) as error:
        extract_shapefile(archive, tmp_path / "out", 10, 1000)
    assert error.value.code == "INVALID_SHAPEFILE"
    assert error.value.details == {"shapefile_count": 2}


def test_valid_nested_shapefile_components_are_located(tmp_path):
    files = {f"nested/SURVEY.{suffix}": b"x" for suffix in ("SHP", "SHX", "DBF")}
    archive = make_zip(tmp_path / "valid.zip", files)
    shape = extract_shapefile(archive, tmp_path / "out", 10, 1000)
    assert shape.relative_to(tmp_path / "out").as_posix() == "nested/SURVEY.SHP"


@pytest.mark.parametrize(
    ("files", "missing"),
    [
        ({"file.dbf": b"x", "file.shx": b"x"}, None),
        ({"file.shp": b"x", "file.dbf": b"x"}, ".shx"),
        ({"file.shp": b"x", "file.shx": b"x"}, ".dbf"),
    ],
)
def test_missing_shapefile_components(tmp_path, files, missing):
    archive = make_zip(tmp_path / "bad.zip", files)
    with pytest.raises(AppError) as error:
        extract_shapefile(archive, tmp_path / "out", 10, 1000)
    assert error.value.code == "INVALID_SHAPEFILE"
    if missing:
        assert missing in error.value.details["missing"]
