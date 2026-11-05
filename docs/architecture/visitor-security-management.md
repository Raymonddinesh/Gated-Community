# Visitor & Security Management Foundation — Technical Specification (Phase 9)

## 1. Domain Entities & State Machines

### 1.1 Visitor Profile (`Visitor`)
- **Fields**: `id`, `society_id`, `name`, `phone`, `alternate_phone`, `visitor_type` (`GUEST`, `DELIVERY`, `SERVICE`, `CAB`, `OTHER`), `identification_type`, `identification_number`, `photo_file_key`, `notes`, `status` (`ACTIVE`, `BLOCKED`, `ARCHIVED`).

### 1.2 Visitor Invitation (`VisitorInvitation`)
- **Fields**: `id`, `society_id`, `visitor_id`, `host_user_id`, `unit_id`, `expected_date`, `expected_arrival_window_start`, `expected_arrival_window_end`, `expected_departure`, `purpose`, `pass_code`, `access_code_hash`, `delivery_company`, `service_type`, `status` (`PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`, `CANCELLED`, `USED`), `notes`.

### 1.3 Visitor Approval (`VisitorApproval`)
- **Fields**: `id`, `society_id`, `visitor_id`, `invitation_id`, `unit_id`, `approving_user_id`, `approval_status` (`PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`), `decision_reason`, `decision_time`.

### 1.4 Visitor Access Record (`VisitorAccessRecord`)
- **Fields**: `id`, `society_id`, `visitor_id`, `invitation_id`, `approval_id`, `unit_id`, `host_user_id`, `security_user_id`, `vehicle_id`, `visitor_name_snapshot`, `visitor_phone_snapshot`, `visitor_type_snapshot`, `gate_identifier`, `access_type` (`ENTRY`, `EXIT`), `access_time`, `entry_method` (`MANUAL`, `QR`, `OTP`, `PRE_APPROVED`), `exit_time`, `exit_gate_identifier`, `exit_security_user_id`, `exit_method`, `delivery_company`, `service_type`, `notes`, `emergency_override_reason`.

### 1.5 Visitor Document (`VisitorDocument`)
- **Fields**: `id`, `society_id`, `visitor_id`, `document_type` (`PHOTO`, `ID_CARD`, `DRIVING_LICENSE`, `PASSPORT`, `OTHER`), `file_key`, `file_name`, `file_size_bytes`, `content_type`, `uploaded_by`, `archived_at`.

---

## 2. Implemented vs Deferred Scope

### Implemented Now
- Multi-tenant visitor registration and search.
- Resident host pre-approved invitations with pass codes.
- Security guard walk-in registration with resident approval workflow.
- Gate entry check-in and exit check-out with append-only audit records.
- Immutability guards preventing deletion of access logs.
- Audit-logged emergency entry override.
- Delivery company and service personnel classification.
- Optional Phase 8 Vehicle linkage.
- Visitor document metadata upload and soft archival.
- Granular RBAC permissions for resident, security guard, and admin roles.
- PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`).

### Deferred / Out of Scope
- SMS / WhatsApp gateway integration.
- Facial recognition / AI license plate or identity scanner.
- Physical gate barrier hardware relay triggers.
- External delivery platform APIs (e.g. Swiggy/Zomato live webhooks).
- Permanent unrestricted visitor passes.
