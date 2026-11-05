# Phase 20 — Notifications & Communication Delivery REST API Specification

## 1. Overview
The Phase 20 REST API provides endpoints for notification inbox management, user communication preferences, template catalog management, delivery tracking, and provider status monitoring.

All endpoints require Bearer JWT authentication and `X-Society-ID` tenant context header.

---

## 2. API Endpoints Specification

### In-App Notification Inbox

#### `GET /api/v1/notification-inbox`
- **Description**: Fetch personal in-app notification inbox for the authenticated user.
- **Permission**: `notification.view_own`
- **Query Parameters**:
  - `is_read` (boolean, optional)
  - `category` (string, optional)
  - `limit` (int, default=50, max=100)
  - `offset` (int, default=0)
- **Response**: `200 OK` -> `List[NotificationRecipientResponse]`

#### `POST /api/v1/notification-inbox/{recipient_id}/read`
- **Description**: Mark a specific in-app notification as read.
- **Permission**: `notification.view_own`
- **Response**: `200 OK` -> `NotificationRecipientResponse`

#### `POST /api/v1/notification-inbox/read-all`
- **Description**: Mark all unread notifications in the user's inbox as read.
- **Permission**: `notification.view_own`
- **Response**: `200 OK` -> `{ "updated_count": int }`

---

### User Communication Preferences

#### `GET /api/v1/notification-preferences`
- **Description**: Get communication preferences and quiet-hour settings for the current user.
- **Permission**: `notification.preference.view`
- **Response**: `200 OK` -> `NotificationPreferenceResponse`

#### `PUT /api/v1/notification-preferences`
- **Description**: Update communication preferences and quiet-hour settings.
- **Permission**: `notification.preference.manage`
- **Request Body**: `NotificationPreferenceUpdateRequest`
- **Response**: `200 OK` -> `NotificationPreferenceResponse`

---

### Notification Templates (Admin)

#### `GET /api/v1/notification-templates`
- **Description**: List notification templates for the society.
- **Permission**: `notification.template.view`
- **Response**: `200 OK` -> `List[NotificationTemplateResponse]`

#### `POST /api/v1/notification-templates`
- **Description**: Create a new notification template.
- **Permission**: `notification.template.manage`
- **Request Body**: `NotificationTemplateCreateRequest`
- **Response**: `201 Created` -> `NotificationTemplateResponse`

---

### Delivery Tracking & Audit (Admin)

#### `GET /api/v1/notification-deliveries`
- **Description**: List delivery logs across channels for administrative audit.
- **Permission**: `notification.delivery.view`
- **Query Parameters**:
  - `channel` (string, optional: `IN_APP`, `EMAIL`, `SMS`, `WHATSAPP`, `PUSH`)
  - `status` (string, optional)
  - `notification_id` (UUID, optional)
  - `limit` (int, default=50)
  - `offset` (int, default=0)
- **Response**: `200 OK` -> `List[NotificationDeliveryResponse]`

#### `POST /api/v1/notification-deliveries/{delivery_id}/retry`
- **Description**: Manually trigger a retry for a failed delivery task.
- **Permission**: `notification.delivery.manage`
- **Response**: `200 OK` -> `NotificationDeliveryResponse`
