# ADR-018: Visitor & Security Management Foundation Architecture

## Status
Approved / Implemented (Phase 9)

## Context
SocietySphere requires a multi-tenant, production-grade Visitor and Security Management module for apartment societies. The module must support resident pre-approved visitors, security guard walk-in check-in, resident real-time approval workflows, gate entry/exit check-in logging, delivery/service personnel handling, photo/document archival, emergency entry overrides, append-only access record immutability, and future QR/OTP readiness without introducing external hardware dependencies or breaking previous Phases 1–8 architectural guarantees.

## Decision
1. **Domain & Data Model Isolation**:
   - Established dedicated entities: `Visitor`, `VisitorInvitation`, `VisitorApproval`, `VisitorAccessRecord`, `VisitorDocument`.
   - Every entity includes mandatory `society_id` for multi-tenant Row-Level Security (RLS).
   - Reused existing Phase 7 `User`, `UserSocietyMembership`, `Unit`, `UnitOccupancy`, `ResidentProfile` models for resident host resolution.
   - Reused existing Phase 8 `Vehicle` domain for optional vehicle check-in linkage.

2. **Access Record Immutability**:
   - `VisitorAccessRecord` is append-only for gate check-in and updateable only for exit timestamp / exit gate.
   - ORM `before_delete` event listener raises `VisitorAccessRecordImmutableError` to block physical deletion.

3. **Granular Security & Emergency Override**:
   - Created fine-grained permissions: `visitor.view`, `visitor.create`, `visitor.invite`, `visitor.approve`, `visitor.reject`, `visitor.entry`, `visitor.exit`, `visitor.access.view`, `visitor.manage`, `visitor.emergency.override`.
   - Security guards receive gate operational capabilities (`visitor.entry`, `visitor.exit`, `visitor.view`, `visitor.access.view`).
   - Emergency overrides require `visitor.emergency.override` permission and mandate a logged audit reason.

4. **Document Archival**:
   - Visitor photos/ID card references use MinIO/S3 object storage keys.
   - Deleting a document executes soft archival (`archived_at`), excluding it from active listings while preserving audit compliance.

5. **Future QR / OTP & Hardware Integration Boundaries**:
   - Prepared `entry_method` enum values (`MANUAL`, `QR`, `OTP`, `PRE_APPROVED`) and `pass_code` generation.
   - Kept pure software readiness without integrating SMS gateways, external cameras, ANPR, or barrier hardware.

## Consequences
- Complete tenant data isolation under PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`).
- High-concurrency safety using in-memory advisory locks (`get_visitor_entry_lock`) preventing double entries.
- Absolute financial isolation: visitor operations create 0 accounting journal entries or billing alterations.
