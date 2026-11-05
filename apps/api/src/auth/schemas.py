"""Pydantic v2 Request and Response Schemas for Authentication and RBAC."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None = None
    phone: str | None = None
    first_name: str
    last_name: str
    display_name: str
    status: str


class SocietyOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    legal_name: str
    display_name: str


class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Email address or phone number")
    password: str = Field(..., description="Plaintext password")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    user: UserSummary
    active_society_id: UUID | None = None
    available_societies: list[SocietyOption] = Field(default_factory=list)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Opaque refresh token")


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str


class PasswordResetRequest(BaseModel):
    identifier: str = Field(..., description="Registered email or phone")


class PasswordResetResponse(BaseModel):
    message: str
    reset_token: str | None = Field(
        default=None, description="Provided strictly in non-production environments for verification"
    )


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., description="Password reset verification token")
    new_password: str = Field(..., description="New password meeting security policy")


class SocietySwitchResponse(BaseModel):
    society_id: UUID
    display_name: str
    roles: list[str]
    permissions: list[str]


class UserMeResponse(BaseModel):
    user: UserSummary
    memberships: list[SocietyOption]
    active_society_id: UUID | None = None
    active_roles: list[str] = Field(default_factory=list)
    active_permissions: list[str] = Field(default_factory=list)


class RoleAssignmentRequest(BaseModel):
    user_id: UUID
    role_code: str = Field(..., description="System role code (e.g. RESIDENT, SECRETARY)")


class CreateMembershipRequest(BaseModel):
    user_id: UUID
    membership_status: str = Field(default="ACTIVE", description="Initial membership status")


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    society_id: UUID
    membership_status: str


class RoleAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    role_code: str
    society_id: UUID | None
    status: str


class GenericActionResponse(BaseModel):
    success: bool = True
    message: str
