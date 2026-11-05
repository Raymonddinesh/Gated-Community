# Phase 11 — Maintenance & Work Order Management API Reference

## Endpoints Summary

Base Path: `/api/v1/maintenance`

### Categories & Subcategories
- `GET /categories`: List categories and subcategories.
- `POST /categories`: Create category (`maintenance.category.manage`).
- `POST /categories/{id}/subcategories`: Create subcategory (`maintenance.category.manage`).

### Work Orders Core
- `POST /work-orders`: Create work order (`maintenance.create`).
- `GET /work-orders`: List work orders with status/priority/category filters (`maintenance.view_own` / `maintenance.view_all`).
- `GET /work-orders/{id}`: Get work order detail.
- `POST /work-orders/{id}/schedule`: Update work order schedule (`maintenance.schedule`).
- `PATCH /work-orders/{id}/status`: Transition status machine (`maintenance.status.manage`).

### Assignments
- `POST /work-orders/{id}/assignments`: Assign/reassign work order (`maintenance.assign`).

### Comments & Attachments
- `GET /work-orders/{id}/comments`: List public and optional internal comments.
- `POST /work-orders/{id}/comments`: Post comment.
- `GET /work-orders/{id}/attachments`: List attachments.
- `POST /work-orders/{id}/attachments`: Upload evidence attachment.

### Materials Usage
- `GET /work-orders/{id}/materials`: List material usage items.
- `POST /work-orders/{id}/materials`: Track material/part usage (`maintenance.material.manage`).

### Resolution & Verification
- `POST /work-orders/{id}/complete`: Mark work order completed (`maintenance.resolve`).
- `POST /work-orders/{id}/verify`: Verify resolution (`maintenance.verify`).
- `POST /work-orders/{id}/close`: Close work order (`maintenance.close`).

### Escalation
- `POST /work-orders/{id}/escalate`: Trigger SLA breach escalation (`maintenance.escalate`).
