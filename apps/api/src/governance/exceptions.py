"""Phase 18 Governance Domain Exceptions."""


class GovernanceError(Exception):
    """Base exception for Governance domain."""

    def __init__(self, message: str, code: str = "GOVERNANCE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class GovernanceNotFoundError(GovernanceError):
    def __init__(self, message: str = "Governance entity not found", code: str = "GOVERNANCE_NOT_FOUND"):
        super().__init__(message, code=code)


class CommitteeNotFoundError(GovernanceNotFoundError):
    def __init__(self, message: str = "Committee not found"):
        super().__init__(message, code="COMMITTEE_NOT_FOUND")


class MeetingNotFoundError(GovernanceNotFoundError):
    def __init__(self, message: str = "Meeting not found"):
        super().__init__(message, code="MEETING_NOT_FOUND")


class ResolutionNotFoundError(GovernanceNotFoundError):
    def __init__(self, message: str = "Resolution not found"):
        super().__init__(message, code="RESOLUTION_NOT_FOUND")


class InvalidGovernanceStateError(GovernanceError):
    def __init__(self, message: str = "Invalid governance state transition"):
        super().__init__(message, code="INVALID_GOVERNANCE_STATE")


class QuorumNotAchievedError(GovernanceError):
    def __init__(self, message: str = "Meeting quorum was not achieved"):
        super().__init__(message, code="QUORUM_NOT_ACHIEVED")


class DuplicateVoteError(GovernanceError):
    def __init__(self, message: str = "User has already cast a vote for this resolution"):
        super().__init__(message, code="DUPLICATE_VOTE")


class VoteClosedError(GovernanceError):
    def __init__(self, message: str = "Voting is closed for this resolution"):
        super().__init__(message, code="VOTE_CLOSED")


class MinutesNotApprovedError(GovernanceError):
    def __init__(self, message: str = "Meeting minutes must be approved before publication"):
        super().__init__(message, code="MINUTES_NOT_APPROVED")


class MakerCheckerViolationError(GovernanceError):
    def __init__(self, message: str = "Author cannot approve their own minutes draft"):
        super().__init__(message, code="MAKER_CHECKER_VIOLATION")


class CrossTenantGovernanceError(GovernanceError):
    def __init__(self, message: str = "Cross-tenant governance operation forbidden"):
        super().__init__(message, code="CROSS_TENANT_GOVERNANCE_ERROR")
