# Vendor & Service Provider Management API Specification

## Endpoints Summary

### Categories
- `POST /api/v1/vendors/categories` — Create vendor service category
- `GET /api/v1/vendors/categories` — List vendor categories
- `GET /api/v1/vendors/categories/{id}` — Get vendor category details
- `PATCH /api/v1/vendors/categories/{id}` — Update category details

### Vendor Profiles
- `POST /api/v1/vendors` — Create new vendor profile
- `GET /api/v1/vendors` — Search and list vendors with pagination
- `GET /api/v1/vendors/{id}` — Get vendor profile details
- `PATCH /api/v1/vendors/{id}` — Update vendor profile
- `POST /api/v1/vendors/{id}/status` — Update vendor lifecycle status
- `DELETE /api/v1/vendors/{id}` — Archive vendor profile
- `GET /api/v1/vendors/{id}/status-history` — View vendor status audit history
- `GET /api/v1/vendors/{id}/assignments` — View vendor work order assignment history

### Contacts & Services
- `POST /api/v1/vendors/{id}/contacts` — Add vendor contact person
- `GET /api/v1/vendors/{id}/contacts` — List vendor contact persons
- `POST /api/v1/vendors/{id}/services` — Add offered service to catalog
- `GET /api/v1/vendors/{id}/services` — List offered services

### Documents
- `POST /api/v1/vendors/{id}/documents` — Upload compliance document
- `GET /api/v1/vendors/{id}/documents` — List vendor documents
- `DELETE /api/v1/vendors/documents/{id}` — Archive vendor document
