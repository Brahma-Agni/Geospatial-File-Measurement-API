# API Reference

## Conventions

- Base URL in local development: `http://localhost:8000`
- JSON is used for responses; uploads use `multipart/form-data`.
- File identifiers are UUIDs.
- Timestamps are UTC ISO 8601 values.
- Unknown response fields should be ignored by clients for forward compatibility.

Interactive documentation is available at `/docs` and `/redoc` while the service is running.

## Health check

### `GET /health`

Returns `200 OK` when the application can serve requests.

```json
{"status": "ok"}
```

This is a process liveness endpoint. It does not perform deep database, filesystem, or GDAL dependency checks.

## Upload and process

### `POST /api/files/`

Send exactly one multipart field named `file`. The filename extension, case-insensitively, must be `.kml` or `.zip`; ZIP is interpreted as a Shapefile archive.

```bash
curl --fail-with-body -F 'file=@survey.kml' http://localhost:8000/api/files/
```

The endpoint returns only after synchronous processing succeeds. Success is `201 Created` with:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Stable upload identifier |
| `filename` | string | Original client basename, never a client path |
| `file_type` | enum | `KML` or `SHAPEFILE` |
| `upload_size` | integer | Stored input bytes |
| `feature_count` | integer | Normalized feature count |
| `source_crs` | string | Source CRS |
| `measurement_crs` | string | Metric CRS used for measurement |
| `status` | enum | Normally `COMPLETED` for a successful synchronous response |
| `created_at` | datetime | UTC creation time |
| `updated_at` | datetime | UTC last update time |
| `processing_error` | string | Present only when appropriate |

## File metadata

### `GET /api/files/{id}/`

Returns the same metadata representation for a persisted upload. An unknown UUID returns `FILE_NOT_FOUND`; a malformed identifier returns `VALIDATION_ERROR`.

## Original features

### `GET /api/files/{id}/features/`

Query parameters:

| Parameter | Default | Constraint | Meaning |
|---|---:|---|---|
| `limit` | configured default, initially 100 | integer ≥ 1, capped at configured maximum | Page size |
| `offset` | 0 | integer ≥ 0 | Number of records to skip |

Response:

```json
{
  "file_id": "2f2a86a1-84ca-48f9-b7bb-df0650da6e79",
  "feature_count": 1,
  "limit": 100,
  "offset": 0,
  "features": [
    {
      "feature_index": 0,
      "source_feature_id": "0",
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[77.0, 12.0], [77.001, 12.0], [77.001, 12.001], [77.0, 12.0]]]
      },
      "properties": {"name": "Plot A"},
      "source_crs": "EPSG:4326"
    }
  ]
}
```

Geometry is the original source geometry serialized as GeoJSON. It is not the projected measurement copy.

## Measurements

### `GET /api/files/{id}/measurements/`

Pagination matches the feature endpoint. Each entry repeats the feature index, geometry type, and properties so measurement consumers do not need a join request.

```json
{
  "file_id": "2f2a86a1-84ca-48f9-b7bb-df0650da6e79",
  "source_crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "feature_count": 2,
  "limit": 100,
  "offset": 0,
  "features": [
    {
      "feature_index": 0,
      "geometry_type": "Polygon",
      "properties": {"name": "Plot A"},
      "measurement": {
        "type": "AREA",
        "value": 12012.4,
        "unit": "m2",
        "status": "SUCCESS",
        "message": null
      }
    },
    {
      "feature_index": 1,
      "geometry_type": "Point",
      "properties": {"name": "Marker"},
      "measurement": null
    }
  ]
}
```

Point and MultiPoint entries use `measurement: null`. Unsupported, invalid, null, and empty geometries return a measurement object when a status or explanatory message must be conveyed.

## Error envelope

```json
{
  "error": {
    "code": "INVALID_SHAPEFILE",
    "message": "The uploaded ZIP does not contain a valid Shapefile.",
    "details": {"missing": [".shx", ".dbf"]}
  }
}
```

`details` is optional. Validation details contain only location, message, and type; submitted values are not echoed.

## Error catalog

| Code | Typical HTTP status | Meaning |
|---|---:|---|
| `UNSUPPORTED_FILE_TYPE` | 415 | Filename extension is not supported |
| `FILE_TOO_LARGE` | 413 | Upload byte limit was exceeded |
| `INVALID_ARCHIVE` | 422 | ZIP is malformed, unsafe, or exceeds archive limits |
| `INVALID_SHAPEFILE` | 422 | Shapefile structure or data is invalid |
| `INVALID_KML` | 422 | KML could not be read |
| `MISSING_CRS` | 422 | Source or suitable measurement CRS is unavailable |
| `CORRUPT_FILE` | 422 | Coordinates could not be transformed safely |
| `EMPTY_DATASET` | 422 | Reader returned no features |
| `INVALID_GEOMETRY` | 422 | Reserved domain code for invalid geometry operations |
| `PROCESSING_FAILED` | 422 or 500 | Results are unavailable or an unexpected failure occurred |
| `FILE_NOT_FOUND` | 404 | UUID has no persisted upload |
| `VALIDATION_ERROR` | 422 | Path, query, form, or schema validation failed |

## HTTP behavior notes

- MIME type is advisory; accepted formats are selected by filename extension and then parsed by GDAL/Pyogrio.
- An excessive requested `limit` is capped, not rejected.
- An offset beyond the result count returns an empty `features` array.
- Results are ordered by `feature_index`.
- Numeric measurement values are stored and returned as floating-point values without display rounding.
