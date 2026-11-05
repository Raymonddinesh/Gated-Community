# Committee, Meetings & Resolutions Governance Foundation Architecture

## Overview
Phase 18 introduces the Committee, Meetings & Resolutions Governance Foundation for SocietySphere. It provides multi-tenant, audit-compliant governance capabilities for apartment societies, enabling managing committees, executive bodies, and sub-committees to convene meetings, calculate quorum, propose and vote on formal resolutions, track minutes with maker-checker controls, and manage governance action items.

## Domain Model
Phase 18 defines 12 core entities in `apps/api/src/database/models/governance.py`:
1. **Committee**: Standing or ad-hoc governance body (`MANAGING_COMMITTEE`, `SUB_COMMITTEE`, `AD_HOC`).
2. **CommitteeMember**: Committee positions and office bearers (`PRESIDENT`, `SECRETARY`, `TREASURER`, `MEMBER`).
3. **Meeting**: General body (AGM/EGM) or committee meetings with sequential `MTG-YYYY-XXXXXX` numbering.
4. **MeetingAgendaItem**: Sequential meeting agenda topics and discussion notes.
5. **MeetingAttendance**: Check-in, presence, and proxy records for meeting participants.
6. **MeetingQuorum**: Quorum calculation audit log (`ACHIEVED` vs `NOT_ACHIEVED`).
7. **Resolution**: Formal society resolutions with sequential `RES-YYYY-XXXXXX` numbering and voting rules (`SIMPLE_MAJORITY`, `TWO_THIRDS`, `UNANIMOUS`).
8. **ResolutionVote**: Anonymous or recorded votes cast by eligible residents/delegates.
9. **ResolutionStatusHistory**: Immutable lifecycle audit trail for resolutions.
10. **MeetingMinutes**: Versioned meeting minutes draft with maker-checker approval controls.
11. **MeetingActionItem**: Governance task assignments decoupled from maintenance work orders.
12. **GovernanceAttachment**: Uploaded circulars, signed notices, and legal annexures.

## Concurrency & Advisory Locks
Advisory locks are enforced via PostgreSQL transaction-level locks:
- `acquire_meeting_number_lock`: Prevents race conditions during sequential `MTG-YYYY-XXXXXX` generation.
- `acquire_resolution_number_lock`: Prevents race conditions during sequential `RES-YYYY-XXXXXX` generation.
- `acquire_resolution_vote_lock`: Enforces concurrency safety during high-throughput vote casting.

All advisory locks safely verify `bind.dialect.name == "postgresql"` to ensure compatibility with SQLite test environments.

## Governance State Machines
1. **MeetingStateMachine**: `DRAFT` -> `SCHEDULED` -> `NOTICE_PUBLISHED` -> `IN_PROGRESS` -> `COMPLETED` / `CANCELLED` / `ADJOURNED`.
2. **ResolutionStateMachine**: `DRAFT` -> `PROPOSED` -> `UNDER_DISCUSSION` -> `VOTING` -> `APPROVED` / `REJECTED` / `WITHDRAWN`.

## Maker-Checker Minutes Approval
To maintain governance integrity, `GovernanceService.approve_and_publish_minutes` verifies that `minutes.prepared_by != approver_id`. The author of a minutes draft cannot self-approve their own draft.
