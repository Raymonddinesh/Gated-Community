# Phase 16 — Announcements, Communications & Resident Notification Architecture

## Overview
Phase 16 establishes a production-grade multi-tenant Announcement, Communication & Resident Notification foundation for SocietySphere. It provides official society broadcasts, block/floor/unit/resident audience targeting, mandatory acknowledgements, read tracking receipts, material change versioning, attachment metadata, and decoupled domain event hooks.

## Domain Model & Table Architecture
- `announcements`: Core announcement entity (`ANN-YYYY-XXXXXX`).
- `announcement_audiences`: Multi-level audience targeting rules (SOCIETY, BLOCK, FLOOR, UNIT, RESIDENT).
- `announcement_attachments`: Object storage file attachment metadata.
- `announcement_acknowledgements`: Explicit resident mandatory acknowledgement tracking per version.
- `announcement_read_receipts`: Read receipts tracking.
- `announcement_schedules`: Publishing schedule for deferred publication.
- `announcement_status_histories`: Immutable status transition history log.
- `announcement_versions`: Immutable published version snapshots for material edits.

## Key Architectural Principles
1. **Audience Resolution (`AnnouncementAudienceResolver`)**:
   - Evaluates audience rules against authoritative Phase 2 & 7 hierarchy (Society, Block, Floor, Unit, Resident, Owner, Tenant).
   - Validates audience hierarchy objects belong strictly to the same `society_id` (preventing cross-tenant targeting IDOR).
2. **Concurrency Protection (`concurrency.py`)**:
   - Uses PostgreSQL transaction-level advisory locks (`pg_advisory_xact_lock`) on hashed `society_id` during sequential number generation (`ANN-YYYY-XXXXXX`).
3. **Multi-Tenancy & PostgreSQL RLS**:
   - RLS enabled & forced (`FORCE ROW LEVEL SECURITY`) on all 8 tables with `society_id` tenant isolation policies.
4. **Financial Isolation**:
   - Zero direct database writes to accounting, billing, invoice, or ledger tables.
5. **Notification Boundary**:
   - Emits decoupled domain events (`AnnouncementEventHooks`). Zero provider coupling with external SMS, WhatsApp, Email, or Push vendors.
