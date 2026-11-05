# ADR-029: Notifications & Communication Delivery Foundation Architecture

## Status
APPROVED (Pre-Implementation Architecture Specification)

## Context
SocietySphere is a production-grade multi-tenant Apartment Society Management SaaS platform. Following the successful implementation and architectural lock of Phases 1 through 19 (including Maintenance, Visitors, Complaints, Work Orders, Staff, Vendor, Facility Asset, Facility Booking, Announcements, Events, Governance, and Emergency Incident Management), the platform requires a centralized, secure, provider-neutral notification and communication delivery framework.

Previously, individual domain modules emitted decoupled logging hooks (`DOMAIN_EVENT: ...` via `IncidentDomainHooks`, `GovernanceDomainHooks`, `EventDomainHooks`, `FacilityBookingEventHooks`, `AnnouncementEventHooks`). Business domains were strictly decoupled from communication vendor SDKs. Phase 20 establishes the authoritative central notification domain that ingests these domain events, evaluates recipient preferences, resolves templates and audiences, manages delivery across channels (In-App, Email, SMS, WhatsApp, Push), and tracks delivery lifecycle while maintaining absolute provider neutrality and strict multi-tenant RLS isolation.

## Architectural Principles & Decisions

### 1. Provider Neutrality
Business domains (e.g. Incidents, Billing, Work Orders) MUST NOT directly invoke vendor APIs (Twilio, SendGrid, AWS SNS, Firebase, WhatsApp Cloud API). All communication is routed through a unified `CommunicationProvider` abstraction with adapter interfaces (`InAppProvider`, `EmailProvider`, `SMSProvider`, `WhatsAppProvider`, `PushProvider`).

### 2. Transactional Isolation & Outbox Pattern
Business transactions (e.g. emergency reporting, invoice generation) MUST NOT depend on external communication provider availability. Domain events emit notification intents asynchronously (via domain event hooks and background workers) so provider outages or throttling never roll back core business database transactions.

### 3. Domain Event vs. Notification vs. Delivery Hierarchy
- **Domain Event**: Immutable record that something happened in a business domain (e.g., `INCIDENT_REPORTED`).
- **Notification Intent**: Decoupled directive to evaluate whether notifications should be generated.
- **Notification**: Logical message record generated for a target recipient.
- **Delivery**: Channel-specific attempt to transmit the notification to a recipient via a provider adapter.

### 4. Emergency & Critical Priority Override
Non-critical notifications respect user preferences and quiet hours. However, `CRITICAL` priority notifications (e.g., active fire, security threat, evacuation alerts from Phase 19) bypass quiet hours and channel opt-outs to ensure life-safety alerts reach residents immediately.

### 5. Multi-Tenant RLS & Privacy Filtering
Every Phase 20 entity contains `society_id` and enforces PostgreSQL Row-Level Security (`ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`). PII (phone numbers, email addresses, medical details) is masked for non-administrative viewers.

## Consequences
- **Positive**: Complete decoupling of business logic from communication providers; central delivery tracking, metrics, and audit trail; zero vendor lock-in; reliable asynchronous fan-out for mass broadcasts.
- **Negative**: Requires careful queue and worker orchestration; template versioning governance required.

## Status & Boundaries
Phase 20 is an ARCHITECTURE AND PRE-IMPLEMENTATION SPECIFICATION ONLY. No production code or database migrations are implemented during this phase.
