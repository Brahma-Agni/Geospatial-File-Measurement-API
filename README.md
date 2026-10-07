# Geospatial File Measurement API

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![Vercel](https://img.shields.io/badge/deploy-Vercel-black)](docs/vercel.md)
[![Tests](https://img.shields.io/badge/tests-61%20passing-brightgreen)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)](#testing)

A production-oriented FastAPI backend for uploading KML files and ZIP archives containing an ESRI Shapefile, preserving their original features, and calculating CRS-safe metric measurements.

The service processes small-to-medium files synchronously, persists file and feature results, and exposes them through a documented REST API.

## Contents

- [Capabilities](#capabilities)
- [Quick start](#quick-start)
- [Deploy to Vercel](#deploy-to-vercel)
- [Using the API](#using-the-api)
- [Measurement behavior](#measurement-behavior)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Testing](#testing)
- [Security](#security)
- [Known limitations](#known-limitations)
- [Documentation](#documentation)

## Capabilities

- accepts `.kml` and `.zip` uploads through multipart form data;
- validates ZIP structure, entry count, extracted size, paths, and required Shapefile components;
- reads vector data with GeoPandas and Pyogrio/GDAL;
- rejects datasets without a known CRS instead of guessing one;
- projects geographic and non-metric data before calculating area or length;
- preserves original source geometry, attributes, and CRS for API output;
- measures Polygon, MultiPolygon, LineString, and MultiLineString features;
- handles point, invalid, empty, null, and unsupported geometries per feature;
- persists upload state and normalized features with SQLAlchemy;
- provides paginated feature and measurement endpoints;
- returns stable, structured API errors without exposing server internals;
- includes unit, integration, regression, security, and bounded stress tests;
- runs locally or as a non-root Docker container.

### Deliberate V1 boundaries

The service does not include authentication, background workers, durable source-file storage, geometry repair, multiple Shapefiles per archive, or spatial database queries. See [Known limitations](#known-limitations) for the complete rationale.

## Quick start

### Requirements

- Python 3.12 or newer
- `pip` or another PEP 517-compatible package installer
- Docker with Compose, if using the container workflow

Pyogrio wheels include the GDAL runtime on supported platforms. A platform without a compatible wheel may require system GDAL packages.

### Native Python

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload
```

The service starts at `http://127.0.0.1:8000`.

| Resource | URL |
|---|---|
| Health check | `http://127.0.0.1:8000/health` |
| Swagger UI | `http://127.0.0.1:8000/docs` |
| ReDoc | `http://127.0.0.1:8000/redoc` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |

### Docker Compose

```bash
docker compose up --build
```

Compose exposes port `8000` and stores the SQLite database and uploaded files in the `geospatial_data` named volume.

Stop the service with:

```bash
docker compose down
```

Use `docker compose down -v` only when the persisted database and uploads should also be deleted.

## Deploy to Vercel

The production deployment is one Python Vercel Function backed by external PostgreSQL. SQLite remains the zero-service local default but is rejected when `VERCEL=1`, because a serverless instance cannot provide durable local database storage.

1. Provision PostgreSQL through the Vercel Marketplace or another provider.
2. Set `DATABASE_URL` to its pooled connection URL.
3. Set `MAX_UPLOAD_SIZE_MB=4`, `MAX_PAGE_SIZE=100`, and `DELETE_UPLOAD_AFTER_PROCESSING=true`.
4. Import the repository in Vercel or deploy with `vercel --prod`.

`pyproject.toml` declares `app.main:app` as the Vercel entry point, `.python-version` selects Python 3.12, and `vercel.json` configures a 300-second function duration while excluding development files from the bundle.

The Vercel request and response limit is 4.5 MB, so this direct multipart V1 intentionally limits uploads to 4 MB to leave room for multipart overhead. Uploads are processed in `/tmp` and deleted after each request; only normalized database results are durable. See [Vercel deployment](docs/vercel.md) before deploying.

## Using the API

### Upload a KML file

```bash
curl --fail-with-body \
  -F 'file=@survey.kml;type=application/vnd.google-earth.kml+xml' \
  http://localhost:8000/api/files/
```

### Upload a zipped Shapefile

```bash
curl --fail-with-body \
  -F 'file=@parcels.zip;type=application/zip' \
  http://localhost:8000/api/files/
```

A successful upload is processed before the request returns:

```json
{
  "id": "2f2a86a1-84ca-48f9-b7bb-df0650da6e79",
  "filename": "survey.kml",
  "file_type": "KML",
  "upload_size": 1834,
  "feature_count": 3,
  "source_crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "status": "COMPLETED",
  "created_at": "2026-10-07T10:30:20Z",
  "updated_at": "2026-10-07T10:30:20Z"
}
```

### Retrieve results

```bash
FILE_ID=2f2a86a1-84ca-48f9-b7bb-df0650da6e79

curl "http://localhost:8000/api/files/$FILE_ID/"
curl "http://localhost:8000/api/files/$FILE_ID/features/?limit=100&offset=0"
curl "http://localhost:8000/api/files/$FILE_ID/measurements/?limit=100&offset=0"
```

### Endpoint summary

| Method | Path | Success | Purpose |
|---|---|---:|---|
| `GET` | `/health` | 200 | Process liveness |
| `POST` | `/api/files/` | 201 | Upload and synchronously process a file |
| `GET` | `/api/files/{id}/` | 200 | File metadata and processing status |
| `GET` | `/api/files/{id}/features/` | 200 | Original normalized features |
| `GET` | `/api/files/{id}/measurements/` | 200 | Per-feature measurement results |

Both collection endpoints accept `limit` and `offset`. The default page size is 100 and the default maximum is 500; both are configurable.

The full request and response contract is in [API reference](docs/api.md).

## Measurement behavior

| Source geometry | Measurement | Unit | Successful status |
|---|---|---|---|
| Polygon | Area | `m2` | `SUCCESS` |
| MultiPolygon | Total area | `m2` | `SUCCESS` |
| LineString | Length | `m` | `SUCCESS` |
| MultiLineString | Total length | `m` | `SUCCESS` |
| Point | None | — | `SKIPPED` |
| MultiPoint | None | — | `SKIPPED` |
| GeometryCollection or other unsupported type | None | — | `UNSUPPORTED` |
| Null or empty geometry | None | — | `SKIPPED` |
| Invalid geometry | None | — | `FAILED` |

Measurements are never calculated directly in longitude/latitude degrees. If the source CRS is geographic, GeoPandas estimates a dataset-level UTM CRS and a separate copy is transformed for measurement. A projected source CRS is reused only when its horizontal units are metres. The original geometry is never replaced by the projected copy.

See [Architecture and processing design](docs/architecture.md#crs-and-measurement-design) for the complete algorithm and trade-offs.

## Architecture

```text
Client
  │
  ▼
FastAPI route ──► FileService ──► geospatial functions ──► CRS selection
                      │                                      │
                      │                                      ▼
                      │                              Measurement service
                      ▼                                      │
               controlled storage                           ▼
                      │                            normalized Features
                      └──────────────► SQLAlchemy session ─────┘
                                             │
                                             ▼
                                      SQLite / SQLAlchemy
```

The HTTP layer validates transport concerns. Services own file and geospatial processing. Repositories own persistence. Pydantic schemas isolate the public contract from GeoPandas and SQLAlchemy objects.

### Repository structure

```text
app/
├── api/                 FastAPI routes and pagination
├── exceptions/          domain exceptions and HTTP handlers
├── models/              SQLAlchemy tables and enums
├── schemas/             Pydantic response contracts
├── services/            upload lifecycle and geospatial processing
├── utils/               archive security and JSON serialization
├── config.py            environment-backed settings
├── database.py          engine, sessions, and table initialization
└── main.py              application construction and health endpoint
tests/
├── unit/                isolated domain and utility behavior
├── integration/         API and real-format workflows
└── stress/              bounded large-data and concurrency checks
docs/                    detailed project documentation
vercel.json              Vercel function limits and bundle exclusions
.python-version          Vercel/local Python selection
```

Read [Architecture and processing design](docs/architecture.md) for component ownership, state transitions, persistence schema, and extension points.

## Configuration

Settings are read from environment variables and an optional `.env` file.

| Variable | Default | Validation | Purpose |
|---|---:|---|---|
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy URL | Database connection |
| `UPLOAD_DIR` | `./data/uploads` | writable path | Controlled upload storage |
| `MAX_UPLOAD_SIZE_MB` | `50` | positive integer | Maximum uploaded file size |
| `MAX_EXTRACTED_SIZE_MB` | `200` | positive integer | Maximum sum of ZIP entry sizes |
| `MAX_ARCHIVE_ENTRIES` | `1000` | positive integer | Maximum non-directory ZIP entries |
| `DEFAULT_PAGE_SIZE` | `100` | positive integer | Page size when `limit` is omitted |
| `MAX_PAGE_SIZE` | `500` | positive integer | Server-side cap for `limit` |
| `LOG_LEVEL` | `INFO` | logging level name | Application log verbosity |
| `DELETE_UPLOAD_AFTER_PROCESSING` | `false` locally, `true` on Vercel | boolean | Remove source bytes after normalized results are stored |
| `VERCEL` | set by Vercel | boolean | Activates serverless-safe defaults and validation |

Start from [.env.example](.env.example). Do not commit `.env` files containing deployment-specific values.

Operational guidance is in [Operations and deployment](docs/operations.md).

## Database and lifecycle

The local database contains two tables:

- `uploaded_files`: UUID, safe stored name, original basename, type, size, source and measurement CRS, feature count, lifecycle status, timestamps, and file-level error;
- `features`: upload foreign key, stable feature index, source identifier, original GeoJSON geometry and properties, measurement value/type/unit/status/message.

File states follow:

```text
UPLOADED ──► PROCESSING ──► COMPLETED
                  │
                  └────────► FAILED
```

Feature-level failures do not change a successfully readable file to `FAILED`; they are represented by that feature's measurement status.

## Error model

All application errors use one envelope:

```json
{
  "error": {
    "code": "INVALID_SHAPEFILE",
    "message": "The uploaded ZIP does not contain a valid Shapefile.",
    "details": {"missing": [".shx"]}
  }
}
```

Typical HTTP mappings are:

| Status | Meaning |
|---:|---|
| 404 | File UUID does not exist |
| 413 | Upload exceeds configured limit |
| 415 | Extension is not `.kml` or `.zip` |
| 422 | Validation, archive, format, CRS, or processing-domain error |
| 500 | Unexpected internal failure with a generic public message |

The complete error-code catalog is in [API reference](docs/api.md#error-catalog).

## Testing

Install development dependencies, then run:

```bash
pytest
pytest --cov=app --cov-branch --cov-report=term-missing
pytest -m stress
ruff check .
```

The verified baseline is 61 passing tests with 95% branch-aware coverage across unit, integration, regression, configuration, and stress behavior. The stress suite processes a 2,000-feature KML and exercises concurrent reads. These are deterministic regression loads, not universal latency or throughput guarantees.

See [Testing strategy](docs/testing.md) for test layers, coverage expectations, fixtures, and the verification matrix.

## Security

The implementation:

- stores uploads under generated UUID filenames;
- records only the basename of the client filename;
- rejects absolute, parent-traversing, and symbolic-link ZIP members;
- limits upload bytes, archive entries, and declared extracted bytes;
- extracts only inside a temporary directory and cleans it afterward;
- never executes uploaded content or constructs shell commands from it;
- rejects unknown CRS instead of making unsafe assumptions;
- omits paths, SQL details, tracebacks, and request values from public errors;
- runs as an unprivileged user in Docker.

Deployment responsibilities and residual risks are described in [Security model](docs/security.md).

## Known limitations

- Processing is synchronous and occupies an application worker until complete.
- One estimated UTM CRS is used for the entire dataset; very large, polar, global, or multi-zone data needs another strategy.
- SQLite is intended for local or single-instance use, not high-write multi-instance deployment.
- Geometry is stored as JSON rather than in spatial database columns.
- V1 accepts exactly one primary Shapefile per ZIP.
- Invalid geometry is reported but not repaired.
- Local/Docker source files are retained by default; Vercel deletes them after processing because `/tmp` is scratch space.
- Direct uploads and responses on Vercel must remain below its 4.5 MB payload limit.
- GeoPandas, Pyogrio, NumPy, and GDAL make the Python function bundle comparatively large; deployment must remain under Vercel's Python bundle limit.
- Authentication, authorization, rate limiting, malware scanning, and infrastructure request limits are deployment concerns not included in V1.

## Learning

The project demonstrates GDAL-backed vector parsing, the multi-file nature of Shapefiles, safe archive extraction, geographic versus projected coordinate systems, CRS transformation, metric Shapely measurements, typed API design, explicit lifecycle persistence, and realistic geospatial testing.

## Future scope

- PostgreSQL/PostGIS with migrations and spatial indexes
- S3-compatible object storage and retention policies
- Celery or another worker and queue for asynchronous processing
- upload status polling, webhooks, and cancellation
- streaming and resource isolation for large datasets
- GeoJSON, GPX, and multiple archive layers
- opt-in geometry repair and geodesic measurements
- configurable output units
- authentication, authorization, quotas, and rate limiting
- metrics, tracing, dashboards, and alerting
- map visualization frontend

## Documentation

| Document | Audience and purpose |
|---|---|
| [Architecture and processing design](docs/architecture.md) | Maintainers extending processing, storage, or CRS behavior |
| [API reference](docs/api.md) | API consumers and QA engineers |
| [Operations and deployment](docs/operations.md) | Developers and operators running the service |
| [Testing strategy](docs/testing.md) | Contributors validating changes |
| [Security model](docs/security.md) | Reviewers and deployment owners |
| [Vercel deployment](docs/vercel.md) | Developers deploying the serverless production shape |
