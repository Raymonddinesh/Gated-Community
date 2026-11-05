"""Phase 20 Notifications Domain Exceptions."""


class NotificationDomainError(Exception):
    """Base Domain Exception for Notifications."""

    pass


class NotificationNotFoundError(NotificationDomainError):
    """Raised when a requested notification is not found."""

    pass


class RecipientNotFoundError(NotificationDomainError):
    """Raised when a recipient record is not found."""

    pass


class TemplateNotFoundError(NotificationDomainError):
    """Raised when a requested notification template is not found."""

    pass


class TemplateVersionNotFoundError(NotificationDomainError):
    """Raised when a specified template version is not found."""

    pass


class TemplateRenderError(NotificationDomainError):
    """Raised when rendering a template fails or variable is not allowlisted."""

    pass


class InvalidNotificationStateError(NotificationDomainError):
    """Raised when an invalid state transition is requested."""

    pass


class DuplicateNotificationError(NotificationDomainError):
    """Raised when an idempotency key conflict occurs."""

    pass


class ProviderDeliveryError(NotificationDomainError):
    """Raised when a provider delivery fails."""

    pass


class MaxRetriesExceededError(NotificationDomainError):
    """Raised when delivery retries exceed max_attempts."""

    pass


class RecipientSuppressedError(NotificationDomainError):
    """Raised when recipient preferences suppress notification delivery."""

    pass
