# Testing Strategy

## Goals

The test suite checks domain correctness, API compatibility, upload security, persistence behavior, and bounded workload stability. Real KML and Shapefile data are generated during tests so the suite does not depend on developer-machine fixture paths.

## Commands

```bash
# Complete suite
pytest

# Coverage, including branch decisions
pytest --cov=app --cov-branch --cov-report=term-missing

# Workload-focused tests only
pytest -m stress

# Style and static lint checks
ruff check .

# Optional formatting check
ruff format --check .
```

The verified delivery baseline is 61 passing tests and 95% branch-aware application coverage, including serverless configuration validation.

## Test layers

### Unit tests

Unit tests isolate behavior without HTTP:

- Polygon, MultiPolygon, LineString, and MultiLineString numeric measurement;
- point-family, GeometryCollection, invalid, empty, and null outcomes;
- geographic, metric projected, and non-metric projected CRS decisions;
- source geometry and property serialization, including NumPy scalars and non-finite values;
- feature normalization and original-coordinate preservation;
- Vercel defaults, external-database enforcement, payload limits, and cleanup requirements;
- malformed ZIP, traversal variants, symbolic links, entry/size limits, nested files, duplicate primaries, and missing Shapefile components.

### Integration tests

Integration tests run the FastAPI application with SQLAlchemy and actual GDAL/Pyogrio readers:

- health and OpenAPI-facing request behavior;
- valid KML and zipped Shapefile processing;
- metadata, feature, and measurement retrieval;
- pagination defaults, caps, boundaries, and validation;
- unsupported extension and upload-size behavior;
- malformed input, missing CRS, empty datasets, and unknown UUIDs.

### Regression and security tests

Regression tests protect previously discovered failure modes:

- validation error context must remain JSON serializable and must not echo input values;
- GeoPandas null geometry represented as `NaN` must remain a skipped feature;
- nullable KML attributes must normalize to JSON `null`;
- client paths must not control stored filenames;
- failed processing must persist a `FAILED` lifecycle record;
- original coordinates must not be replaced by projected measurement coordinates;
- error responses must not expose tracebacks or temporary paths.
- ephemeral source files must be removed when serverless cleanup is enabled.

### Stress tests

The `stress` marker currently covers:

- one KML containing 2,000 point features, including complete 500-record pagination;
- a burst of 120 concurrent metadata, feature, and measurement reads.

A live Docker smoke run has also been verified with a real upload and 75 concurrent reads. These loads are intended to expose race conditions, truncation, and state corruption. They are not a benchmark because timing depends on CPU, storage, GDAL build, and deployment topology.

## Fixture and database isolation

Tests use a file-backed SQLite database under `/tmp/geospatial-api-tests`. Tables are dropped and recreated around each test. File-backed SQLite is deliberate: an in-memory connection shared across threads does not model concurrent request behavior safely.

Temporary paths supplied by pytest contain generated Shapefile sidecars, ZIP archives, and KML data. Production paths are never referenced.

## Numeric assertions

Exact equality is appropriate for measurements in a known metric Cartesian CRS. Reprojected geographic results use `pytest.approx()` with a documented tolerance because projection and library versions may produce small numeric variation.

Tests should assert semantic behavior—CRS choice, type, unit, status, and reasonable measurement—not incidental floating-point formatting.

## Adding tests

- Put pure service and utility behavior in `tests/unit/`.
- Put database/HTTP/real-format behavior in `tests/integration/`.
- Add a regression test whenever a defect is fixed.
- Mark intentionally larger or concurrent checks with `@pytest.mark.stress`.
- Generate fixtures in `tmp_path`; do not add absolute developer paths.
- Assert public error codes and safe messages rather than internal exception text.
- Keep workload counts bounded so CI remains deterministic.

## Release verification checklist

1. `ruff format --check .`
2. `ruff check .`
3. `pytest --cov=app --cov-branch --cov-report=term-missing`
4. `docker build -t geospatial-measurement-api:verify .`
5. Start the image and verify `/health`.
6. Upload a real KML and zipped Shapefile to the container.
7. Confirm Swagger paths match the documented endpoints.
