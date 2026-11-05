# Governance REST API Documentation

## Endpoints Summary

### Committees
- `POST /api/v1/governance/committees`: Create committee (`committee.manage`)
- `GET /api/v1/governance/committees`: List committees (`committee.view`)
- `GET /api/v1/governance/committees/{id}`: Get committee details (`committee.view`)
- `PATCH /api/v1/governance/committees/{id}`: Update committee (`committee.manage`)
- `POST /api/v1/governance/committees/{id}/members`: Add member (`committee.manage`)
- `GET /api/v1/governance/committees/{id}/members`: List members (`committee.view`)
- `DELETE /api/v1/governance/committees/{id}/members/{member_id}`: Remove member (`committee.manage`)

### Meetings & Quorum
- `POST /api/v1/governance/meetings`: Create meeting draft (`meeting.create`)
- `GET /api/v1/governance/meetings`: List meetings (`meeting.view`)
- `GET /api/v1/governance/meetings/{id}`: Get meeting (`meeting.view`)
- `PATCH /api/v1/governance/meetings/{id}`: Update meeting (`meeting.update`)
- `POST /api/v1/governance/meetings/{id}/transition`: Transition status (`meeting.status.manage`)
- `POST /api/v1/governance/meetings/{id}/agenda`: Add agenda item (`meeting.update`)
- `POST /api/v1/governance/meetings/{id}/quorum`: Record quorum (`quorum.manage`)
- `POST /api/v1/governance/meetings/{id}/attendance`: Record attendance (`meeting.update`)

### Resolutions & Voting
- `POST /api/v1/governance/resolutions`: Propose resolution (`resolution.create`)
- `GET /api/v1/governance/resolutions`: List resolutions (`resolution.view`)
- `GET /api/v1/governance/resolutions/{id}`: Get resolution (`resolution.view`)
- `POST /api/v1/governance/resolutions/{id}/transition`: Transition status (`resolution.create`)
- `POST /api/v1/governance/resolutions/{id}/vote`: Cast vote (`resolution.vote`)
- `GET /api/v1/governance/resolutions/{id}/votes`: List votes (`resolution.view`)

### Minutes & Action Items
- `POST /api/v1/governance/meetings/{id}/minutes`: Draft minutes (`minutes.create`)
- `GET /api/v1/governance/meetings/{id}/minutes`: Get minutes (`meeting.view`)
- `POST /api/v1/governance/meetings/{id}/minutes/approve`: Approve & publish minutes (`minutes.approve`)
- `POST /api/v1/governance/action-items`: Create action item (`action_item.manage`)
- `GET /api/v1/governance/action-items`: List action items (`meeting.view`)
- `PATCH /api/v1/governance/action-items/{id}`: Update action item (`action_item.manage`)
