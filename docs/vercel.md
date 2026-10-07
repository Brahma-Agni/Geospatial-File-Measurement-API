# Vercel Deployment

## Production shape

```text
Internet
   │
   ▼
Vercel CDN / routing
   │
   ▼
One Python Function running FastAPI
   ├── /tmp/geospatial-uploads   request-scoped scratch files
   ├── GeoPandas / Pyogrio      parsing and projection
   └── pooled connection        external PostgreSQL
                                      │
                                      ▼
                            metadata and normalized features
```

This is still the same FastAPI application used locally. Vercel loads `app.main:app` from `[tool.vercel]` in `pyproject.toml`; no adapter or duplicated route layer is needed.

## Why SQLite and durable local uploads are not used

[Vercel Functions have a read-only filesystem with writable `/tmp` scratch space](https://vercel.com/docs/functions/runtimes#file-system-support). Scratch space is suitable for synchronous parsing but is not durable shared storage. The application therefore:

- rejects SQLite configuration when `VERCEL=1`;
- requires external PostgreSQL for durable metadata and normalized features;
- defaults `UPLOAD_DIR` to `/tmp/geospatial-uploads`;
- defaults `DELETE_UPLOAD_AFTER_PROCESSING` to `true`;
- deletes source bytes after either successful or failed processing.

If source files must be retained, add object storage rather than disabling cleanup. [Vercel Blob is intended for uploads and large objects](https://vercel.com/docs/storage#store-generated-files-with-vercel-blob), but it is deliberately not required for this synchronous V1 because normalized results are the durable product.

## Platform limits that shape the design

The current implementation is designed around the official limits, not around an always-on server assumption:

| Vercel constraint | Application decision |
|---|---|
| [4.5 MB maximum request or response payload](https://vercel.com/docs/functions/limitations#request-body-size) | App upload limit is 4 MB on Vercel; pagination should stay small |
| [500 MB writable `/tmp` scratch space](https://vercel.com/docs/functions/runtimes#file-system-support) | Temporary upload/extraction only, with immediate cleanup |
| [500 MB standard uncompressed Python bundle](https://vercel.com/docs/functions/runtimes/python#controlling-what-gets-bundled) | Exclude tests, docs, caches, and local data in `vercel.json` |
| Function duration is bounded | `maxDuration` is configured to 300 seconds; input remains small-to-medium |
| Serverless instances scale independently | Durable state is external PostgreSQL, never process memory or local files |

GeoPandas, NumPy, Pyogrio, PyProj, Shapely, and GDAL are substantial native dependencies. Confirm the built function size on every dependency upgrade. Vercel documents larger Python Functions as a beta option, but the standard bundle should remain the baseline.

## Required environment variables

Set these for Preview and Production in the Vercel project:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@POOLED_HOST/DATABASE?sslmode=require
MAX_UPLOAD_SIZE_MB=4
MAX_EXTRACTED_SIZE_MB=200
MAX_ARCHIVE_ENTRIES=1000
DEFAULT_PAGE_SIZE=50
MAX_PAGE_SIZE=100
DELETE_UPLOAD_AFTER_PROCESSING=true
LOG_LEVEL=INFO
```

Do not set `UPLOAD_DIR` unless there is a specific reason; the Vercel-aware default is `/tmp/geospatial-uploads`. Vercel injects `VERCEL=1`.

The database URL may use `postgres://`, `postgresql://`, or `postgresql+psycopg://`; the application normalizes the first two to SQLAlchemy's Psycopg 3 driver.

## Provision PostgreSQL

Use a PostgreSQL provider from the [Vercel Marketplace storage integrations](https://vercel.com/docs/storage#provision-databases-through-vercel-marketplace) or an external managed service.

Prefer a pooled/serverless connection URL and place the database in or near the function region. Map the provider's URL to `DATABASE_URL` if it uses another environment-variable name. The application uses SQLAlchemy `NullPool` on Vercel so warm function instances do not retain their own idle connection pools; the external pooler owns connection reuse.

V1 calls `create_all()` during application startup. That is acceptable for the initial schema but not a long-term migration strategy. Before changing production tables, add Alembic migrations and run them as a deployment/release step rather than from concurrent cold starts.

## Deploy from Git

1. Push the repository to GitHub, GitLab, or Bitbucket.
2. Import it from the Vercel dashboard.
3. Add the PostgreSQL integration or `DATABASE_URL` manually.
4. Add the remaining environment variables above.
5. Deploy.
6. Check the function build size and logs.
7. Call `/health`, open `/docs`, and upload a small representative KML and Shapefile.

Vercel detects FastAPI from `pyproject.toml`, reads `.python-version`, and uses the explicit `app.main:app` entry point. The official [Python runtime documentation](https://vercel.com/docs/functions/runtimes/python) describes this detection model.

## Deploy with the CLI

Use Vercel CLI 48.1.8 or newer:

```bash
npm install --global vercel
vercel login
vercel link
vercel env pull .env.vercel.local
vercel dev
vercel
vercel --prod
```

Do not copy production credentials into `.env` or commit pulled environment files.

## Post-deployment checks

```bash
BASE_URL=https://your-project.vercel.app

curl --fail "$BASE_URL/health"
curl --fail "$BASE_URL/openapi.json" > /tmp/openapi.json
curl --fail-with-body -F 'file=@small-survey.kml' "$BASE_URL/api/files/"
```

Then retrieve the returned UUID through metadata, feature, and measurement endpoints. Confirm that the measurement CRS is projected and that source coordinates remain unchanged.

## Operational cautions

- Cold starts must import the native geospatial stack; monitor initialization latency.
- CPU-heavy processing is billed function work and blocks the synchronous request.
- Large geometry/properties can make a paginated response exceed 4.5 MB even when the record count is small.
- A platform 413 may occur before FastAPI runs, so its body will use Vercel's error shape rather than the application error envelope.
- A function timeout may leave an upload record at `PROCESSING`; a future asynchronous design should add leases/timeouts and reconciliation.
- Do not deploy multiple regions against an unprepared database topology; keep compute near the primary database.

## When to change the architecture

Direct multipart processing is appropriate only while uploads fit below 4.5 MB and complete within the function duration. When either ceiling becomes limiting:

1. upload directly from the client to private Blob/object storage;
2. submit the object key to the API;
3. queue processing with Vercel Queues or another worker system;
4. return `202 Accepted` with the file UUID;
5. poll the existing metadata endpoint or deliver a webhook;
6. store source objects under an explicit retention policy.

That is a V2 scaling change, not infrastructure needed to understand or operate V1.
