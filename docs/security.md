# Security Model

## Trust boundaries

Uploaded filenames, file bytes, ZIP metadata, vector attributes, geometries, query parameters, and UUID path values are untrusted. Environment variables, the database, upload storage, reverse proxy, and deployment identity are operator-controlled trust boundaries.

## Implemented controls

### Upload handling

- Only `.kml` and `.zip` filename extensions are accepted.
- Uploads are streamed in 1 MiB chunks and stopped at `MAX_UPLOAD_SIZE_MB`.
- Client path components are removed with basename handling.
- Stored filenames use server-generated UUIDs.
- Uploaded bytes are never executed or used to build shell commands.
- Vercel writes only to `/tmp` and deletes the source after processing.

### Archive handling

- Invalid ZIP central directories are rejected.
- Absolute paths and `..` traversal are rejected after normalizing both slash styles.
- Symbolic-link entries are rejected.
- Non-directory entry count is capped.
- The sum of declared uncompressed entry sizes is capped.
- Each member is copied into a private temporary directory rather than extracted with an unrestricted bulk API.
- Exactly one primary `.shp` is accepted and matching `.shx` and `.dbf` files are required.
- Temporary extraction is removed when processing completes or fails.

### Data and API handling

- UUID path parameters and pagination constraints are validated by FastAPI/Pydantic.
- Unknown CRS is rejected instead of assumed.
- Invalid source geometry is not silently repaired or mutated.
- SQLAlchemy uses parameterized statements.
- Public errors omit request values, paths, SQL, and tracebacks.
- Server logs identify work by UUID rather than dumping file contents.

### Container handling

- The image runs as a non-root `appuser`.
- Only the application port is exposed.
- Persistent writes are directed to `/data`.

## Residual risks and deployment controls

Application validation cannot replace infrastructure controls:

| Risk | Deployment mitigation |
|---|---|
| Slow upload or request-body exhaustion | Reverse-proxy body size, header, rate, and timeout limits |
| High CPU/memory from valid complex geometry | Worker memory/time limits, queueing, feature limits, isolation |
| Compression-ratio abuse | Infrastructure resource limits and optional compressed-ratio policy |
| Malicious parser input | Current GDAL/Pyogrio packages, sandboxed workers, malware scanning where required |
| Unauthorized uploads/results | Authentication, authorization, tenant scoping |
| Brute-force or abusive traffic | Rate limits, quotas, WAF rules |
| Data retention/privacy | Encryption, access controls, retention and deletion jobs |
| Disk exhaustion | Capacity monitoring, quotas, cleanup policy |
| SQLite multi-instance corruption/locking | Single instance or migration to PostgreSQL |
| Vercel payload rejection | Keep direct request/response payloads below 4.5 MB or introduce direct object-storage uploads |

## Data sensitivity

Geospatial coordinates and attributes may be sensitive even when files contain no conventional personal identifiers. Operators should classify uploaded content, protect storage and backups, restrict logs, and define retention according to their security and privacy requirements.

## Error disclosure policy

Expected domain errors return a stable code, safe message, and minimal structured detail. Unexpected exceptions are logged internally and represented publicly as:

```json
{
  "error": {
    "code": "PROCESSING_FAILED",
    "message": "An unexpected server error occurred."
  }
}
```

Validation errors expose only field location, validation message, and type. They do not echo submitted values.

## Security regression coverage

Automated tests cover traversal with Unix and Windows separators, absolute paths, symbolic links, archive count and size limits, multiple primaries, generated storage names, oversized uploads, invalid UUIDs, and response sanitization.

## Review triggers

Repeat a focused security review when adding a new upload format, changing archive extraction, introducing geometry repair, moving processing to workers, adding object storage, exposing deletion, supporting multiple tenants, or changing authentication/authorization.
