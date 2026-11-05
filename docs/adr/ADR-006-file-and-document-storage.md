# ADR 006: File & Document Storage Strategy

## Status
Accepted

## Context
SocietySphere manages diverse binary assets: society bye-laws, AGM meeting recordings/minutes, vendor contracts, proof of ownership documents, maintenance receipts, and visitor profile photos. 
Direct file storage on application servers or in database BLOB columns impairs scalability, introduces security vulnerabilities, and violates tenant isolation.

## Decision
1. **Object Storage Engine**:
   - S3-compatible object storage (AWS S3 in production; MinIO in local Docker/development).
2. **Tenant-Isolated Key Structure**:
   ```
   /{society_id}/{category}/{year}/{resource_id}/{file_hash}.{ext}
   ```
   Example:
   `/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/invoices/2026/inv-00421/receipt.pdf`
3. **Presigned URL Workflow**:
   - **Uploads**:
     1. Client requests upload URL from backend with metadata (mime-type, file size, target resource).
     2. Backend validates permissions and file constraints (max 10MB, allowed MIME types).
     3. Backend generates short-lived presigned PUT URL (5-minute expiration).
     4. Client uploads directly to object storage.
   - **Downloads / Views**:
     1. Zero public bucket policies. Buckets are 100% private.
     2. Client requests download URL through backend endpoint `/api/v1/documents/:id/download`.
     3. Backend validates tenant membership and document access rights.
     4. Backend generates short-lived presigned GET URL (60-second expiration).
4. **Antivirus & Content Scanning Hook**:
   - Storage upload notification triggers an asynchronous worker to scan uploads for malware prior to marking the document active.

## Consequences
### Positive
- Zero load on application backend servers for large file streaming.
- Defense-in-depth tenant boundary: file keys strictly prefixed by `society_id`.
- Ephemeral access links prevent unauthorized document forwarding or scraping.

### Negative / Trade-offs
- Upload workflows require a two-step handshake (metadata pre-registration followed by direct S3 upload).
