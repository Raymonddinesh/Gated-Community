# Phase 16 — Announcement REST API Specification

## Endpoints

### Core Announcement Management
- `POST /api/v1/announcements`
  - Create a new draft announcement (`ANN-YYYY-XXXXXX`).
- `GET /api/v1/announcements`
  - List announcements targeted to the authenticated resident/user.
- `GET /api/v1/announcements/{announcement_id}`
  - Get detailed announcement with audiences, attachments, read state, and acknowledgement state.
- `PUT /api/v1/announcements/{announcement_id}`
  - Update announcement content. Creates version snapshot if published.
- `POST /api/v1/announcements/{announcement_id}/submit`
  - Submit draft announcement for administrative review.
- `POST /api/v1/announcements/{announcement_id}/approve`
  - Approve pending announcement.
- `POST /api/v1/announcements/{announcement_id}/reject`
  - Reject pending announcement.
- `POST /api/v1/announcements/{announcement_id}/publish`
  - Publish approved announcement immediately.
- `POST /api/v1/announcements/{announcement_id}/schedule`
  - Schedule deferred publication (`publish_at`).
- `POST /api/v1/announcements/{announcement_id}/expire`
  - Manually expire published announcement.
- `POST /api/v1/announcements/{announcement_id}/archive`
  - Archive announcement.

### Tracking & Metrics
- `POST /api/v1/announcements/{announcement_id}/read`
  - Record read receipt for user.
- `POST /api/v1/announcements/{announcement_id}/acknowledge`
  - Record mandatory explicit acknowledgement for current announcement version.
- `GET /api/v1/announcements/{announcement_id}/metrics`
  - View aggregate read and acknowledgement statistics.
- `GET /api/v1/announcements/{announcement_id}/audit-trail`
  - View status transition history audit trail.
