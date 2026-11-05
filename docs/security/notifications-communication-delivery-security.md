# Phase 20 — Notifications & Communication Delivery Foundation Security Architecture

## 1. Security Baseline & Threat Model

The Notifications & Communication Delivery domain handles sensitive PII (phone numbers, email addresses, resident names, unit numbers, emergency details). It requires strict security controls to prevent cross-tenant leakage, unauthorized broadcasts, and credential exposure.

### Threat Model & Mitigations

| Threat Vector | Risk Level | Architectural Mitigation |
|---|---|---|
| **Cross-Tenant Data Leakage** | CRITICAL | Mandatory `society_id` on all 10 Phase 20 tables with PostgreSQL `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`. |
| **IDOR in Notification Inbox** | HIGH | Endpoint authorization verifies `recipient_user_id == current_user.id` and `society_id == current_user.society_id`. |
| **Unauthorized Mass Broadcast** | HIGH | Mass notifications require `notification.send` permission and administrative authorization. |
| **Provider Credential Theft** | CRITICAL | Zero secrets stored in DB plaintext; provider credentials injected via environment / Vault secret manager. |
| **Webhook Forgery / Replay** | HIGH | Webhook endpoints enforce HMAC-SHA256 signature verification and anti-replay timestamp validation (max 300s clock skew). |
| **Emergency Priority Abuse** | HIGH | `CRITICAL` priority (which bypasses quiet hours) requires `incident.report` or `incident.override` permission. |
| **PII Exposure in Logs** | MEDIUM | Provider request/response logging sanitizes auth headers, phone numbers, and full message bodies. |
| **Template Code Injection** | HIGH | Jinja2 sandbox with allowlisted variable substitution; zero arbitrary code evaluation. |
| **Notification Amplification / Spam** | MEDIUM | Redis sliding-window rate limiters per user, per society, and per provider channel. |
| **Financial Ledger Mutation** | CRITICAL | Zero direct interaction or mutation of Phase 4-6 financial tables (`JournalEntry`, `Invoice`, `Payment`). |

---

## 2. PostgreSQL Row-Level Security (RLS) Policies

All 10 Phase 20 tables enforce strict RLS policies:

```sql
-- Standard Tenant Isolation Policy Pattern
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications FORCE ROW LEVEL SECURITY;

CREATE POLICY notifications_tenant_isolation ON notifications
    USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```

For shared template catalogs (global platform defaults):
```sql
ALTER TABLE notification_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_templates FORCE ROW LEVEL SECURITY;

CREATE POLICY notification_templates_tenant_isolation ON notification_templates
    USING (society_id IS NULL OR society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```

---

## 3. RBAC Permission Registry

Phase 20 introduces 15 canonical RBAC permissions:

1. `notification.view`: View society notification logs and delivery statuses.
2. `notification.view_own`: View personal in-app notification inbox.
3. `notification.create`: Create notification requests.
4. `notification.manage`: Full administrative notification management.
5. `notification.send`: Trigger mass broadcasts or manual notifications.
6. `notification.cancel`: Cancel scheduled or queued notifications.
7. `notification.template.view`: View notification templates.
8. `notification.template.manage`: Create and update notification templates.
9. `notification.preference.view`: View communication preferences.
10. `notification.preference.manage`: Modify personal communication preferences.
11. `notification.delivery.view`: View channel delivery tracking logs.
12. `notification.delivery.manage`: Manage delivery retries and suppressions.
13. `notification.audit.view`: View notification security audit logs.
14. `communication.provider.view`: View provider configurations.
15. `communication.provider.manage`: Manage provider adapter settings.
