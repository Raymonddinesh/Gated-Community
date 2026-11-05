"""Seed script for development and integration testing environments.

Populates:
1. Platform Permissions and Standard Roles (SUPER_ADMIN, SOCIETY_ADMIN, SECRETARY, TREASURER, RESIDENT, TENANT, SECURITY, COMMITTEE_MEMBER).
2. Global Users (Super Admin, Society A Admin, Owner, Tenant, Delegate, Society B Admin).
3. Society A (Palm Meadows CHS) with physical hierarchy (Block A, Block B -> Floors -> Units).
4. Society B (Greenwood Enclave) with physical hierarchy (Tower 1 -> Floors -> Units).
5. User Society Memberships, Unit Occupancies, Resident Profiles, and Role Assignments.
"""

import asyncio
import logging
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.auth.security.password import hash_password
from apps.api.src.core.config import get_settings
from apps.api.src.database.base import Base
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.authorization import Permission, Role, RoleAssignment, RolePermission
from apps.api.src.database.models.billing import (
    BillingPeriod,
    Invoice,
    InvoiceLine,
    MaintenanceChargeRule,
    Payment,
    PaymentAllocation,
    Receipt,
    SocietyBillingConfig,
)
from apps.api.src.database.models.complaint import (
    Complaint,
    ComplaintAssignment,
    ComplaintCategory,
    ComplaintComment,
    ComplaintSLAPolicy,
    ComplaintStatusHistory,
    ComplaintSubcategory,
)
from apps.api.src.database.models.finance import (
    Account,
    FinancialPeriod,
    JournalEntry,
    JournalEntryLine,
    SocietyAccountingConfig,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.membership import (
    ResidentDelegate,
    ResidentFamilyMember,
    ResidentProfile,
    UnitOccupancy,
    UnitOwnership,
    UserSocietyMembership,
)
from apps.api.src.database.models.reconciliation import (
    ReconciliationItem,
    ReconciliationSession,
)
from apps.api.src.database.models.society import Block, Floor, Society, Unit
from apps.api.src.database.models.vehicle import (
    Vehicle,
    VehicleAccessRecord,
    VehicleDocument,
    VehicleParkingAssociation,
    VehicleResidentAssociation,
    VehicleVerification,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")

# Deterministic UUIDs for development predictability
UUID_SUPER_ADMIN = uuid.UUID("11111111-1111-1111-1111-11111111111a")
UUID_SOCIETY_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
UUID_SOCIETY_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
UUID_USER_OWNER_A = uuid.UUID("22222222-2222-2222-2222-22222222222a")
UUID_USER_TENANT_A = uuid.UUID("33333333-3333-3333-3333-33333333333a")
UUID_USER_DELEGATE_A = uuid.UUID("44444444-4444-4444-4444-44444444444a")
UUID_USER_MEMBER_B = uuid.UUID("55555555-5555-5555-5555-55555555555b")


async def seed_data(session: AsyncSession) -> None:
    logger.info("Beginning database seeding...")

    # 1. Platform & Tenant Permissions
    permissions_data = [
        # Platform
        ("platform.admin", "Platform Administration", "platform", "Full access to platform administration"),
        ("society.create", "Create Society", "society", "Ability to create new societies"),
        # Society / Management
        ("society.read", "Read Society Details", "society", "View society configuration"),
        ("society.manage", "Manage Society Details", "society", "Modify society configuration"),
        ("units.read", "Read Units", "units", "View unit and block listings"),
        ("units.manage", "Manage Units", "units", "Modify unit allocations and properties"),
        ("occupancy.read", "Read Occupancies", "occupancy", "View resident and tenant occupancies"),
        ("occupancy.manage", "Manage Occupancies", "occupancy", "Approve or update unit occupancies"),
        ("roles.assign", "Assign Roles", "authorization", "Grant society roles to members"),
        ("audit.read", "Read Audit Logs", "audit", "View society audit logs"),
        # Finance & Accounting
        ("finance.read", "Read Financial Data", "finance", "View chart of accounts, journals, and reports"),
        ("finance.account.manage", "Manage Accounts", "finance", "Create and modify accounts and periods"),
        ("finance.journal.create", "Create Journals", "finance", "Create draft journals and import entries"),
        ("finance.journal.post", "Post Journals", "finance", "Commit draft journals to immutable ledger"),
        ("finance.journal.reverse", "Reverse Journals", "finance", "Create balanced journal reversals"),
        ("finance.expense.create", "Create Expenses", "finance", "Create draft operational expenses"),
        ("finance.expense.approve", "Approve Expenses", "finance", "Approve operational expenses"),
        (
            "finance.report.generate",
            "Generate Reports",
            "finance",
            "Generate and snapshot financial statements",
        ),
        ("finance.period.close", "Manage Periods", "finance", "Close or reopen financial periods"),
        # Maintenance Billing & Financial Obligations
        ("billing.config.manage", "Manage Billing Config", "billing", "Configure billing rules and cycles"),
        (
            "billing.rule.manage",
            "Manage Charge Rules",
            "billing",
            "Create and modify maintenance charge rules",
        ),
        ("billing.period.create", "Create Billing Periods", "billing", "Open and manage billing periods"),
        (
            "billing.generate",
            "Generate Invoices",
            "billing",
            "Execute deterministic billing invoice generation",
        ),
        ("billing.review", "Review Invoices", "billing", "Review generated invoices"),
        ("billing.approve", "Approve Invoices", "billing", "Approve invoices for publication"),
        ("billing.publish", "Publish Invoices", "billing", "Publish invoices and post to general ledger"),
        (
            "billing.adjust",
            "Adjust Invoices",
            "billing",
            "Apply discounts, waivers, or corrections to invoices",
        ),
        ("billing.credit_note", "Issue Credit Notes", "billing", "Issue credit notes against invoices"),
        ("billing.debit_note", "Issue Debit Notes", "billing", "Issue debit notes against invoices"),
        ("billing.payment.record", "Record Payments", "billing", "Record incoming resident payments"),
        (
            "billing.payment.allocate",
            "Allocate Payments",
            "billing",
            "Allocate payments against unpaid invoices",
        ),
        ("billing.receipt.view", "View Receipts", "billing", "View issued payment receipts"),
        (
            "billing.reports.view",
            "View Billing Reports",
            "billing",
            "View billing registers, aging, and summaries",
        ),
        (
            "billing.resident.view",
            "Resident Billing Self-Service",
            "billing",
            "View personal invoices and receipts",
        ),
        # Resident & Occupancy Domain (Phase 7)
        ("resident.profile.view", "View Resident Profile", "resident", "View resident profile details"),
        ("resident.profile.update", "Update Resident Profile", "resident", "Update resident profile details"),
        ("resident.create", "Create Resident", "resident", "Add resident profile to society"),
        ("resident.update", "Update Resident", "resident", "Modify resident profile"),
        ("resident.occupancy.view", "View Occupancy", "occupancy", "View unit occupancy records"),
        ("resident.occupancy.create", "Create Occupancy", "occupancy", "Create unit occupancy / move-in"),
        ("resident.occupancy.end", "End Occupancy", "occupancy", "End unit occupancy / move-out"),
        (
            "resident.occupancy.history",
            "View Occupancy History",
            "occupancy",
            "View historical occupancy records",
        ),
        (
            "resident.owner.manage",
            "Manage Ownership",
            "ownership",
            "Manage unit ownership and joint co-owners",
        ),
        ("resident.family.manage", "Manage Family", "household", "Manage household family members"),
        ("resident.delegate.manage", "Manage Delegates", "household", "Manage resident delegates"),
        (
            "resident.contact.view",
            "View Unmasked Contact",
            "resident",
            "View full unmasked resident contact information",
        ),
        ("resident.emergency.view", "View Emergency Contact", "resident", "View resident emergency contacts"),
        # Vehicle Management & Access Foundation (Phase 8)
        ("vehicle.view", "View Vehicle", "vehicle", "View registered vehicles and access logs"),
        ("vehicle.create", "Register Vehicle", "vehicle", "Register a new vehicle in society"),
        ("vehicle.update", "Update Vehicle", "vehicle", "Update vehicle details"),
        ("vehicle.verify", "Verify Vehicle", "vehicle", "Approve or reject vehicle verification"),
        (
            "vehicle.deactivate",
            "Deactivate Vehicle",
            "vehicle",
            "Deactivate, mark sold, transferred or scrapped",
        ),
        ("vehicle.document.view", "View Vehicle Documents", "vehicle", "View RC, insurance, PUC documents"),
        (
            "vehicle.document.manage",
            "Manage Vehicle Documents",
            "vehicle",
            "Upload and manage vehicle documents",
        ),
        ("vehicle.access.view", "View Vehicle Access Logs", "vehicle", "View gate entry and exit history"),
        (
            "vehicle.access.record",
            "Record Vehicle Access",
            "vehicle",
            "Record vehicle entry/exit at security gates",
        ),
        # Visitor & Security Management Foundation (Phase 9)
        ("visitor.view", "View Visitor", "visitor", "View visitor details and history"),
        ("visitor.create", "Register Visitor", "visitor", "Register new visitor profile"),
        ("visitor.invite", "Invite Visitor", "visitor", "Create pre-approved visitor invitations"),
        ("visitor.approve", "Approve Visitor Entry", "visitor", "Approve pending visitor entry"),
        ("visitor.reject", "Reject Visitor Entry", "visitor", "Reject pending visitor entry"),
        ("visitor.entry", "Record Visitor Entry", "visitor", "Check in visitor at security gate"),
        ("visitor.exit", "Record Visitor Exit", "visitor", "Check out visitor at security gate"),
        ("visitor.access.view", "View Gate Access History", "visitor", "View gate entry and exit history"),
        ("visitor.manage", "Manage Visitors", "visitor", "Full visitor profile administration"),
        (
            "visitor.emergency.override",
            "Emergency Entry Override",
            "visitor",
            "Execute audit-logged emergency entry override",
        ),
        # Complaints & Helpdesk Management Foundation (Phase 10)
        ("complaint.create", "Create Complaint", "complaint", "Raise new complaints and service requests"),
        (
            "complaint.view_own",
            "View Own Complaints",
            "complaint",
            "View complaints created by self or for unit",
        ),
        ("complaint.view_all", "View All Complaints", "complaint", "View all complaints in society"),
        ("complaint.comment", "Add Public Comment", "complaint", "Add public comments to complaints"),
        (
            "complaint.comment_internal",
            "Add Internal Note",
            "complaint",
            "Add internal staff notes to complaints",
        ),
        ("complaint.assign", "Assign Complaint", "complaint", "Assign complaints to helpdesk/staff"),
        (
            "complaint.priority.manage",
            "Manage Complaint Priority",
            "complaint",
            "Change complaint priority level",
        ),
        ("complaint.status.manage", "Manage Complaint Status", "complaint", "Transition complaint status"),
        ("complaint.sla.manage", "Manage SLA Policies", "complaint", "Configure and override SLA policies"),
        ("complaint.escalate", "Escalate Complaint", "complaint", "Escalate overdue or critical complaints"),
        ("complaint.resolve", "Resolve Complaint", "complaint", "Mark complaint as resolved"),
        ("complaint.close", "Close Complaint", "complaint", "Close resolved complaints"),
        ("complaint.reopen", "Reopen Complaint", "complaint", "Reopen resolved or closed complaints"),
        ("complaint.cancel", "Cancel Complaint", "complaint", "Cancel active complaints"),
        (
            "complaint.category.manage",
            "Manage Categories",
            "complaint",
            "Manage complaint categories and subcategories",
        ),
        (
            "complaint.attachment.manage",
            "Manage Attachments",
            "complaint",
            "Upload or soft-delete evidence attachments",
        ),
        (
            "complaint.audit.view",
            "View Complaint Audit",
            "complaint",
            "View detailed complaint status history and SLA logs",
        ),
        # Maintenance & Work Order Management Foundation (Phase 11)
        ("maintenance.create", "Create Work Order", "maintenance", "Create new maintenance work orders"),
        (
            "maintenance.view_own",
            "View Own Work Orders",
            "maintenance",
            "View work orders requested by self or for unit",
        ),
        (
            "maintenance.view_all",
            "View All Work Orders",
            "maintenance",
            "View all maintenance work orders in society",
        ),
        (
            "maintenance.assign",
            "Assign Work Order",
            "maintenance",
            "Assign work orders to users, teams, staff, or vendors",
        ),
        (
            "maintenance.schedule",
            "Schedule Work Order",
            "maintenance",
            "Schedule start and end dates for work orders",
        ),
        (
            "maintenance.priority.manage",
            "Manage Priority",
            "maintenance",
            "Manage work order operational priority",
        ),
        ("maintenance.status.manage", "Manage Status", "maintenance", "Transition work order status machine"),
        ("maintenance.comment", "Add Public Comment", "maintenance", "Add public comments to work orders"),
        (
            "maintenance.comment_internal",
            "Add Internal Note",
            "maintenance",
            "Add internal staff notes to work orders",
        ),
        (
            "maintenance.attachment.manage",
            "Manage Attachments",
            "maintenance",
            "Upload or archive work order attachments",
        ),
        (
            "maintenance.material.manage",
            "Manage Materials",
            "maintenance",
            "Track operational material usages",
        ),
        (
            "maintenance.sla.manage",
            "Manage Priority Policies",
            "maintenance",
            "Configure priority SLA policies",
        ),
        ("maintenance.escalate", "Escalate Work Order", "maintenance", "Escalate overdue work orders"),
        (
            "maintenance.resolve",
            "Resolve Work Order",
            "maintenance",
            "Mark work order as completed / resolved",
        ),
        ("maintenance.verify", "Verify Resolution", "maintenance", "Verify completed work orders"),
        ("maintenance.close", "Close Work Order", "maintenance", "Close verified work orders"),
        (
            "maintenance.reopen",
            "Reopen Work Order",
            "maintenance",
            "Reopen completed, verified, or closed work orders",
        ),
        ("maintenance.cancel", "Cancel Work Order", "maintenance", "Cancel active work orders"),
        (
            "maintenance.category.manage",
            "Manage Categories",
            "maintenance",
            "Manage maintenance categories and subcategories",
        ),
        (
            "maintenance.audit.view",
            "View Audit Timeline",
            "maintenance",
            "View work order activity history and audit logs",
        ),
        # Staff & Workforce Management Foundation (Phase 12)
        ("staff.create", "Create Staff Profile", "staff", "Create new staff profiles"),
        ("staff.view", "View Staff Profile", "staff", "View operational staff profiles"),
        (
            "staff.view_sensitive",
            "View Sensitive Contact",
            "staff",
            "View unmasked staff phone, emergency contacts, and sensitive PII",
        ),
        ("staff.update", "Update Staff Profile", "staff", "Update operational staff profile details"),
        (
            "staff.status.manage",
            "Manage Staff Status",
            "staff",
            "Update staff status lifecycle (activate, suspend, offboard)",
        ),
        (
            "staff.role.manage",
            "Manage Staff Roles",
            "staff",
            "Manage operational staff roles and assignments",
        ),
        ("staff.team.manage", "Manage Staff Teams", "staff", "Manage operational staff teams"),
        ("staff.team.assign", "Assign Team Members", "staff", "Assign staff to operational teams"),
        ("staff.document.manage", "Manage Staff Documents", "staff", "Upload or archive staff documents"),
        ("staff.document.view", "View Staff Documents", "staff", "View and download staff documents"),
        (
            "staff.assignment.view",
            "View Staff Assignments",
            "staff",
            "View work order assignment history for staff",
        ),
        ("staff.audit.view", "View Staff Audit", "staff", "View staff status history and audit logs"),
        ("staff.archive", "Archive Staff Profile", "staff", "Offboard and archive staff profiles"),
        # Vendor & Service Provider Management Foundation (Phase 13)
        ("vendor.create", "Create Vendor Profile", "vendor", "Create vendor profiles"),
        ("vendor.view", "View Vendor Profile", "vendor", "View basic vendor details"),
        (
            "vendor.view_sensitive",
            "View Sensitive Vendor Contact",
            "vendor",
            "View sensitive vendor contact and document details",
        ),
        (
            "vendor.update",
            "Update Vendor Profile",
            "vendor",
            "Update vendor profiles, contacts, and services",
        ),
        (
            "vendor.status.manage",
            "Manage Vendor Status",
            "vendor",
            "Update vendor status lifecycle (activate, suspend, blacklist)",
        ),
        ("vendor.category.manage", "Manage Vendor Categories", "vendor", "Manage vendor service categories"),
        (
            "vendor.service.manage",
            "Manage Vendor Services",
            "vendor",
            "Manage offered vendor service catalog",
        ),
        ("vendor.contact.manage", "Manage Vendor Contacts", "vendor", "Manage vendor contact persons"),
        (
            "vendor.document.manage",
            "Manage Vendor Documents",
            "vendor",
            "Upload or archive vendor compliance documents",
        ),
        ("vendor.document.view", "View Vendor Documents", "vendor", "View uploaded vendor documents"),
        (
            "vendor.assignment.view",
            "View Vendor Assignments",
            "vendor",
            "View work order assignment history for vendors",
        ),
        ("vendor.assignment.manage", "Manage Vendor Assignments", "vendor", "Assign work orders to vendors"),
        ("vendor.audit.view", "View Vendor Audit", "vendor", "View vendor status history and audit logs"),
        ("vendor.archive", "Archive Vendor Profile", "vendor", "Offboard and archive vendor profiles"),
        # Facility & Asset Management Foundation (Phase 14)
        ("facility.create", "Create Facility", "facility", "Create physical facilities in society"),
        ("facility.view", "View Facility", "facility", "View facility profile and details"),
        ("facility.update", "Update Facility", "facility", "Update facility information and sub-areas"),
        (
            "facility.status.manage",
            "Manage Facility Status",
            "facility",
            "Update facility status (active, maintenance, closed)",
        ),
        (
            "facility.area.manage",
            "Manage Facility Areas",
            "facility",
            "Create and modify sub-areas within facility",
        ),
        (
            "facility.document.manage",
            "Manage Facility Documents",
            "facility",
            "Upload or archive facility operational documents",
        ),
        ("facility.document.view", "View Facility Documents", "facility", "View uploaded facility documents"),
        (
            "facility.audit.view",
            "View Facility Audit Logs",
            "facility",
            "View facility change logs and audit history",
        ),
        ("facility.archive", "Archive Facility", "facility", "Decommission and archive facilities"),
        ("asset.create", "Create Asset", "asset", "Register new physical asset"),
        ("asset.view", "View Asset Details", "asset", "View asset details and operational status"),
        (
            "asset.view_sensitive",
            "View Sensitive Asset Information",
            "asset",
            "View sensitive asset details such as serial numbers, model numbers, vendor IDs",
        ),
        ("asset.update", "Update Asset Details", "asset", "Update asset attributes, serial numbers, models"),
        (
            "asset.status.manage",
            "Manage Asset Status",
            "asset",
            "Transition asset status (in service, maintenance, out of service, disposed)",
        ),
        ("asset.category.manage", "Manage Asset Categories", "asset", "Manage asset category taxonomy"),
        (
            "asset.location.manage",
            "Manage Asset Location History",
            "asset",
            "Track and update physical movement of assets",
        ),
        (
            "asset.assignment.manage",
            "Manage Asset Assignments",
            "asset",
            "Assign asset to staff, vendor, or location",
        ),
        (
            "asset.document.manage",
            "Manage Asset Documents",
            "asset",
            "Upload or archive asset manuals, warranties, and invoices",
        ),
        ("asset.document.view", "View Asset Documents", "asset", "View uploaded asset documents"),
        (
            "asset.maintenance.link",
            "Link Asset to Work Orders",
            "asset",
            "Link asset to maintenance work orders and complaints",
        ),
        (
            "asset.audit.view",
            "View Asset Audit History",
            "asset",
            "View asset status history and movement logs",
        ),
        ("asset.archive", "Archive / Dispose Asset", "asset", "Dispose or decommission assets"),
        # Facility Booking & Common Area Reservation (Phase 15)
        (
            "facility.booking.create",
            "Create Facility Booking Request",
            "facility_booking",
            "Create facility reservation request",
        ),
        (
            "facility.booking.view",
            "View Basic Booking Info",
            "facility_booking",
            "View basic facility booking details",
        ),
        (
            "facility.booking.view_own",
            "View Own Bookings",
            "facility_booking",
            "View personal facility booking history",
        ),
        (
            "facility.booking.view_all",
            "View All Facility Bookings",
            "facility_booking",
            "View all society facility bookings",
        ),
        (
            "facility.booking.update",
            "Update Booking Details",
            "facility_booking",
            "Update draft or pending booking request",
        ),
        (
            "facility.booking.approve",
            "Approve Booking Requests",
            "facility_booking",
            "Approve pending facility reservation requests",
        ),
        (
            "facility.booking.reject",
            "Reject Booking Requests",
            "facility_booking",
            "Reject pending facility reservation requests",
        ),
        ("facility.booking.cancel", "Cancel Facility Booking", "facility_booking", "Cancel facility booking"),
        (
            "facility.booking.override",
            "Administrative Booking Override",
            "facility_booking",
            "Override booking rules or blackouts",
        ),
        (
            "facility.booking.manage_rules",
            "Manage Facility Booking Rules",
            "facility_booking",
            "Configure facility booking rules and capacity limits",
        ),
        (
            "facility.booking.manage_availability",
            "Manage Operating Hours",
            "facility_booking",
            "Configure facility availability windows",
        ),
        (
            "facility.booking.manage_blackout",
            "Manage Blackout Periods",
            "facility_booking",
            "Manage facility blackout and maintenance periods",
        ),
        (
            "facility.booking.checkin",
            "Perform Booking Check-In",
            "facility_booking",
            "Mark facility booking as checked-in",
        ),
        (
            "facility.booking.complete",
            "Mark Booking Completed",
            "facility_booking",
            "Mark facility booking as completed",
        ),
        (
            "facility.booking.no_show",
            "Mark Booking No-Show",
            "facility_booking",
            "Mark facility booking as no-show",
        ),
        (
            "facility.booking.audit.view",
            "View Booking Audit History",
            "facility_booking",
            "View booking status history and audit trail",
        ),
        # Announcements, Communications & Resident Notification (Phase 16)
        ("announcement.create", "Create Draft Announcement", "announcement", "Create new draft announcement"),
        ("announcement.view", "View Announcements", "announcement", "View announcements targeted to user"),
        (
            "announcement.view_own",
            "View Own Announcements",
            "announcement",
            "View announcements created by user",
        ),
        ("announcement.view_all", "View All Announcements", "announcement", "View all society announcements"),
        (
            "announcement.update",
            "Update Announcement Draft",
            "announcement",
            "Update draft or pending announcement",
        ),
        (
            "announcement.submit",
            "Submit Announcement for Review",
            "announcement",
            "Submit draft announcement for administrative review",
        ),
        ("announcement.review", "Review Announcement", "announcement", "Review pending announcement request"),
        (
            "announcement.approve",
            "Approve Announcement",
            "announcement",
            "Approve pending announcement for publication",
        ),
        ("announcement.reject", "Reject Announcement", "announcement", "Reject pending announcement request"),
        (
            "announcement.publish",
            "Publish Announcement",
            "announcement",
            "Publish approved announcement immediately",
        ),
        (
            "announcement.schedule",
            "Schedule Announcement Publication",
            "announcement",
            "Schedule future announcement publication",
        ),
        (
            "announcement.archive",
            "Archive Announcement",
            "announcement",
            "Archive expired or published announcement",
        ),
        ("announcement.expire", "Expire Announcement", "announcement", "Manually mark announcement expired"),
        (
            "announcement.audience.manage",
            "Manage Announcement Audience",
            "announcement",
            "Manage audience targeting rules",
        ),
        (
            "announcement.attachment.manage",
            "Manage Announcement Attachments",
            "announcement",
            "Upload or manage announcement attachment files",
        ),
        (
            "announcement.acknowledgement.view",
            "View Acknowledgement Metrics",
            "announcement",
            "View announcement acknowledgement status and statistics",
        ),
        (
            "announcement.read_receipt.view",
            "View Read Receipt Metrics",
            "announcement",
            "View announcement read receipt status and statistics",
        ),
        (
            "announcement.audit.view",
            "View Announcement Audit History",
            "announcement",
            "View announcement lifecycle audit trail",
        ),
        # Events & Community Management Foundation (Phase 17)
        ("event.create", "Create Event Draft", "event", "Create new event draft"),
        ("event.view", "View Eligible Events", "event", "View published events targeted to resident"),
        ("event.view_all", "View All Events", "event", "View all society events regardless of status"),
        ("event.update", "Update Event Draft", "event", "Modify event details and capacity"),
        (
            "event.submit",
            "Submit Event for Approval",
            "event",
            "Submit event draft for administrative approval",
        ),
        ("event.review", "Review Event Request", "event", "Review pending event approval request"),
        ("event.approve", "Approve Event", "event", "Approve pending event request"),
        ("event.publish", "Publish Event", "event", "Publish approved event and open registration"),
        ("event.schedule", "Schedule Event", "event", "Configure event schedule and registration window"),
        ("event.cancel", "Cancel Event", "event", "Cancel published or scheduled event"),
        ("event.archive", "Archive Event", "event", "Archive completed or cancelled event"),
        (
            "event.participant.view",
            "View Event Participants",
            "event",
            "View unmasked event participant list",
        ),
        (
            "event.participant.manage",
            "Manage Event Participants",
            "event",
            "Manage event participant details",
        ),
        (
            "event.registration.view",
            "View Event Registrations",
            "event",
            "View event registration list and waitlist",
        ),
        (
            "event.registration.manage",
            "Manage Event Registrations",
            "event",
            "Manage event registrations and capacity",
        ),
        ("event.attendance.view", "View Event Attendance", "event", "View event attendance check-in records"),
        (
            "event.attendance.manage",
            "Record Event Attendance",
            "event",
            "Mark resident check-in, attendance, or no-show",
        ),
        (
            "event.facility.manage",
            "Manage Event Facility Booking",
            "event",
            "Configure facility association for event",
        ),
        (
            "event.attachment.manage",
            "Manage Event Attachments",
            "event",
            "Upload and manage event circulars and posters",
        ),
        (
            "event.audit.view",
            "View Event Audit History",
            "event",
            "View event status history and audit trail",
        ),
        # Committee, Meetings & Resolutions Governance Foundation (Phase 18)
        ("committee.view", "View Committee", "governance", "View committee profiles and member lists"),
        (
            "committee.manage",
            "Manage Committee",
            "governance",
            "Create, update, or archive committees and manage members",
        ),
        ("meeting.create", "Create Meeting Draft", "governance", "Create new meeting draft"),
        ("meeting.view", "View Meeting Details", "governance", "View meeting details, schedule, and agenda"),
        ("meeting.view_all", "View All Meetings", "governance", "View all society governance meetings"),
        (
            "meeting.update",
            "Update Meeting Details",
            "governance",
            "Modify meeting schedule, location, and agenda items",
        ),
        ("meeting.status.manage", "Manage Meeting Status", "governance", "Advance meeting lifecycle state"),
        (
            "quorum.manage",
            "Manage Meeting Quorum",
            "governance",
            "Record and calculate meeting quorum status",
        ),
        ("resolution.create", "Propose Resolution", "governance", "Propose resolution for meeting"),
        (
            "resolution.view",
            "View Resolution Details",
            "governance",
            "View resolution text, voting rules, and results",
        ),
        ("resolution.vote", "Cast Resolution Vote", "governance", "Cast vote on active resolution"),
        ("minutes.create", "Create Meeting Minutes", "governance", "Prepare meeting minutes draft"),
        (
            "minutes.approve",
            "Approve Meeting Minutes",
            "governance",
            "Approve and publish meeting minutes (maker-checker)",
        ),
        (
            "action_item.manage",
            "Manage Governance Action Items",
            "governance",
            "Create, assign, and update governance action items",
        ),
        # Emergency & Incident Management Foundation (Phase 19)
        (
            "incident.report",
            "Report Emergency Incident",
            "incident",
            "Report new emergency or security incident",
        ),
        ("incident.view_own", "View Own Incidents", "incident", "View incidents reported by user"),
        ("incident.view", "View Incidents", "incident", "View society incidents"),
        ("incident.view_all", "View All Incidents", "incident", "View all society emergency incidents"),
        ("incident.create", "Create Incident Record", "incident", "Create incident record directly"),
        (
            "incident.triage",
            "Triage Incident",
            "incident",
            "Perform operational triage and severity classification",
        ),
        (
            "incident.acknowledge",
            "Acknowledge Incident",
            "incident",
            "Acknowledge incident response assignment",
        ),
        (
            "incident.assign",
            "Assign Responder",
            "incident",
            "Assign staff, security, vendor, or committee responders",
        ),
        (
            "incident.respond",
            "Record Response Action",
            "incident",
            "Record containment and immediate field response",
        ),
        ("incident.escalate", "Escalate Incident", "incident", "Escalate incident level to higher authority"),
        ("incident.resolve", "Resolve Incident", "incident", "Mark incident resolved"),
        ("incident.close", "Close Incident", "incident", "Perform final incident closure"),
        (
            "incident.timeline.view",
            "View Incident Timeline",
            "incident",
            "View append-only incident operational log",
        ),
        (
            "incident.timeline.manage",
            "Manage Incident Timeline",
            "incident",
            "Add operational timeline entries",
        ),
        ("incident.action.view", "View Incident Actions", "incident", "View response task items"),
        ("incident.action.create", "Create Incident Action", "incident", "Create response task item"),
        ("incident.action.assign", "Assign Incident Action", "incident", "Assign response task item"),
        ("incident.action.update", "Update Incident Action", "incident", "Update response task item status"),
        ("incident.contact.view", "View Emergency Contacts", "incident", "View emergency contact directory"),
        (
            "incident.contact.manage",
            "Manage Emergency Contacts",
            "incident",
            "Create and update emergency contacts",
        ),
        (
            "incident.override",
            "Administrative Emergency Override",
            "incident",
            "Execute administrative status override",
        ),
        # Notifications & Communication Delivery Foundation (Phase 20)
        ("notification.view", "View Notifications", "notification", "View notification records and inbox"),
        ("notification.create", "Create Notification", "notification", "Create targeted notifications"),
        ("notification.manage", "Manage Notifications", "notification", "Manage notification lifecycle"),
        ("notification.send", "Send Broadcast Notification", "notification", "Send mass broadcast notifications"),
        ("notification.template.view", "View Templates", "notification", "View notification templates"),
        ("notification.template.manage", "Manage Templates", "notification", "Create and version templates"),
        ("notification.preference.view", "View Preferences", "notification", "View notification preferences"),
        ("notification.preference.manage", "Manage Preferences", "notification", "Update notification preferences"),
        ("notification.delivery.view", "View Deliveries", "notification", "View delivery logs and status"),
        ("notification.provider.view", "View Providers", "notification", "View communication providers"),
        ("notification.provider.manage", "Manage Providers", "notification", "Manage provider configurations"),
        ("notification.audit.view", "View Notification Audit", "notification", "View notification audit trail"),
    ]

    permission_map: dict[str, Permission] = {}
    for code, name, module, desc in permissions_data:
        perm_res = await session.execute(select(Permission).where(Permission.code == code))
        p = perm_res.scalar_one_or_none()
        if not p:
            p = Permission(code=code, name=name, module=module, description=desc)
            session.add(p)
            await session.flush()
        permission_map[code] = p

    logger.info("Seeded %d permissions.", len(permission_map))

    # 2. Roles
    roles_data = [
        (
            "SUPER_ADMIN",
            "Platform Super Administrator",
            "PLATFORM",
            True,
            [
                "platform.admin",
                "society.create",
                "society.read",
                "audit.read",
                "finance.read",
                "finance.account.manage",
                "finance.journal.create",
                "finance.journal.post",
                "finance.journal.reverse",
                "finance.expense.create",
                "finance.expense.approve",
                "finance.report.generate",
                "finance.period.close",
                "billing.config.manage",
                "billing.rule.manage",
                "billing.period.create",
                "billing.generate",
                "billing.review",
                "billing.approve",
                "billing.publish",
                "billing.adjust",
                "billing.credit_note",
                "billing.debit_note",
                "billing.payment.record",
                "billing.payment.allocate",
                "billing.receipt.view",
                "billing.reports.view",
                "billing.resident.view",
                "resident.profile.view",
                "resident.profile.update",
                "resident.create",
                "resident.update",
                "resident.occupancy.view",
                "resident.occupancy.create",
                "resident.occupancy.end",
                "resident.occupancy.history",
                "resident.owner.manage",
                "resident.family.manage",
                "resident.delegate.manage",
                "resident.contact.view",
                "resident.emergency.view",
                "vehicle.view",
                "vehicle.create",
                "vehicle.update",
                "vehicle.verify",
                "vehicle.deactivate",
                "vehicle.document.view",
                "vehicle.document.manage",
                "vehicle.access.view",
                "vehicle.access.record",
                "visitor.view",
                "visitor.create",
                "visitor.invite",
                "visitor.approve",
                "visitor.reject",
                "visitor.entry",
                "visitor.exit",
                "visitor.access.view",
                "visitor.manage",
                "visitor.emergency.override",
                "complaint.create",
                "complaint.view_own",
                "complaint.view_all",
                "complaint.comment",
                "complaint.comment_internal",
                "complaint.assign",
                "complaint.priority.manage",
                "complaint.status.manage",
                "complaint.sla.manage",
                "complaint.escalate",
                "complaint.resolve",
                "complaint.close",
                "complaint.reopen",
                "complaint.cancel",
                "complaint.category.manage",
                "complaint.attachment.manage",
                "complaint.audit.view",
                "vendor.create",
                "vendor.view",
                "vendor.view_sensitive",
                "vendor.update",
                "vendor.status.manage",
                "vendor.category.manage",
                "vendor.service.manage",
                "vendor.contact.manage",
                "vendor.document.manage",
                "vendor.document.view",
                "vendor.assignment.view",
                "vendor.assignment.manage",
                "vendor.audit.view",
                "vendor.archive",
                "facility.create",
                "facility.view",
                "facility.update",
                "facility.status.manage",
                "facility.area.manage",
                "facility.document.manage",
                "facility.document.view",
                "facility.audit.view",
                "facility.archive",
                "asset.create",
                "asset.view",
                "asset.view_sensitive",
                "asset.update",
                "asset.status.manage",
                "asset.category.manage",
                "asset.location.manage",
                "asset.assignment.manage",
                "asset.document.manage",
                "asset.document.view",
                "asset.maintenance.link",
                "asset.audit.view",
                "asset.archive",
                "facility.booking.create",
                "facility.booking.view",
                "facility.booking.view_own",
                "facility.booking.view_all",
                "facility.booking.update",
                "facility.booking.approve",
                "facility.booking.reject",
                "facility.booking.cancel",
                "facility.booking.override",
                "facility.booking.manage_rules",
                "facility.booking.manage_availability",
                "facility.booking.manage_blackout",
                "facility.booking.checkin",
                "facility.booking.complete",
                "facility.booking.no_show",
                "facility.booking.audit.view",
                "announcement.create",
                "announcement.view",
                "announcement.view_own",
                "announcement.view_all",
                "announcement.update",
                "announcement.submit",
                "announcement.review",
                "announcement.approve",
                "announcement.reject",
                "announcement.publish",
                "announcement.schedule",
                "announcement.archive",
                "announcement.expire",
                "announcement.audience.manage",
                "announcement.attachment.manage",
                "announcement.acknowledgement.view",
                "announcement.read_receipt.view",
                "announcement.audit.view",
            ],
        ),
        (
            "SOCIETY_ADMIN",
            "Society Administrator",
            "SOCIETY",
            True,
            [
                "society.read",
                "society.manage",
                "units.read",
                "units.manage",
                "occupancy.read",
                "occupancy.manage",
                "roles.assign",
                "audit.read",
                "finance.read",
                "finance.account.manage",
                "finance.journal.create",
                "finance.journal.post",
                "finance.journal.reverse",
                "finance.expense.create",
                "finance.expense.approve",
                "finance.report.generate",
                "finance.period.close",
                "billing.config.manage",
                "billing.rule.manage",
                "billing.period.create",
                "billing.generate",
                "billing.review",
                "billing.approve",
                "billing.publish",
                "billing.adjust",
                "billing.credit_note",
                "billing.debit_note",
                "billing.payment.record",
                "billing.payment.allocate",
                "billing.receipt.view",
                "billing.reports.view",
                "billing.resident.view",
                "resident.profile.view",
                "resident.profile.update",
                "resident.create",
                "resident.update",
                "resident.occupancy.view",
                "resident.occupancy.create",
                "resident.occupancy.end",
                "resident.occupancy.history",
                "resident.owner.manage",
                "resident.family.manage",
                "resident.delegate.manage",
                "resident.contact.view",
                "resident.emergency.view",
                "vehicle.view",
                "vehicle.create",
                "vehicle.update",
                "vehicle.verify",
                "vehicle.deactivate",
                "vehicle.document.view",
                "vehicle.document.manage",
                "vehicle.access.view",
                "vehicle.access.record",
                "visitor.view",
                "visitor.create",
                "visitor.invite",
                "visitor.approve",
                "visitor.reject",
                "visitor.entry",
                "visitor.exit",
                "visitor.access.view",
                "visitor.manage",
                "visitor.emergency.override",
                "complaint.create",
                "complaint.view_own",
                "complaint.view_all",
                "complaint.comment",
                "complaint.comment_internal",
                "complaint.assign",
                "complaint.priority.manage",
                "complaint.status.manage",
                "complaint.sla.manage",
                "complaint.escalate",
                "complaint.resolve",
                "complaint.close",
                "complaint.reopen",
                "complaint.cancel",
                "complaint.category.manage",
                "complaint.attachment.manage",
                "complaint.audit.view",
                "vendor.create",
                "vendor.view",
                "vendor.view_sensitive",
                "vendor.update",
                "vendor.status.manage",
                "vendor.category.manage",
                "vendor.service.manage",
                "vendor.contact.manage",
                "vendor.document.manage",
                "vendor.document.view",
                "vendor.assignment.view",
                "vendor.assignment.manage",
                "vendor.audit.view",
                "vendor.archive",
                "facility.create",
                "facility.view",
                "facility.update",
                "facility.status.manage",
                "facility.area.manage",
                "facility.document.manage",
                "facility.document.view",
                "facility.audit.view",
                "facility.archive",
                "asset.create",
                "asset.view",
                "asset.view_sensitive",
                "asset.update",
                "asset.status.manage",
                "asset.category.manage",
                "asset.location.manage",
                "asset.assignment.manage",
                "asset.document.manage",
                "asset.document.view",
                "asset.maintenance.link",
                "asset.audit.view",
                "asset.archive",
                "facility.booking.create",
                "facility.booking.view",
                "facility.booking.view_own",
                "facility.booking.view_all",
                "facility.booking.update",
                "facility.booking.approve",
                "facility.booking.reject",
                "facility.booking.cancel",
                "facility.booking.override",
                "facility.booking.manage_rules",
                "facility.booking.manage_availability",
                "facility.booking.manage_blackout",
                "facility.booking.checkin",
                "facility.booking.complete",
                "facility.booking.no_show",
                "facility.booking.audit.view",
                "announcement.create",
                "announcement.view",
                "announcement.view_own",
                "announcement.view_all",
                "announcement.update",
                "announcement.submit",
                "announcement.review",
                "announcement.approve",
                "announcement.reject",
                "announcement.publish",
                "announcement.schedule",
                "announcement.archive",
                "announcement.expire",
                "announcement.audience.manage",
                "announcement.attachment.manage",
                "announcement.acknowledgement.view",
                "announcement.read_receipt.view",
                "announcement.audit.view",
            ],
        ),
        (
            "SECRETARY",
            "Honorary Secretary",
            "SOCIETY",
            True,
            [
                "society.read",
                "society.manage",
                "units.read",
                "occupancy.read",
                "occupancy.manage",
                "audit.read",
                "finance.read",
                "finance.expense.create",
                "finance.expense.approve",
                "finance.report.generate",
                "billing.period.create",
                "billing.review",
                "billing.reports.view",
                "billing.receipt.view",
                "billing.resident.view",
                "resident.profile.view",
                "resident.profile.update",
                "resident.create",
                "resident.update",
                "resident.occupancy.view",
                "resident.occupancy.create",
                "resident.occupancy.end",
                "resident.occupancy.history",
                "resident.owner.manage",
                "resident.family.manage",
                "resident.delegate.manage",
                "resident.contact.view",
                "resident.emergency.view",
                "vehicle.view",
                "vehicle.create",
                "vehicle.update",
                "vehicle.verify",
                "vehicle.deactivate",
                "vehicle.document.view",
                "vehicle.document.manage",
                "vehicle.access.view",
                "vehicle.access.record",
                "complaint.create",
                "complaint.view_own",
                "complaint.view_all",
                "complaint.comment",
                "complaint.comment_internal",
                "complaint.assign",
                "complaint.priority.manage",
                "complaint.status.manage",
                "complaint.sla.manage",
                "complaint.escalate",
                "complaint.resolve",
                "complaint.close",
                "complaint.reopen",
                "complaint.cancel",
                "complaint.category.manage",
                "complaint.attachment.manage",
                "complaint.audit.view",
            ],
        ),
        (
            "TREASURER",
            "Honorary Treasurer",
            "SOCIETY",
            True,
            [
                "society.read",
                "units.read",
                "occupancy.read",
                "finance.read",
                "finance.account.manage",
                "finance.journal.create",
                "finance.journal.post",
                "finance.journal.reverse",
                "finance.expense.create",
                "finance.expense.approve",
                "finance.report.generate",
                "finance.period.close",
                "billing.config.manage",
                "billing.rule.manage",
                "billing.period.create",
                "billing.generate",
                "billing.review",
                "billing.approve",
                "billing.publish",
                "billing.adjust",
                "billing.credit_note",
                "billing.debit_note",
                "billing.payment.record",
                "billing.payment.allocate",
                "billing.receipt.view",
                "billing.reports.view",
                "billing.resident.view",
                "resident.profile.view",
                "resident.occupancy.view",
                "resident.occupancy.history",
                "resident.contact.view",
                "vehicle.view",
                "vehicle.document.view",
                "vehicle.access.view",
                "complaint.view_all",
                "complaint.create",
                "complaint.comment",
                "complaint.comment_internal",
                "complaint.status.manage",
                "complaint.resolve",
                "complaint.close",
            ],
        ),
        (
            "RESIDENT",
            "Resident / Owner",
            "SOCIETY",
            True,
            [
                "society.read",
                "units.read",
                "occupancy.read",
                "finance.read",
                "billing.resident.view",
                "resident.profile.view",
                "resident.profile.update",
                "resident.occupancy.view",
                "vehicle.view",
                "vehicle.create",
                "vehicle.update",
                "vehicle.document.view",
                "vehicle.document.manage",
                "visitor.view",
                "visitor.create",
                "visitor.invite",
                "visitor.approve",
                "visitor.reject",
                "complaint.create",
                "complaint.view_own",
                "complaint.comment",
                "complaint.reopen",
                "complaint.cancel",
                "complaint.attachment.manage",
                "facility.booking.create",
                "facility.booking.view",
                "facility.booking.view_own",
                "facility.booking.cancel",
                "announcement.view",
                "announcement.view_own",
            ],
        ),
        (
            "TENANT",
            "Tenant Occupant",
            "SOCIETY",
            True,
            [
                "society.read",
                "units.read",
                "billing.resident.view",
                "resident.profile.view",
                "resident.profile.update",
                "resident.occupancy.view",
                "vehicle.view",
                "vehicle.create",
                "vehicle.update",
                "vehicle.document.view",
                "vehicle.document.manage",
                "visitor.view",
                "visitor.create",
                "visitor.invite",
                "visitor.approve",
                "visitor.reject",
                "complaint.create",
                "complaint.view_own",
                "complaint.comment",
                "complaint.reopen",
                "complaint.cancel",
                "complaint.attachment.manage",
                "facility.booking.create",
                "facility.booking.view",
                "facility.booking.view_own",
                "facility.booking.cancel",
                "announcement.view",
                "announcement.view_own",
            ],
        ),
        (
            "SECURITY",
            "Gate Security Guard",
            "SOCIETY",
            True,
            [
                "society.read",
                "units.read",
                "vehicle.view",
                "vehicle.access.view",
                "vehicle.access.record",
                "visitor.view",
                "visitor.create",
                "visitor.entry",
                "visitor.exit",
                "visitor.access.view",
                "complaint.create",
                "complaint.view_own",
                "complaint.comment",
            ],
        ),
        (
            "COMMITTEE_MEMBER",
            "Managing Committee Member",
            "SOCIETY",
            True,
            [
                "society.read",
                "units.read",
                "occupancy.read",
                "complaint.view_all",
                "complaint.create",
                "complaint.comment",
                "complaint.comment_internal",
                "complaint.escalate",
                "finance.read",
                "resident.profile.view",
                "resident.occupancy.view",
                "resident.occupancy.history",
                "vehicle.view",
                "vehicle.document.view",
                "vehicle.access.view",
            ],
        ),
    ]

    role_map: dict[str, Role] = {}
    for code, name, scope, is_sys, perm_codes in roles_data:
        role_res = await session.execute(select(Role).where(Role.code == code, Role.scope_type == scope))
        r = role_res.scalar_one_or_none()
        if not r:
            r = Role(code=code, name=name, scope_type=scope, is_system_role=is_sys)
            session.add(r)
            await session.flush()

        for p_code in perm_codes:
            if p_code in permission_map:
                perm_id = permission_map[p_code].id
                rp_exists = await session.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == r.id,
                        RolePermission.permission_id == perm_id,
                    )
                )
                if not rp_exists.scalar_one_or_none():
                    session.add(RolePermission(role_id=r.id, permission_id=perm_id))
        role_map[code] = r

    logger.info("Seeded %d standard roles.", len(role_map))

    # 3. Global Users
    users_data = [
        (UUID_SUPER_ADMIN, "superadmin@societysphere.io", "+919999999000", "Super", "Admin", "Super Admin"),
        (UUID_USER_OWNER_A, "owner.a@palmstree.in", "+919876543210", "Vikram", "Mehta", "Vikram Mehta"),
        (UUID_USER_TENANT_A, "tenant.a@palmstree.in", "+919876543211", "Priya", "Nair", "Priya Nair"),
        (UUID_USER_DELEGATE_A, "delegate.a@palmstree.in", "+919876543212", "Rohan", "Mehta", "Rohan Mehta"),
        (UUID_USER_MEMBER_B, "member.b@greenwood.in", "+919876543220", "Anita", "Deshmukh", "Anita Deshmukh"),
    ]

    default_password_hash = hash_password("Password123!")
    user_map: dict[str, User] = {}
    for uid, email, phone, fname, lname, dname in users_data:
        user_res = await session.execute(select(User).where(User.id == uid))
        u = user_res.scalar_one_or_none()
        if not u:
            u = User(
                id=uid,
                email=email,
                phone=phone,
                password_hash=default_password_hash,
                first_name=fname,
                last_name=lname,
                display_name=dname,
                status="ACTIVE",
            )
            session.add(u)
            await session.flush()
        else:
            if not u.password_hash:
                u.password_hash = default_password_hash
        user_map[email] = u

    logger.info("Seeded %d global users.", len(user_map))

    # 4. Super Admin Role Assignment (Platform Scope)
    sa_res = await session.execute(
        select(RoleAssignment).where(
            RoleAssignment.user_id == UUID_SUPER_ADMIN,
            RoleAssignment.role_id == role_map["SUPER_ADMIN"].id,
            RoleAssignment.scope_type == "PLATFORM",
        )
    )
    if not sa_res.scalar_one_or_none():
        ra = RoleAssignment(
            user_id=UUID_SUPER_ADMIN,
            role_id=role_map["SUPER_ADMIN"].id,
            scope_type="PLATFORM",
            society_id=None,
        )
        session.add(ra)

    # 5. Society A (Palm Meadows CHS)
    soc_a_res = await session.execute(select(Society).where(Society.id == UUID_SOCIETY_A))
    society_a = soc_a_res.scalar_one_or_none()
    if not society_a:
        society_a = Society(
            id=UUID_SOCIETY_A,
            legal_name="Palm Meadows Cooperative Housing Society Ltd.",
            display_name="Palm Meadows CHS",
            registration_number="BOM/HSG/TC/12345/2020",
            address_line1="Plot 42, Sector 18, Vashi",
            city="Navi Mumbai",
            state="Maharashtra",
            country="IN",
            postal_code="400703",
            timezone="Asia/Kolkata",
            default_language="en",
            status="ACTIVE",
        )
        session.add(society_a)
        await session.flush()

    # 6. Society B (Greenwood Enclave)
    soc_b_res = await session.execute(select(Society).where(Society.id == UUID_SOCIETY_B))
    society_b = soc_b_res.scalar_one_or_none()
    if not society_b:
        society_b = Society(
            id=UUID_SOCIETY_B,
            legal_name="Greenwood Enclave Residents Welfare Association",
            display_name="Greenwood Enclave",
            registration_number="BLR/RWA/8899/2021",
            address_line1="100 Feet Road, Indiranagar",
            city="Bengaluru",
            state="Karnataka",
            country="IN",
            postal_code="560038",
            timezone="Asia/Kolkata",
            default_language="en",
            status="ACTIVE",
        )
        session.add(society_b)
        await session.flush()

    logger.info("Seeded Society A and Society B.")

    # 7. Physical Spatial Hierarchy for Society A (Block A, Floors 1-2, Units 101, 102, 201)
    blk_a_res = await session.execute(
        select(Block).where(Block.society_id == UUID_SOCIETY_A, Block.code == "BLK-A")
    )
    block_a = blk_a_res.scalar_one_or_none()
    if not block_a:
        block_a = Block(
            society_id=UUID_SOCIETY_A,
            code="BLK-A",
            display_name="Block A - Iris",
            sequence_order=1,
            status="ACTIVE",
        )
        session.add(block_a)
        await session.flush()

        # Floors
        floor_1 = Floor(
            society_id=UUID_SOCIETY_A,
            block_id=block_a.id,
            floor_number=1,
            display_name="First Floor",
            sequence_order=1,
            status="ACTIVE",
        )
        floor_2 = Floor(
            society_id=UUID_SOCIETY_A,
            block_id=block_a.id,
            floor_number=2,
            display_name="Second Floor",
            sequence_order=2,
            status="ACTIVE",
        )
        session.add_all([floor_1, floor_2])
        await session.flush()

        # Units
        unit_101 = Unit(
            society_id=UUID_SOCIETY_A,
            block_id=block_a.id,
            floor_id=floor_1.id,
            unit_number="101",
            unit_type="3BHK",
            carpet_area_sqft=1450.0,
            occupancy_status="OCCUPIED_OWNER",
            status="ACTIVE",
        )
        unit_102 = Unit(
            society_id=UUID_SOCIETY_A,
            block_id=block_a.id,
            floor_id=floor_1.id,
            unit_number="102",
            unit_type="2BHK",
            carpet_area_sqft=1100.0,
            occupancy_status="OCCUPIED_TENANT",
            status="ACTIVE",
        )
        unit_201 = Unit(
            society_id=UUID_SOCIETY_A,
            block_id=block_a.id,
            floor_id=floor_2.id,
            unit_number="201",
            unit_type="3BHK",
            carpet_area_sqft=1500.0,
            occupancy_status="OCCUPIED_OWNER",
            status="ACTIVE",
        )
        session.add_all([unit_101, unit_102, unit_201])
        await session.flush()

    # 8. Physical Spatial Hierarchy for Society B (Tower 1, Floor 1, Unit 101)
    blk_b_res = await session.execute(
        select(Block).where(Block.society_id == UUID_SOCIETY_B, Block.code == "TOW-1")
    )
    block_b = blk_b_res.scalar_one_or_none()
    if not block_b:
        block_b = Block(
            society_id=UUID_SOCIETY_B,
            code="TOW-1",
            display_name="Tower 1",
            sequence_order=1,
            status="ACTIVE",
        )
        session.add(block_b)
        await session.flush()

        floor_b1 = Floor(
            society_id=UUID_SOCIETY_B,
            block_id=block_b.id,
            floor_number=1,
            display_name="Ground Floor",
            sequence_order=1,
            status="ACTIVE",
        )
        session.add(floor_b1)
        await session.flush()

        unit_b101 = Unit(
            society_id=UUID_SOCIETY_B,
            block_id=block_b.id,
            floor_id=floor_b1.id,
            unit_number="101",
            unit_type="2BHK",
            carpet_area_sqft=1050.0,
            occupancy_status="OCCUPIED_OWNER",
            status="ACTIVE",
        )
        session.add(unit_b101)
        await session.flush()

    logger.info("Seeded spatial hierarchies for Society A and B.")

    # 9. Memberships & Occupancies in Society A
    # Owner Vikram in Society A
    mem_a_res = await session.execute(
        select(UserSocietyMembership).where(
            UserSocietyMembership.user_id == UUID_USER_OWNER_A,
            UserSocietyMembership.society_id == UUID_SOCIETY_A,
        )
    )
    if not mem_a_res.scalar_one_or_none():
        session.add(
            UserSocietyMembership(
                user_id=UUID_USER_OWNER_A,
                society_id=UUID_SOCIETY_A,
                membership_status="ACTIVE",
                joined_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
    ra_owner_a = await session.execute(
        select(RoleAssignment).where(
            RoleAssignment.user_id == UUID_USER_OWNER_A,
            RoleAssignment.society_id == UUID_SOCIETY_A,
            RoleAssignment.role_id == role_map["SOCIETY_ADMIN"].id,
        )
    )
    if not ra_owner_a.scalar_one_or_none():
        # Assign SOCIETY_ADMIN role to Vikram in Society A
        session.add(
            RoleAssignment(
                user_id=UUID_USER_OWNER_A,
                role_id=role_map["SOCIETY_ADMIN"].id,
                society_id=UUID_SOCIETY_A,
                scope_type="SOCIETY",
            )
        )
        # Resident Profile
        session.add(
            ResidentProfile(
                user_id=UUID_USER_OWNER_A,
                society_id=UUID_SOCIETY_A,
                emergency_contact_name="Sunita Mehta",
                emergency_contact_phone="+919876543299",
                accessibility_preferences={"easy_mode": False, "high_contrast": False},
                communication_preferences={"sms": True, "email": True, "push": True},
            )
        )

    # Tenant Priya in Society A
    mem_p_res = await session.execute(
        select(UserSocietyMembership).where(
            UserSocietyMembership.user_id == UUID_USER_TENANT_A,
            UserSocietyMembership.society_id == UUID_SOCIETY_A,
        )
    )
    if not mem_p_res.scalar_one_or_none():
        session.add(
            UserSocietyMembership(
                user_id=UUID_USER_TENANT_A,
                society_id=UUID_SOCIETY_A,
                membership_status="ACTIVE",
                joined_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        session.add(
            RoleAssignment(
                user_id=UUID_USER_TENANT_A,
                role_id=role_map["TENANT"].id,
                society_id=UUID_SOCIETY_A,
                scope_type="SOCIETY",
            )
        )
        session.add(
            ResidentProfile(
                user_id=UUID_USER_TENANT_A,
                society_id=UUID_SOCIETY_A,
                emergency_contact_name="Karan Nair",
                emergency_contact_phone="+919876543298",
                accessibility_preferences={"easy_mode": True, "font_size": "large"},
                communication_preferences={"sms": False, "email": True, "push": True},
            )
        )

    # 10. Occupancy links for Unit 101 & 102
    res_unit101 = await session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    u101 = res_unit101.scalar_one_or_none()
    if u101:
        res_occ = await session.execute(
            select(UnitOccupancy).where(
                UnitOccupancy.unit_id == u101.id,
                UnitOccupancy.user_id == UUID_USER_OWNER_A,
            )
        )
        if not res_occ.scalar_one_or_none():
            session.add(
                UnitOccupancy(
                    society_id=UUID_SOCIETY_A,
                    unit_id=u101.id,
                    user_id=UUID_USER_OWNER_A,
                    relationship_type="OWNER",
                    is_primary_contact=True,
                    valid_from=date(2021, 1, 1),
                    status="ACTIVE",
                )
            )

    res_unit102 = await session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "102")
    )
    u102 = res_unit102.scalar_one_or_none()
    if u102:
        res_occ_t = await session.execute(
            select(UnitOccupancy).where(
                UnitOccupancy.unit_id == u102.id,
                UnitOccupancy.user_id == UUID_USER_TENANT_A,
            )
        )
        if not res_occ_t.scalar_one_or_none():
            session.add(
                UnitOccupancy(
                    society_id=UUID_SOCIETY_A,
                    unit_id=u102.id,
                    user_id=UUID_USER_TENANT_A,
                    relationship_type="TENANT",
                    is_primary_contact=True,
                    valid_from=date(2022, 6, 1),
                    status="ACTIVE",
                )
            )
        res_occ_o = await session.execute(
            select(UnitOccupancy).where(
                UnitOccupancy.unit_id == u102.id,
                UnitOccupancy.user_id == UUID_USER_OWNER_A,
            )
        )
        if not res_occ_o.scalar_one_or_none():
            session.add(
                UnitOccupancy(
                    society_id=UUID_SOCIETY_A,
                    unit_id=u102.id,
                    user_id=UUID_USER_OWNER_A,
                    relationship_type="OWNER",
                    is_primary_contact=False,
                    valid_from=date(2020, 1, 1),
                    status="ACTIVE",
                )
            )

    res_unit201 = await session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "201")
    )
    u201 = res_unit201.scalar_one_or_none()
    if u201:
        res_occ201 = await session.execute(
            select(UnitOccupancy).where(
                UnitOccupancy.unit_id == u201.id,
                UnitOccupancy.user_id == UUID_USER_DELEGATE_A,
            )
        )
        if not res_occ201.scalar_one_or_none():
            session.add(
                UnitOccupancy(
                    society_id=UUID_SOCIETY_A,
                    unit_id=u201.id,
                    user_id=UUID_USER_DELEGATE_A,
                    relationship_type="OWNER",
                    is_primary_contact=True,
                    valid_from=date(2021, 1, 1),
                    status="ACTIVE",
                )
            )

        # Unit 201 Joint Co-ownership (60% Vikram, 40% Delegate A)
        res_own_co1 = await session.execute(
            select(UnitOwnership).where(
                UnitOwnership.unit_id == u201.id,
                UnitOwnership.user_id == UUID_USER_OWNER_A,
            )
        )
        if not res_own_co1.scalar_one_or_none():
            session.add(
                UnitOwnership(
                    id=uuid.uuid4(),
                    society_id=UUID_SOCIETY_A,
                    unit_id=u201.id,
                    user_id=UUID_USER_OWNER_A,
                    ownership_percentage=Decimal("60.00"),
                    start_date=date(2023, 1, 1),
                    is_primary=True,
                    status="ACTIVE",
                    notes="Primary co-owner (60% undivided share)",
                )
            )
        res_own_co2 = await session.execute(
            select(UnitOwnership).where(
                UnitOwnership.unit_id == u201.id,
                UnitOwnership.user_id == UUID_USER_DELEGATE_A,
            )
        )
        if not res_own_co2.scalar_one_or_none():
            session.add(
                UnitOwnership(
                    id=uuid.uuid4(),
                    society_id=UUID_SOCIETY_A,
                    unit_id=u201.id,
                    user_id=UUID_USER_DELEGATE_A,
                    ownership_percentage=Decimal("40.00"),
                    start_date=date(2023, 1, 1),
                    is_primary=False,
                    status="ACTIVE",
                    notes="Secondary co-owner (40% undivided share)",
                )
            )

    # 10.1 Phase 7: Unit Ownerships & Household Seeding (Units 101, 102, 201)
    if u101:
        # Unit 101 Owner
        res_own101 = await session.execute(
            select(UnitOwnership).where(
                UnitOwnership.unit_id == u101.id,
                UnitOwnership.user_id == UUID_USER_OWNER_A,
            )
        )
        if not res_own101.scalar_one_or_none():
            session.add(
                UnitOwnership(
                    id=uuid.uuid4(),
                    society_id=UUID_SOCIETY_A,
                    unit_id=u101.id,
                    user_id=UUID_USER_OWNER_A,
                    ownership_percentage=Decimal("100.00"),
                    start_date=date(2021, 1, 1),
                    is_primary=True,
                    status="ACTIVE",
                )
            )

        # Family Members in Unit 101
        res_fam_spouse = await session.execute(
            select(ResidentFamilyMember).where(
                ResidentFamilyMember.unit_id == u101.id,
                ResidentFamilyMember.name == "Sunita Mehta",
            )
        )
        if not res_fam_spouse.scalar_one_or_none():
            session.add(
                ResidentFamilyMember(
                    id=uuid.uuid4(),
                    society_id=UUID_SOCIETY_A,
                    unit_id=u101.id,
                    primary_resident_user_id=UUID_USER_OWNER_A,
                    name="Sunita Mehta",
                    relationship="SPOUSE",
                    phone="+919876543299",
                    email="sunita.mehta@example.com",
                    access_scope={"announcements": True, "emergency": True, "billing": False},
                    status="ACTIVE",
                )
            )

        res_fam_child = await session.execute(
            select(ResidentFamilyMember).where(
                ResidentFamilyMember.unit_id == u101.id,
                ResidentFamilyMember.name == "Aarav Mehta",
            )
        )
        if not res_fam_child.scalar_one_or_none():
            session.add(
                ResidentFamilyMember(
                    id=uuid.uuid4(),
                    society_id=UUID_SOCIETY_A,
                    unit_id=u101.id,
                    primary_resident_user_id=UUID_USER_OWNER_A,
                    name="Aarav Mehta",
                    relationship="CHILD",
                    access_scope={"announcements": True, "emergency": True, "billing": False},
                    status="ACTIVE",
                )
            )

        # Delegate for Unit 101
        res_del101 = await session.execute(
            select(ResidentDelegate).where(
                ResidentDelegate.unit_id == u101.id,
                ResidentDelegate.delegate_user_id == UUID_USER_DELEGATE_A,
            )
        )
        if not res_del101.scalar_one_or_none():
            session.add(
                ResidentDelegate(
                    id=uuid.uuid4(),
                    society_id=UUID_SOCIETY_A,
                    unit_id=u101.id,
                    delegator_user_id=UUID_USER_OWNER_A,
                    delegate_user_id=UUID_USER_DELEGATE_A,
                    permissions=["resident.view", "billing.view", "payment.view"],
                    valid_from=date(2024, 1, 1),
                    status="ACTIVE",
                    notes="Property representative for routine billing matters",
                )
            )

    if u102:
        # Unit 102 Owner
        res_own102 = await session.execute(
            select(UnitOwnership).where(
                UnitOwnership.unit_id == u102.id,
                UnitOwnership.user_id == UUID_USER_OWNER_A,
            )
        )
        if not res_own102.scalar_one_or_none():
            session.add(
                UnitOwnership(
                    id=uuid.uuid4(),
                    society_id=UUID_SOCIETY_A,
                    unit_id=u102.id,
                    user_id=UUID_USER_OWNER_A,
                    ownership_percentage=Decimal("100.00"),
                    start_date=date(2020, 1, 1),
                    is_primary=True,
                    status="ACTIVE",
                )
            )

        # Ended Historical Occupancy for Unit 102
        res_ended_occ = await session.execute(
            select(UnitOccupancy).where(
                UnitOccupancy.unit_id == u102.id,
                UnitOccupancy.status == "ENDED",
            )
        )
        if not res_ended_occ.scalar_one_or_none():
            session.add(
                UnitOccupancy(
                    id=uuid.uuid4(),
                    society_id=UUID_SOCIETY_A,
                    unit_id=u102.id,
                    user_id=UUID_USER_OWNER_A,
                    relationship_type="OWNER",
                    is_primary_contact=False,
                    valid_from=date(2020, 1, 1),
                    valid_to=date(2022, 5, 31),
                    status="ENDED",
                    notes="Moved to Unit 101; leased unit to tenant Priya",
                )
            )

    # 11. Membership & Occupancy in Society B (Anita)
    mem_b_res = await session.execute(
        select(UserSocietyMembership).where(
            UserSocietyMembership.user_id == UUID_USER_MEMBER_B,
            UserSocietyMembership.society_id == UUID_SOCIETY_B,
        )
    )
    if not mem_b_res.scalar_one_or_none():
        session.add(
            UserSocietyMembership(
                user_id=UUID_USER_MEMBER_B,
                society_id=UUID_SOCIETY_B,
                membership_status="ACTIVE",
                joined_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        session.add(
            RoleAssignment(
                user_id=UUID_USER_MEMBER_B,
                role_id=role_map["RESIDENT"].id,
                society_id=UUID_SOCIETY_B,
                scope_type="SOCIETY",
            )
        )
        session.add(
            RoleAssignment(
                user_id=UUID_USER_MEMBER_B,
                role_id=role_map["SOCIETY_ADMIN"].id,
                society_id=UUID_SOCIETY_B,
                scope_type="SOCIETY",
            )
        )

    # 12. Audit Log Entry for initial seed execution
    audit = AuditLog(
        society_id=UUID_SOCIETY_A,
        actor_user_id=UUID_SUPER_ADMIN,
        action="SYSTEM_SEED",
        entity_type="Society",
        entity_id=str(UUID_SOCIETY_A),
        before_state=None,
        after_state={"seeded_at": datetime.now(UTC).isoformat()},
        diff={"action": "INITIAL_SEED_COMPLETED"},
    )
    session.add(audit)

    # 13. Financial Core Seeding (Societies A & B)
    for soc_id, soc_name in [(UUID_SOCIETY_A, "Society A"), (UUID_SOCIETY_B, "Society B")]:
        # Accounting Config
        cfg_res = await session.execute(
            select(SocietyAccountingConfig).where(SocietyAccountingConfig.society_id == soc_id)
        )
        if not cfg_res.scalar_one_or_none():
            session.add(
                SocietyAccountingConfig(
                    society_id=soc_id,
                    accounting_mode="NATIVE",
                    authoritative_source="INTERNAL",
                )
            )

        # Financial Period FY 2026-2027
        per_res = await session.execute(
            select(FinancialPeriod).where(
                FinancialPeriod.society_id == soc_id,
                FinancialPeriod.fiscal_year == "2026-2027",
            )
        )
        period = per_res.scalar_one_or_none()
        if not period:
            period = FinancialPeriod(
                id=uuid.uuid4(),
                society_id=soc_id,
                name="FY 2026-2027",
                start_date=date(2026, 4, 1),
                end_date=date(2027, 3, 31),
                fiscal_year="2026-2027",
                status="OPEN",
                currency="INR",
            )
            session.add(period)
            await session.flush()

        # Standard Chart of Accounts
        coa_defs = [
            ("1000", "Cash on Hand", "ASSET", "DEBIT", "CASH"),
            ("1010", "Bank Operating Account", "ASSET", "DEBIT", "BANK"),
            ("1020", "Maintenance Receivables", "ASSET", "DEBIT", "RECEIVABLE"),
            ("2000", "Accounts Payable", "LIABILITY", "CREDIT", "PAYABLE"),
            ("3000", "General Reserve Fund", "EQUITY", "CREDIT", "RESERVE"),
            ("4000", "Maintenance Income", "INCOME", "CREDIT", "OPERATING"),
            ("5000", "Security Services Expense", "EXPENSE", "DEBIT", "OPERATING"),
            ("5010", "Common Electricity & Water", "EXPENSE", "DEBIT", "UTILITY"),
            ("5020", "Lift Maintenance & AMC", "EXPENSE", "DEBIT", "MAINTENANCE"),
        ]

        acc_map: dict[str, Account] = {}
        for code, name, acc_type, normal_bal, sub in coa_defs:
            acc_res = await session.execute(
                select(Account).where(Account.society_id == soc_id, Account.account_code == code)
            )
            acc = acc_res.scalar_one_or_none()
            if not acc:
                acc = Account(
                    id=uuid.uuid4(),
                    society_id=soc_id,
                    account_code=code,
                    account_name=name,
                    account_type=acc_type,
                    normal_balance=normal_bal,
                    sub_type=sub,
                    currency="INR",
                    is_active=True,
                )
                session.add(acc)
                await session.flush()
            acc_map[code] = acc

        # Seed initial balanced posted journal in Society A
        if soc_id == UUID_SOCIETY_A:
            jv_res = await session.execute(
                select(JournalEntry).where(
                    JournalEntry.society_id == UUID_SOCIETY_A,
                    JournalEntry.journal_number == "JV-000001",
                )
            )
            if not jv_res.scalar_one_or_none():
                initial_jv = JournalEntry(
                    id=uuid.uuid4(),
                    society_id=UUID_SOCIETY_A,
                    financial_period_id=period.id,
                    journal_number="JV-000001",
                    entry_date=date(2026, 4, 15),
                    description="Opening Maintenance Collections",
                    status="POSTED",
                    source_type="MANUAL",
                    total_debit=Decimal("50000.0000"),
                    total_credit=Decimal("50000.0000"),
                    currency="INR",
                    posted_at=datetime.now(UTC).replace(tzinfo=None),
                )
                session.add(initial_jv)
                await session.flush()

                line1 = JournalEntryLine(
                    id=uuid.uuid4(),
                    journal_entry_id=initial_jv.id,
                    society_id=UUID_SOCIETY_A,
                    account_id=acc_map["1010"].id,
                    line_number=1,
                    debit_amount=Decimal("50000.0000"),
                    credit_amount=Decimal("0.0000"),
                    description="Deposit to Bank Operating Account",
                )
                line2 = JournalEntryLine(
                    id=uuid.uuid4(),
                    journal_entry_id=initial_jv.id,
                    society_id=UUID_SOCIETY_A,
                    account_id=acc_map["4000"].id,
                    line_number=2,
                    debit_amount=Decimal("0.0000"),
                    credit_amount=Decimal("50000.0000"),
                    description="Maintenance Income recognized",
                )
                session.add_all([line1, line2])

        # Seed Maintenance Billing Configuration
        bill_cfg_res = await session.execute(
            select(SocietyBillingConfig).where(SocietyBillingConfig.society_id == soc_id)
        )
        if not bill_cfg_res.scalar_one_or_none():
            bill_cfg = SocietyBillingConfig(
                id=uuid.uuid4(),
                society_id=soc_id,
                receivable_account_id=acc_map["1020"].id,
                income_account_id=acc_map["4000"].id,
                bank_account_id=acc_map["1010"].id,
                currency="INR",
                billing_frequency="MONTHLY",
                billing_day=1,
                default_due_days=15,
                late_fee_enabled=True,
                late_fee_type="PERCENTAGE",
                late_fee_rate=Decimal("2.0000"),
                grace_period_days=5,
                default_responsibility="OWNER",
                approval_required=True,
            )
            session.add(bill_cfg)

        # Seed Standard Maintenance Charge Rule
        rule_res = await session.execute(
            select(MaintenanceChargeRule).where(
                MaintenanceChargeRule.society_id == soc_id,
                MaintenanceChargeRule.code == "MAINT_FIXED",
            )
        )
        charge_rule = rule_res.scalar_one_or_none()
        if not charge_rule:
            charge_rule = MaintenanceChargeRule(
                id=uuid.uuid4(),
                society_id=soc_id,
                name="Standard Flat Maintenance",
                code="MAINT_FIXED",
                calculation_type="FIXED_PER_UNIT",
                rate_or_amount=Decimal("3000.0000"),
                income_account_id=acc_map["4000"].id,
                effective_from=date(2026, 4, 1),
                is_active=True,
            )
            session.add(charge_rule)
            await session.flush()

        # Seed Operational Billing Period
        bp_res = await session.execute(
            select(BillingPeriod).where(
                BillingPeriod.society_id == soc_id,
                BillingPeriod.period_code == "BP-2026-04",
            )
        )
        billing_period = bp_res.scalar_one_or_none()
        if not billing_period:
            billing_period = BillingPeriod(
                id=uuid.uuid4(),
                society_id=soc_id,
                financial_period_id=period.id,
                period_code="BP-2026-04",
                name="April 2026 Maintenance Billing",
                start_date=date(2026, 4, 1),
                end_date=date(2026, 4, 30),
                billing_date=date(2026, 4, 1),
                due_date=date(2026, 4, 15),
                status="PUBLISHED",
                published_at=datetime.now(UTC),
            )
            session.add(billing_period)
            await session.flush()

        # Seed Invoices, Payment, and Receipt in Society A
        if soc_id == UUID_SOCIETY_A:
            # Query unit A-101
            u101_res = await session.execute(
                select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
            )
            target_unit_101 = u101_res.scalars().first()

            u102_res = await session.execute(
                select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "102")
            )
            target_unit_102 = u102_res.scalars().first()

            if target_unit_101:
                inv1_res = await session.execute(
                    select(Invoice).where(
                        Invoice.society_id == UUID_SOCIETY_A,
                        Invoice.invoice_number == "INV-000001",
                    )
                )
                if not inv1_res.scalar_one_or_none():
                    inv1 = Invoice(
                        id=uuid.uuid4(),
                        society_id=UUID_SOCIETY_A,
                        billing_period_id=billing_period.id,
                        unit_id=target_unit_101.id,
                        responsible_user_id=UUID_USER_OWNER_A,
                        invoice_number="INV-000001",
                        invoice_date=date(2026, 4, 1),
                        due_date=date(2026, 4, 15),
                        subtotal=Decimal("3000.0000"),
                        grand_total=Decimal("3000.0000"),
                        paid_amount=Decimal("3000.0000"),
                        outstanding_amount=Decimal("0.0000"),
                        status="PAID",
                        currency="INR",
                        accounting_status="POSTED",
                        published_at=datetime.now(UTC),
                    )
                    session.add(inv1)
                    await session.flush()

                    inv1_line = InvoiceLine(
                        id=uuid.uuid4(),
                        society_id=UUID_SOCIETY_A,
                        invoice_id=inv1.id,
                        charge_rule_id=charge_rule.id,
                        line_number=1,
                        description="Standard Flat Maintenance (MAINT_FIXED)",
                        quantity=Decimal("1.0000"),
                        unit_rate=Decimal("3000.0000"),
                        amount=Decimal("3000.0000"),
                        accounting_account_id=acc_map["4000"].id,
                    )
                    session.add(inv1_line)

                    # Seed payment, allocation, and receipt
                    pay1 = Payment(
                        id=uuid.uuid4(),
                        society_id=UUID_SOCIETY_A,
                        payer_user_id=UUID_USER_OWNER_A,
                        unit_id=target_unit_101.id,
                        amount=Decimal("3000.0000"),
                        currency="INR",
                        payment_date=date(2026, 4, 5),
                        payment_method="BANK_TRANSFER",
                        reference_number="TXN-20260405-001",
                        status="ALLOCATED",
                        allocated_amount=Decimal("3000.0000"),
                        unallocated_amount=Decimal("0.0000"),
                    )
                    session.add(pay1)
                    await session.flush()

                    alloc1 = PaymentAllocation(
                        id=uuid.uuid4(),
                        society_id=UUID_SOCIETY_A,
                        payment_id=pay1.id,
                        invoice_id=inv1.id,
                        amount=Decimal("3000.0000"),
                        allocated_at=datetime.now(UTC),
                    )
                    session.add(alloc1)

                    rec1 = Receipt(
                        id=uuid.uuid4(),
                        society_id=UUID_SOCIETY_A,
                        payment_id=pay1.id,
                        receipt_number="REC-000001",
                        receipt_date=date(2026, 4, 5),
                        amount=Decimal("3000.0000"),
                        payer_user_id=UUID_USER_OWNER_A,
                        unit_id=target_unit_101.id,
                    )
                    session.add(rec1)

            if target_unit_102:
                inv2_res = await session.execute(
                    select(Invoice).where(
                        Invoice.society_id == UUID_SOCIETY_A,
                        Invoice.invoice_number == "INV-000002",
                    )
                )
                if not inv2_res.scalar_one_or_none():
                    inv2 = Invoice(
                        id=uuid.uuid4(),
                        society_id=UUID_SOCIETY_A,
                        billing_period_id=billing_period.id,
                        unit_id=target_unit_102.id,
                        responsible_user_id=UUID_USER_TENANT_A,
                        invoice_number="INV-000002",
                        invoice_date=date(2026, 4, 1),
                        due_date=date(2026, 4, 15),
                        subtotal=Decimal("3000.0000"),
                        grand_total=Decimal("3000.0000"),
                        paid_amount=Decimal("0.0000"),
                        outstanding_amount=Decimal("3000.0000"),
                        status="PUBLISHED",
                        currency="INR",
                        accounting_status="POSTED",
                        published_at=datetime.now(UTC),
                    )
                    session.add(inv2)
                    await session.flush()

                    inv2_line = InvoiceLine(
                        id=uuid.uuid4(),
                        society_id=UUID_SOCIETY_A,
                        invoice_id=inv2.id,
                        charge_rule_id=charge_rule.id,
                        line_number=1,
                        description="Standard Flat Maintenance (MAINT_FIXED)",
                        quantity=Decimal("1.0000"),
                        unit_rate=Decimal("3000.0000"),
                        amount=Decimal("3000.0000"),
                        accounting_account_id=acc_map["4000"].id,
                    )
                    session.add(inv2_line)

                    # Seed sample Bank Reconciliation Session for April 2026
                    bank_acc_a = acc_map.get("1010")
                    if bank_acc_a:
                        recon_sess = ReconciliationSession(
                            id=uuid.uuid4(),
                            society_id=UUID_SOCIETY_A,
                            session_number="REC-SESS-0001",
                            account_id=bank_acc_a.id,
                            statement_reference="STMT-202604-001",
                            statement_start_date=date(2026, 4, 1),
                            statement_end_date=date(2026, 4, 30),
                            opening_balance=Decimal("100000.0000"),
                            closing_balance=Decimal("103000.0000"),
                            reconciled_amount=Decimal("3000.0000"),
                            unreconciled_amount=Decimal("0.0000"),
                            status="RECONCILED",
                            notes="April 2026 Monthly Bank Reconciliation",
                            created_by=UUID_USER_OWNER_A,
                        )
                        session.add(recon_sess)
                        await session.flush()

                        recon_item = ReconciliationItem(
                            id=uuid.uuid4(),
                            society_id=UUID_SOCIETY_A,
                            session_id=recon_sess.id,
                            payment_id=pay1.id,
                            transaction_date=date(2026, 4, 5),
                            reference_number="TXN-20260405-001",
                            description="Maintenance payment received - Flat 101",
                            statement_amount=Decimal("3000.0000"),
                            recorded_amount=Decimal("3000.0000"),
                            discrepancy_amount=Decimal("0.0000"),
                            match_status="MATCHED",
                            matched_at=datetime.now(UTC),
                            matched_by=UUID_USER_OWNER_A,
                        )
                        session.add(recon_item)

    # 12. Seed sample vehicles for Society A (Flat 101, Vikram Mehta)
    unit_101_res = await session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101_obj = unit_101_res.scalar_one_or_none()
    if unit_101_obj:
        v1_res = await session.execute(
            select(Vehicle).where(
                Vehicle.society_id == UUID_SOCIETY_A,
                Vehicle.normalized_registration_number == "MH02EV1001",
            )
        )
        if not v1_res.scalar_one_or_none():
            veh_ev = Vehicle(
                id=uuid.uuid4(),
                society_id=UUID_SOCIETY_A,
                registration_number="MH 02 EV 1001",
                normalized_registration_number="MH02EV1001",
                vehicle_type="FOUR_WHEELER",
                make="Tata",
                model="Nexon EV",
                variant="Empowered Plus",
                color="Teal Blue",
                fuel_type="ELECTRIC",
                is_ev=True,
                battery_capacity_kwh=Decimal("40.50"),
                charging_required=True,
                status="ACTIVE",
                verification_status="VERIFIED",
                notes="Primary electric family car",
                created_by=UUID_USER_OWNER_A,
            )
            session.add(veh_ev)
            await session.flush()

            # Association
            assoc1 = VehicleResidentAssociation(
                id=uuid.uuid4(),
                society_id=UUID_SOCIETY_A,
                vehicle_id=veh_ev.id,
                user_id=UUID_USER_OWNER_A,
                unit_id=unit_101_obj.id,
                association_type="OWNER",
                is_primary=True,
                valid_from=date(2026, 1, 1),
                status="ACTIVE",
            )
            session.add(assoc1)

            # Verification
            verif1 = VehicleVerification(
                id=uuid.uuid4(),
                society_id=UUID_SOCIETY_A,
                vehicle_id=veh_ev.id,
                verifier_user_id=UUID_SUPER_ADMIN,
                verification_status="VERIFIED",
                verification_date=date(2026, 1, 2),
                reason="RC smartcard verified",
            )
            session.add(verif1)

            # Parking association
            park1 = VehicleParkingAssociation(
                id=uuid.uuid4(),
                society_id=UUID_SOCIETY_A,
                vehicle_id=veh_ev.id,
                parking_slot_number="P-101",
                valid_from=date(2026, 1, 1),
                status="ACTIVE",
            )
            session.add(park1)

            # Document
            doc1 = VehicleDocument(
                id=uuid.uuid4(),
                society_id=UUID_SOCIETY_A,
                vehicle_id=veh_ev.id,
                document_type="RC",
                document_number="MH02-2024-0019283",
                file_key="vehicles/society-a/rc-mh02ev1001.pdf",
                file_name="rc_smartcard.pdf",
                file_size_bytes=245000,
                content_type="application/pdf",
                valid_from=date(2024, 1, 1),
                uploaded_by=UUID_USER_OWNER_A,
            )
            session.add(doc1)

            # Access records
            acc_entry = VehicleAccessRecord(
                id=uuid.uuid4(),
                society_id=UUID_SOCIETY_A,
                vehicle_id=veh_ev.id,
                registration_number_snapshot="MH 02 EV 1001",
                normalized_registration_number_snapshot="MH02EV1001",
                access_type="ENTRY",
                gate_identifier="GATE-MAIN-01",
                access_time=datetime(2026, 10, 1, 9, 30),
                detection_method="MANUAL",
                source_provider="MANUAL",
                notes="Resident entry authorized",
            )
            session.add(acc_entry)

        # Vehicle 2: Two Wheeler
        v2_res = await session.execute(
            select(Vehicle).where(
                Vehicle.society_id == UUID_SOCIETY_A,
                Vehicle.normalized_registration_number == "MH02AB2002",
            )
        )
        if not v2_res.scalar_one_or_none():
            veh_2w = Vehicle(
                id=uuid.uuid4(),
                society_id=UUID_SOCIETY_A,
                registration_number="MH 02 AB 2002",
                normalized_registration_number="MH02AB2002",
                vehicle_type="TWO_WHEELER",
                make="Honda",
                model="Activa 6G",
                color="Pearl White",
                fuel_type="PETROL",
                is_ev=False,
                status="ACTIVE",
                verification_status="VERIFIED",
                notes="Secondary two-wheeler",
                created_by=UUID_USER_OWNER_A,
            )
            session.add(veh_2w)
            await session.flush()

            assoc2 = VehicleResidentAssociation(
                id=uuid.uuid4(),
                society_id=UUID_SOCIETY_A,
                vehicle_id=veh_2w.id,
                user_id=UUID_USER_OWNER_A,
                unit_id=unit_101_obj.id,
                association_type="OWNER",
                is_primary=False,
                valid_from=date(2026, 1, 1),
                status="ACTIVE",
            )
            session.add(assoc2)

    # 13. Seed Complaints & Helpdesk Foundation (Phase 10)
    cat_plumbing_res = await session.execute(
        select(ComplaintCategory).where(
            ComplaintCategory.society_id == UUID_SOCIETY_A,
            ComplaintCategory.code == "PLUMBING",
        )
    )
    cat_plumbing = cat_plumbing_res.scalar_one_or_none()
    if not cat_plumbing:
        cat_plumbing = ComplaintCategory(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            name="Plumbing",
            code="PLUMBING",
            description="Water leakage, pipe repair, and plumbing issues",
            is_active=True,
            display_order=1,
        )
        session.add(cat_plumbing)
        await session.flush()

        sub_leak = ComplaintSubcategory(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            category_id=cat_plumbing.id,
            name="Pipe Leakage",
            code="PIPE_LEAKAGE",
            description="Active water leakage from pipes or joints",
            is_active=True,
            display_order=1,
        )
        session.add(sub_leak)

        sub_tap = ComplaintSubcategory(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            category_id=cat_plumbing.id,
            name="Tap & Fitting Repair",
            code="TAP_REPAIR",
            description="Broken taps, flush valves or mixer fittings",
            is_active=True,
            display_order=2,
        )
        session.add(sub_tap)

    cat_elec_res = await session.execute(
        select(ComplaintCategory).where(
            ComplaintCategory.society_id == UUID_SOCIETY_A,
            ComplaintCategory.code == "ELECTRICAL",
        )
    )
    cat_elec = cat_elec_res.scalar_one_or_none()
    if not cat_elec:
        cat_elec = ComplaintCategory(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            name="Electrical",
            code="ELECTRICAL",
            description="Power outage, wiring issues, common light faults",
            is_active=True,
            display_order=2,
        )
        session.add(cat_elec)
        await session.flush()

        sub_power = ComplaintSubcategory(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            category_id=cat_elec.id,
            name="Power Outage",
            code="POWER_OUTAGE",
            description="Main line fault or phase failure",
            is_active=True,
            display_order=1,
        )
        session.add(sub_power)

    # Society B Category
    cat_socb_res = await session.execute(
        select(ComplaintCategory).where(
            ComplaintCategory.society_id == UUID_SOCIETY_B,
            ComplaintCategory.code == "GENERAL",
        )
    )
    if not cat_socb_res.scalar_one_or_none():
        session.add(
            ComplaintCategory(
                id=uuid.uuid4(),
                society_id=UUID_SOCIETY_B,
                name="General Maintenance",
                code="GENERAL",
                description="General society maintenance and issues",
                is_active=True,
                display_order=1,
            )
        )

    # SLA Policies
    sla_res = await session.execute(
        select(ComplaintSLAPolicy).where(
            ComplaintSLAPolicy.society_id == UUID_SOCIETY_A,
            ComplaintSLAPolicy.priority == "CRITICAL",
        )
    )
    if not sla_res.scalar_one_or_none():
        sla_crit = ComplaintSLAPolicy(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            priority="CRITICAL",
            acknowledgement_target_hours=1,
            resolution_target_hours=4,
            is_active=True,
        )
        sla_high = ComplaintSLAPolicy(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            priority="HIGH",
            acknowledgement_target_hours=4,
            resolution_target_hours=12,
            is_active=True,
        )
        sla_med = ComplaintSLAPolicy(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            priority="MEDIUM",
            acknowledgement_target_hours=12,
            resolution_target_hours=48,
            is_active=True,
        )
        sla_low = ComplaintSLAPolicy(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            priority="LOW",
            acknowledgement_target_hours=24,
            resolution_target_hours=96,
            is_active=True,
        )
        session.add_all([sla_crit, sla_high, sla_med, sla_low])

    # Sample Complaint 1
    cmp1_res = await session.execute(
        select(Complaint).where(
            Complaint.society_id == UUID_SOCIETY_A,
            Complaint.complaint_number == "CMP-2026-000001",
        )
    )
    if not cmp1_res.scalar_one_or_none() and unit_101_obj and cat_plumbing:
        sub_res = await session.execute(
            select(ComplaintSubcategory).where(
                ComplaintSubcategory.society_id == UUID_SOCIETY_A,
                ComplaintSubcategory.code == "PIPE_LEAKAGE",
            )
        )
        sub_obj = sub_res.scalar_one_or_none()
        cmp1 = Complaint(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            complaint_number="CMP-2026-000001",
            category_id=cat_plumbing.id,
            subcategory_id=sub_obj.id if sub_obj else None,
            raised_for_unit_id=unit_101_obj.id,
            raised_by_user_id=UUID_USER_OWNER_A,
            title="Severe main pipe leak in Flat 101 bathroom",
            description="Water leaking heavily from vertical supply pipe behind bathroom tile.",
            priority="HIGH",
            status="IN_PROGRESS",
            source="WEB",
            ack_due_at=datetime(2026, 10, 1, 14, 0),
            due_at=datetime(2026, 10, 1, 22, 0),
            acknowledged_at=datetime(2026, 10, 1, 10, 30),
        )
        session.add(cmp1)
        await session.flush()

        hist1 = ComplaintStatusHistory(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            complaint_id=cmp1.id,
            from_status="OPEN",
            to_status="IN_PROGRESS",
            actor_user_id=UUID_SUPER_ADMIN,
            reason="Plumber assigned and en route",
        )
        session.add(hist1)

        assign1 = ComplaintAssignment(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            complaint_id=cmp1.id,
            assigned_to_user_id=UUID_SUPER_ADMIN,
            assigned_by_user_id=UUID_SUPER_ADMIN,
            assigned_at=datetime(2026, 10, 1, 10, 30),
            notes="Assigned to lead maintenance engineer",
        )
        session.add(assign1)

        comment1 = ComplaintComment(
            id=uuid.uuid4(),
            society_id=UUID_SOCIETY_A,
            complaint_id=cmp1.id,
            author_user_id=UUID_SUPER_ADMIN,
            body="Plumber will visit at 11:00 AM to isolate the valve.",
            comment_type="PUBLIC",
        )
        session.add(comment1)

    await session.commit()
    logger.info("Database seeding completed successfully (including Vehicles, Access & Complaints).")


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, autoflush=False, expire_on_commit=False
    )
    async with session_factory() as session:
        try:
            await seed_data(session)
        except Exception as exc:
            logger.error(f"Seeding failed: {exc}")
            await session.rollback()
            sys.exit(1)
        finally:
            await session.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
