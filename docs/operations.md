# Operations and Deployment

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload
```

On startup, the service configures logging, creates the upload directory, and calls SQLAlchemy metadata creation. V1 does not use a migration framework; schema changes require an explicit migration strategy before operating against durable production data.

## Configuration

Environment variables override `.env` values. All numeric limits must be positive integers.

| Variable | Development default | Operational guidance |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/app.db` | Use an absolute SQLite path in containers; production uses the pooled Neon PostgreSQL URL |
| `UPLOAD_DIR` | `./data/uploads` | Mount durable storage and grant write access to the service user |
| `MAX_UPLOAD_SIZE_MB` | `50` | Also enforce a request-body limit at the proxy/load balancer |
| `MAX_EXTRACTED_SIZE_MB` | `200` | Size is the sum of ZIP entry declarations |
| `MAX_ARCHIVE_ENTRIES` | `1000` | Reduce if expected archives are tightly controlled |
| `DEFAULT_PAGE_SIZE` | `100` | Balance request overhead and response size |
| `MAX_PAGE_SIZE` | `500` | Protect database and serialization work |
| `LOG_LEVEL` | `INFO` | Use `WARNING` or `INFO` in production unless diagnosing |

## Docker

Build and run with Compose:

```bash
docker compose up --build -d
docker compose logs -f api
curl --fail http://localhost:8000/health
```

The image runs as `appuser`, listens on port 8000, and uses:

```text
DATABASE_URL=sqlite:////data/app.db
UPLOAD_DIR=/data/uploads
```

The `geospatial_data` named volume mounts at `/data`.

## Vercel

Vercel is the production serverless target. It loads `app.main:app` from the `[tool.vercel]` entry point and deploys the complete API as one Python Function. Production requires external PostgreSQL through `DATABASE_URL`; the settings validator deliberately rejects SQLite when Vercel sets `VERCEL=1`.

The live deployment is [geospatial-file-measurement-api-pink.vercel.app](https://geospatial-file-measurement-api-pink.vercel.app). The function and Neon database are both configured in Singapore (`sin1`) to avoid unnecessary database round trips between regions.

Uploaded bytes use `/tmp/geospatial-uploads` only during processing and are deleted afterward. Set `MAX_UPLOAD_SIZE_MB=4` because the platform's 4.5 MB request limit includes multipart framing. Use a small `MAX_PAGE_SIZE`, such as 100, to reduce the chance of exceeding the same response limit.

For setup, exact limits, and deployment commands, read [Vercel deployment](vercel.md).

## Logging

Logs use a consistent timestamp, level, logger name, and message. Lifecycle messages include `file_id`; failures include a domain code or server exception context. Uploaded content and secret environment values are never logged.

Useful events include:

```text
file_uploaded file_id=<uuid> size=<bytes> type=<type>
processing_started file_id=<uuid>
processing_completed file_id=<uuid> features=<count>
processing_failed file_id=<uuid> code=<domain-code>
```

In production, ship standard output to the platform log collector and attach request correlation at the proxy or middleware layer.

## Health and readiness

`GET /health` is a liveness signal only. A production deployment should add or configure a readiness check that verifies database connectivity and upload-directory writeability without invoking expensive GDAL processing.

## Storage lifecycle

Local and Docker source uploads remain in `UPLOAD_DIR` unless cleanup is enabled. Vercel source uploads are deleted after processing. Temporary Shapefile extraction directories are always removed after the reader returns. No database retention task exists in V1; operators must establish backup and deletion policies for normalized records.

Back up SQLite consistently with the upload directory so metadata and source objects remain aligned. For active databases, use SQLite's supported backup mechanism rather than copying a changing database file blindly.

## Production checklist

- Run behind TLS termination.
- Enforce ingress request size and timeout limits.
- Mount writable, capacity-monitored persistent storage.
- Define source-file and database backup/retention policies.
- Use one application instance with SQLite; migrate to PostgreSQL for multi-instance use.
- Add authentication, authorization, quotas, and rate limiting for untrusted users.
- Add malware/content scanning if organizational policy requires it.
- Monitor error rate, processing time, file size, feature count, disk usage, and worker saturation.
- Pin and regularly update dependencies in the deployment build process.
- Validate representative KML and Shapefile inputs against the exact production GDAL build.

## Scaling path

For larger datasets or higher concurrency:

1. Return after storing the upload with status `UPLOADED`.
2. Queue the file UUID for a background worker.
3. Move source files to object storage.
4. Use PostgreSQL/PostGIS and formal migrations.
5. Add status polling or webhook delivery.
6. Apply worker memory/time limits and dead-letter handling.

The current lifecycle states and service boundaries support this evolution without changing stored result semantics.

## Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| Startup fails opening SQLite | Parent directory missing or unwritable | `DATABASE_URL`, volume ownership, upload directory creation |
| KML returns `INVALID_KML` | Invalid XML/geometry or unavailable driver | Server logs and Pyogrio/GDAL driver support |
| ZIP returns `INVALID_SHAPEFILE` | Missing `.shp`, `.shx`, `.dbf`, multiple `.shp`, or corrupt content | Archive member list and matching basenames |
| Upload returns `MISSING_CRS` | Shapefile has no usable `.prj` | Export with an authoritative CRS definition |
| Measurement CRS cannot be estimated | Invalid, polar, or unsuitable extent | Dataset bounds and alternative projection strategy |
| Requests are slow under uploads | Processing is synchronous and CPU/GDAL bound | File size, feature count, worker saturation |
| Local disk grows continuously | Source retention is enabled locally | Upload directory and cleanup policy |
