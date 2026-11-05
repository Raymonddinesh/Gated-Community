# ADR-027: Committee, Meetings & Resolutions Governance Architecture

## Status
Accepted (Locked)

## Context
Apartment societies require transparent, audit-compliant governance structures for managing committees, general body meetings (AGM/EGM), formal resolution voting, versioned meeting minutes, and actionable follow-ups.

## Decision
1. **Normalized Entities**: Create 12 normalized entities in `apps/api/src/database/models/governance.py` with PostgreSQL RLS + `FORCE RLS` enabled in Alembic migration `0018_committee_meetings_resolutions_governance.py`.
2. **Sequential Numbering & Concurrency Safety**: Use PostgreSQL advisory locking (`acquire_meeting_number_lock`, `acquire_resolution_number_lock`, `acquire_resolution_vote_lock`) for sequential `MTG-YYYY-XXXXXX` and `RES-YYYY-XXXXXX` generation and vote concurrency protection.
3. **Maker-Checker Minutes Control**: Enforce `minutes.prepared_by != approver_id` in `GovernanceService.approve_and_publish_minutes` to prevent authors from self-approving meeting minutes drafts.
4. **Deterministic Voting Engine**: Support `SIMPLE_MAJORITY`, `TWO_THIRDS`, and `UNANIMOUS` voting rules with duplicate vote prevention via unique constraint (`uq_resolution_user_vote`).
5. **Phase 11 Decoupling**: Decouple governance action items from Phase 11 maintenance work orders via domain events (`GOVERNANCE_ACTION_ITEM_CREATED`).

## Consequences
- Strict multi-tenant isolation guaranteed across all 12 governance tables.
- Zero mutation or side effects on financial ledgers (`JournalEntry`, `Invoice`, `Payment`).
- High-concurrency safety during AGM voting sessions.
