# Phase 11 — Maintenance & Work Order Management Architecture

## 1. Executive Summary

Phase 11 introduces a production-grade **Maintenance & Work Order Management** foundation for SocietySphere apartment societies. It provides end-to-end work-order domain capabilities—including category configuration, state machine transitions, scheduling, assignment tracking, internal/public comments, evidence attachments, material usage operational tracking, and SLA escalation—while strictly respecting architectural boundaries (no Staff Management, Vendor Management, Procurement, Inventory, or Financial Ledger mutations).

## 2. Core Entities & Database Schema

The domain consists of 12 tenant-isolated PostgreSQL tables:

1. `maintenance_categories`: Configurable categories (Plumbing, Electrical, Lift, etc.).
2. `maintenance_subcategories`: Sub-categories scoped to a parent category.
3. `maintenance_priority_policies`: Priority SLA policy configurations mapping priority/category to resolution targets.
4. `maintenance_work_orders`: Core work order records (`WO-YYYY-XXXXXX`).
5. `work_order_assignments`: Assignment history log for INTERNAL_USER, TEAM, STAFF, and VENDOR types.
6. `work_order_comments`: Public and Internal comments.
7. `work_order_attachments`: Evidence media and document attachments.
8. `work_order_status_histories`: Status transition audit history.
9. `work_order_escalations`: SLA breach escalation log.
10. `work_order_resolutions`: Resolution details and verification log.
11. `work_order_material_usages`: Operational materials and parts usage tracking.
12. `work_order_activities`: Unified chronological activity timeline.

## 3. Work Order State Machine

Status transitions follow a server-side state machine:
- `DRAFT` → `OPEN`, `CANCELLED`
- `OPEN` → `ASSIGNED`, `SCHEDULED`, `IN_PROGRESS`, `CANCELLED`
- `ASSIGNED` → `SCHEDULED`, `IN_PROGRESS`, `ON_HOLD`, `CANCELLED`
- `SCHEDULED` → `IN_PROGRESS`, `ON_HOLD`, `CANCELLED`
- `IN_PROGRESS` → `ON_HOLD`, `WAITING_FOR_PARTS`, `WAITING_FOR_RESIDENT`, `COMPLETED`, `VERIFIED`, `CANCELLED`
- `ON_HOLD` → `IN_PROGRESS`, `CANCELLED`
- `WAITING_FOR_PARTS` → `IN_PROGRESS`, `CANCELLED`
- `WAITING_FOR_RESIDENT` → `IN_PROGRESS`, `CANCELLED`
- `COMPLETED` → `VERIFIED`, `CLOSED`, `REOPENED`
- `VERIFIED` → `CLOSED`, `REOPENED`
- `CLOSED` → `REOPENED`
- `REOPENED` → `ASSIGNED`, `IN_PROGRESS`
- `CANCELLED` → (terminal state)

## 4. Work Order Numbering Concurrency

Work order numbers use the format `WO-YYYY-XXXXXX` (e.g. `WO-2026-000001`). Concurrency protection is guaranteed at the database level using transaction-scoped PostgreSQL advisory locks (`pg_advisory_xact_lock`) keyed deterministically on `(society_id, year)`.

## 5. Complaint & Phase 10 Integration

When a work order is created from a Phase 10 Complaint (`complaint_id`), the system verifies same-society ownership and accessibility. When a work order resolution is verified and accepted, the linked complaint status is cleanly updated to `RESOLVED` using `ComplaintService` application boundaries.

## 6. Financial Boundary

Phase 11 material usage records (`work_order_material_usages`) are purely operational trackers. No automatic journal entries, invoice postings, or accounting ledger mutations occur.
