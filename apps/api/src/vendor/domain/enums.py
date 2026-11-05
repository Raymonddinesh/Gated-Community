"""Vendor & Service Provider Management Domain Enums."""

from enum import StrEnum


class VendorType(StrEnum):
    INDIVIDUAL = "INDIVIDUAL"
    COMPANY = "COMPANY"
    AGENCY = "AGENCY"
    SERVICE_PROVIDER = "SERVICE_PROVIDER"
    CONTRACTOR = "CONTRACTOR"
    OTHER = "OTHER"


class VendorStatus(StrEnum):
    ONBOARDING = "ONBOARDING"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    BLACKLISTED = "BLACKLISTED"
    OFFBOARDED = "OFFBOARDED"


class VendorAssocStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"


class PreferredContactMethod(StrEnum):
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"


class VendorDocumentType(StrEnum):
    REGISTRATION = "REGISTRATION"
    CERTIFICATE = "CERTIFICATE"
    INSURANCE = "INSURANCE"
    LICENSE = "LICENSE"
    QUALIFICATION = "QUALIFICATION"
    COMPLIANCE = "COMPLIANCE"
    OTHER = "OTHER"


class VendorAssignmentEventType(StrEnum):
    ASSIGNED = "ASSIGNED"
    REASSIGNED = "REASSIGNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
