# Committee, Meetings & Resolutions Governance Security Model

## Row Level Security (RLS)
PostgreSQL RLS and `FORCE RLS` are enabled across all 12 Phase 18 tables in Alembic migration `20261005_0018_committee_meetings_resolutions_governance.py`:
- `committees`
- `committee_members`
- `meetings`
- `meeting_agenda_items`
- `meeting_attendances`
- `meeting_quorums`
- `resolutions`
- `resolution_votes`
- `resolution_status_histories`
- `meeting_minutes`
- `meeting_action_items`
- `governance_attachments`

All RLS policies enforce `society_id = current_setting('app.current_society_id')::uuid`.

## Canonical Governance Permissions
1. `committee.view`: View committee profiles and member lists.
2. `committee.manage`: Create, update, or archive committees and manage members.
3. `meeting.create`: Create meeting draft.
4. `meeting.view`: View meeting details, schedule, and agenda.
5. `meeting.view_all`: View all society governance meetings.
6. `meeting.update`: Modify meeting schedule, location, and agenda items.
7. `meeting.status.manage`: Advance meeting lifecycle state.
8. `quorum.manage`: Record and calculate meeting quorum status.
9. `resolution.create`: Propose resolution for meeting.
10. `resolution.view`: View resolution text, voting rules, and results.
11. `resolution.vote`: Cast vote on active resolution.
12. `minutes.create`: Prepare meeting minutes draft.
13. `minutes.approve`: Approve and publish meeting minutes (maker-checker).
14. `action_item.manage`: Create, assign, and update governance action items.

## Financial Isolation
Phase 18 governance domain maintains strict boundary separation from financial ledgers (`JournalEntry`, `Invoice`, `Payment`). Governance action items trigger domain events (`GOVERNANCE_ACTION_ITEM_CREATED`) without directly mutating financial tables.
