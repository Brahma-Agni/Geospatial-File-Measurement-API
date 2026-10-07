import stat
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from app.exceptions import AppError


def _safe_member(info: ZipInfo) -> bool:
    path = PurePosixPath(info.filename.replace("\\", "/"))
    mode = info.external_attr >> 16
    return (
        bool(path.parts)
        and not path.is_absolute()
        and ".." not in path.parts
        and not stat.S_ISLNK(mode)
    )


def extract_shapefile(
    archive: Path, destination: Path, max_entries: int, max_extracted_bytes: int
) -> Path:
    try:
        with ZipFile(archive) as zipped:
            entries = [entry for entry in zipped.infolist() if not entry.is_dir()]
            if len(entries) > max_entries:
                raise AppError(
                    "INVALID_ARCHIVE",
                    "The archive contains too many files.",
                    details={"maximum_entries": max_entries},
                )
            if any(not _safe_member(entry) for entry in entries):
                raise AppError("INVALID_ARCHIVE", "The archive contains an unsafe path.")
            if sum(entry.file_size for entry in entries) > max_extracted_bytes:
                raise AppError(
                    "INVALID_ARCHIVE",
                    "The extracted archive is too large.",
                    details={"maximum_bytes": max_extracted_bytes},
                )

            for entry in entries:
                target = destination.joinpath(
                    *PurePosixPath(entry.filename.replace("\\", "/")).parts
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(entry) as source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
    except BadZipFile as exc:
        raise AppError("INVALID_ARCHIVE", "The uploaded ZIP is malformed.") from exc

    shapefiles = list(destination.rglob("*.[sS][hH][pP]"))
    if len(shapefiles) != 1:
        raise AppError(
            "INVALID_SHAPEFILE",
            "The ZIP must contain exactly one primary Shapefile.",
            details={"shapefile_count": len(shapefiles)},
        )
    shape = shapefiles[0]
    siblings = {
        path.suffix.lower()
        for path in shape.parent.iterdir()
        if path.stem.lower() == shape.stem.lower()
    }
    missing = sorted({".shp", ".shx", ".dbf"} - siblings)
    if missing:
        raise AppError(
            "INVALID_SHAPEFILE",
            "The uploaded ZIP does not contain a valid Shapefile.",
            details={"missing": missing},
        )
    return shape
