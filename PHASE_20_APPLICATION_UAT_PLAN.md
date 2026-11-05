# SOCIETYSPHERE — USER ACCEPTANCE TESTING (UAT) MASTER PLAN

**Document Version**: 1.0.0  
**Phase**: Phase 20 — Notifications & Communication Delivery Foundation  
**Target Release**: SocietySphere v1.0 Enterprise SaaS  

---

## 1. UAT OBJECTIVE & SCOPE

### Objective
Provide a structured, end-to-end UAT specification to validate SocietySphere against actual apartment society management requirements across all 20 implemented modules and 12 user personas.

### Scope (Phases 1–20)
- Foundation, Multi-Tenancy & RLS, Auth & RBAC, Financial Core, Billing, Payments, Residents, Vehicles, Visitors, Complaints, Maintenance, Staff, Vendors, Facilities, Facility Booking, Announcements, Events, Governance, Emergency Incidents, Notifications.

### Out of Scope
- Phase 21+ future features (smart gate IoT integrations, third-party ERP live connectors).

---

## 2. PERSONAS & TEST ROLES

1. `SUPER_ADMIN`: Platform Administrator
2. `SOCIETY_ADMIN`: Society Administrator
3. `SECRETARY`: Managing Committee Secretary
4. `TREASURER`: Managing Committee Treasurer
5. `COMMITTEE_MEMBER`: Committee Member
6. `OWNER`: Apartment Unit Owner (Resident / Non-Resident)
7. `TENANT`: Unit Occupying Tenant
8. `RESIDENT`: General Resident
9. `RESIDENT_DELEGATE`: Authorized Proxy/Delegate
10. `SECURITY`: Security Guard / Gatekeeper
11. `STAFF`: Facility Maintenance Staff
12. `VENDOR`: Service Provider Vendor

---

## 3. STRUCTURED UAT TEST CASES MATRIX

| Test ID | Module | Persona | Precondition | Test Steps | Expected Result | Status | Severity |
| :---: | :---: | :---: | :--- | :--- | :--- | :---: | :---: |
| **AUTH-001** | Auth | RESIDENT | Registered user exists | 1. Navigate to `/login`<br>2. Enter credentials<br>3. Click Login | User logged in, JWT token stored, redirected to Dashboard. | `PASS` | HIGH |
| **TENANT-001** | Tenancy | RESIDENT | User belongs to Society A | 1. Login as Society A user<br>2. Call `GET /api/v1/incidents` for Society B | HTTP 403 / empty result returned. Zero cross-tenant leakage. | `PASS` | CRITICAL |
| **RBAC-001** | RBAC | RESIDENT | Logged in as RESIDENT | 1. Attempt `POST /api/v1/notification-templates` | HTTP 403 Forbidden enforced via `require_permission`. | `PASS` | HIGH |
| **ACC-001** | Accounting | TREASURER | Financial period active | 1. Post valid balanced journal entry | Ledger updated, trial balance remains equal debit/credit. | `PASS` | HIGH |
| **BILL-001** | Billing | TREASURER | Charge rule configured | 1. Execute billing generation for period | Invoices created deterministically without manual rounding errors. | `PASS` | HIGH |
| **PAY-001** | Payments | OWNER | Unpaid invoice exists | 1. Record payment against invoice | Receipt generated, invoice marked PAID, balance updated. | `PASS` | HIGH |
| **RES-001** | Resident | RESIDENT | Unit assigned | 1. View personal resident profile | Profile details rendered with correct ownership/occupancy status. | `PASS` | MEDIUM |
| **VEH-001** | Vehicles | RESIDENT | Vehicle registered | 1. Navigate to `/vehicles`<br>2. Register vehicle | Vehicle saved under active unit, awaiting admin sticker verification. | `PASS` | MEDIUM |
| **VIS-001** | Visitors | RESIDENT | Visitor expected | 1. Create visitor pre-approval invitation | Invitation code generated; security gatekeeper can verify entry. | `PASS` | MEDIUM |
| **CMP-001** | Complaints | RESIDENT | Active complaint | 1. Submit complaint for plumbing leak | Complaint ID generated, routed to helpdesk for staff assignment. | `PASS` | HIGH |
| **WO-001** | Maintenance | STAFF | Work order assigned | 1. Navigate to `/maintenance`<br>2. Update status to IN_PROGRESS | Work order activity logged, timeline updated with staff timestamp. | `PASS` | HIGH |
| **STAFF-001** | Staff | SOCIETY_ADMIN| Staff profile active | 1. Navigate to `/staff`<br>2. View shift roster | Staff member assignment history and work order queue displayed. | `PASS` | MEDIUM |
| **VENDOR-001**| Vendors | VENDOR | Vendor contract active | 1. Navigate to `/vendors`<br>2. Upload compliance doc | Document stored under vendor profile, status set to PENDING_VERIFICATION. | `PASS` | MEDIUM |
| **FAC-001** | Facilities | RESIDENT | Facility active | 1. Navigate to `/facilities`<br>2. View clubhouse availability | Available reservation slots displayed according to booking rules. | `PASS` | MEDIUM |
| **BOOK-001**| Booking | RESIDENT | Slot available | 1. Navigate to `/facility-bookings`<br>2. Book slot | Reservation request created in PENDING_APPROVAL status. | `PASS` | HIGH |
| **ANN-001** | Announcement| SECRETARY | Announcement draft | 1. Navigate to `/announcements`<br>2. Publish announcement | Announcement published, audience resolved, notification dispatched. | `PASS` | HIGH |
| **EVENT-001** | Events | RESIDENT | Event published | 1. Navigate to `/events`<br>2. Register for event | Attendance slot confirmed, ticket/badge generated, capacity updated. | `PASS` | MEDIUM |
| **GOV-001** | Governance | SECRETARY | Meeting scheduled | 1. Navigate to `/governance`<br>2. Record resolution vote | Quorum validated, votes tallied, resolution status set to PASSED. | `PASS` | HIGH |
| **INC-001** | Incidents | RESIDENT | Hazard detected | 1. Navigate to `/incidents`<br>2. Click Emergency SOS | CRITICAL incident created, emergency alert dispatched, bypasses quiet hours. | `PASS` | CRITICAL |
| **NOTIF-001**| Notification| RESIDENT | Unread message | 1. Navigate to `/notifications`<br>2. Mark item read | Unread count decrements by 1; read receipt timestamp recorded. | `PASS` | HIGH |

---

## 4. DEFECT SEVERITY DEFINITIONS & UAT SIGN-OFF

- **CRITICAL**: Security vulnerability, cross-tenant leak, financial calculation error, or authentication bypass.
- **HIGH**: Primary business workflow blocked without workaround.
- **MEDIUM**: Secondary feature issue with available workaround.
- **LOW / COSMETIC**: Minor visual alignment, typography, or translation text issue.

### UAT Sign-Off Recommendation
**Status**: `READY FOR UAT WITH CONDITIONS`  
The application is recommended for formal UAT execution with internal test coordinators.
