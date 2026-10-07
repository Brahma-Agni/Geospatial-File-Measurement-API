# Architecture and Processing Design

## Purpose and scope

The service converts supported vector files into a common persisted representation and calculates measurements without modifying the original geometries. V1 is intentionally one FastAPI application and one Vercel Function with synchronous processing.

## Why the architecture is lean

Production concerns are preserved, but each layer must own a real boundary. Routes own HTTP, the processing service owns the lifecycle and transaction boundaries, pure geospatial functions own CRS and geometry behavior, and SQLAlchemy owns persistence. There is no repository wrapper because the queries are short and have only one persistence implementation. There are no one-implementation interfaces or service classes around stateless functions.

The fastest way to learn the flow is:

1. Start at `app/api/files.py` to see the public contract.
2. Follow upload handling into `app/services/file_service.py`.
3. Read `geospatial_reader.py`, `crs_service.py`, `feature_service.py`, and `measurement_service.py` in processing order.
4. Read `models/` to see what crosses the persistence boundary.
5. Finish with `exceptions/handlers.py` and `utils/archive.py` for failure and trust-boundary behavior.

## Component responsibilities

| Component | Location | Responsibility |
|---|---|---|
| Application entry point | `app/main.py` | Logging, startup directories, table initialization, routes, health check |
| Configuration | `app/config.py` | Validated environment settings and byte-limit conversion |
| Database | `app/database.py` | SQLAlchemy engine, session factory, dependency, schema creation |
| HTTP API | `app/api/files.py` | Multipart input, UUID validation, pagination, public response composition |
| Public schemas | `app/schemas/` | Pydantic response contracts independent of ORM/GeoPandas |
| File orchestration | `app/services/file_service.py` | Storage, lifecycle transitions, processing transaction boundaries, logging |
| Format reading | `app/services/geospatial_reader.py` | KML/Shapefile dispatch, read errors, empty dataset and CRS validation |
| Shapefile handling | `app/services/shapefile_service.py` | Temporary extraction and Pyogrio-backed loading |
| CRS selection | `app/services/crs_service.py` | Metric CRS selection and transformation |
| Feature normalization | `app/services/feature_service.py` | Source serialization, attributes, identifiers, measurement records |
| Measurement | `app/services/measurement_service.py` | Geometry-type rules and per-feature outcomes |
| Archive validation | `app/utils/archive.py` | ZIP safety limits, path checks, extraction, component discovery |
| JSON conversion | `app/utils/geometry.py` | GeoJSON mapping and JSON-safe property values |
| Domain errors | `app/exceptions/` | Stable codes and sanitized HTTP responses |

## Processing sequence

```text
1. Validate extension (.kml or .zip)
2. Allocate UUID and application-owned destination
3. Stream upload in 1 MiB chunks while enforcing the byte limit
4. Persist upload metadata with status UPLOADED
5. Transition to PROCESSING
6. Validate/extract ZIP when the input is a Shapefile archive
7. Read the dataset into a source GeoDataFrame
8. Reject an empty dataset or missing CRS
9. Choose a metric measurement CRS
10. Transform a separate measurement GeoDataFrame
11. Normalize and measure each feature
12. Persist all feature records
13. Set CRS fields, count, and COMPLETED status
```

An expected domain failure at steps 6–12 rolls back the active transaction, stores `FAILED` and a safe processing message, logs the file UUID and error code, and returns a structured error. An unexpected exception follows the same lifecycle but returns a generic `PROCESSING_FAILED` response.

## File lifecycle

| Status | Meaning |
|---|---|
| `UPLOADED` | Accepted bytes and metadata have been persisted |
| `PROCESSING` | Format reading, CRS work, normalization, or measurement is active |
| `COMPLETED` | Dataset-level processing completed and features were persisted |
| `FAILED` | A file-level condition prevented completion |

Unsupported or invalid individual geometries are feature results, not file-level failures. This preserves useful siblings in a mixed-quality dataset.

## Persistence model

### `uploaded_files`

| Field | Purpose |
|---|---|
| `id` | UUID primary key exposed by the API |
| `filename` | Generated UUID storage filename |
| `original_filename` | Sanitized client basename exposed as `filename` in API responses |
| `file_type` | `KML` or `SHAPEFILE` |
| `upload_size` | Accepted byte count |
| `source_crs` | Source CRS string after successful reading |
| `measurement_crs` | Projected metric CRS used for calculations |
| `feature_count` | Number of normalized records |
| `status` | Lifecycle enum |
| `processing_error` | Safe file-level failure description |
| `created_at`, `updated_at` | UTC lifecycle timestamps |

### `features`

Each feature belongs to one upload. `(uploaded_file_id, feature_index)` is unique. The record preserves a source identifier when available, original geometry as GeoJSON, JSON-safe source properties, source CRS, and the complete measurement result.

The original geometry is JSON because V1 only retrieves it by upload and does not execute spatial database queries. A PostGIS migration should replace or supplement this column with a spatial type and index.

## CRS and measurement design

Planar Shapely area and length use the coordinate units of the geometry. Calculating them on EPSG:4326 would return square degrees or degrees, not metres.

The CRS algorithm is:

1. Parse the source CRS with PyProj.
2. If it is projected and both horizontal axes use metres with a conversion factor of 1, reuse it.
3. Otherwise call `GeoDataFrame.estimate_utm_crs()` using the dataset extent.
4. Require the selected CRS to be projected and metric.
5. Transform a copy with `to_crs()`.
6. Measure the projected copy while serializing the unchanged source geometry.

One UTM CRS for the dataset is practical for local and regional inputs. It becomes less accurate for datasets spanning multiple zones or very large extents and may not be available for polar or invalid bounds. Future geodesic or per-feature projection strategies can be implemented in `crs_service` without changing HTTP or persistence contracts.

## Measurement outcomes

`measurement_service.measure()` has no database or HTTP dependency. It returns a typed value containing measurement type, value, unit, status, and optional message.

- Polygon families return area in `m2`.
- Line families return length in `m`.
- Point families return no measurement and `SKIPPED`.
- Null and empty geometry return `SKIPPED` with context.
- Invalid geometry returns `FAILED`; V1 does not repair it.
- Other geometry types return `UNSUPPORTED`.

## Transaction and failure boundaries

Upload bytes are written before processing begins. Feature inserts are committed as one batch. A processing exception rolls the database session back before the current upload is marked failed. Public errors contain no exception traceback, SQL statement, or storage path; full exception context is restricted to server logs.

On Vercel, upload bytes live only in `/tmp` during the request and are removed in a `finally` block after success or failure. PostgreSQL stores normalized durable results. Local and Docker execution can retain source files by leaving cleanup disabled.

## Extension points

- Add formats in `geospatial_reader` while returning a GeoDataFrame with an established CRS.
- Add measurement strategies in `measurement_service` and extend enums/schemas deliberately.
- Replace synchronous execution by invoking `FileService.process()` from a worker after the initial metadata commit.
- Add PostGIS behind the SQLAlchemy boundary and migrations without exposing ORM geometry objects through schemas.
- Add geometry repair as an explicit pre-measurement policy; never mutate source geometry silently.
