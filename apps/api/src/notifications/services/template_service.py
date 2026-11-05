"""Phase 20 Template & Localization Service with Variable Security."""

import html
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.notifications import (
    NotificationTemplate,
    NotificationTemplateVersion,
)
from apps.api.src.notifications.exceptions import (
    TemplateNotFoundError,
    TemplateRenderError,
)
from apps.api.src.notifications.repositories import TemplateRepository


class TemplateService:
    """Service for Versioned Template Management and Secure Variable Rendering."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TemplateRepository(db)

    async def create_template(
        self,
        society_id: uuid.UUID | None,
        code: str,
        name: str,
        category: str,
        description: str | None = None,
        allowlisted_variables: list[str] | None = None,
    ) -> NotificationTemplate:
        vars_str = ",".join(allowlisted_variables) if allowlisted_variables else None
        template = NotificationTemplate(
            society_id=society_id,
            code=code,
            name=name,
            category=category,
            description=description,
            is_active=True,
            allowlisted_variables=vars_str,
        )
        return await self.repo.create_template(template)

    async def create_version(
        self,
        society_id: uuid.UUID | None,
        template_id: uuid.UUID,
        channel: str,
        locale: str,
        version: int,
        subject_template: str | None,
        body_template: str,
        is_published: bool = True,
    ) -> NotificationTemplateVersion:
        version_obj = NotificationTemplateVersion(
            society_id=society_id,
            template_id=template_id,
            channel=channel,
            locale=locale,
            version=version,
            subject_template=subject_template,
            body_template=body_template,
            is_published=is_published,
        )
        return await self.repo.create_version(version_obj)

    async def render_template(
        self,
        society_id: uuid.UUID | None,
        template_code: str,
        channel: str,
        locale: str = "en",
        variables: dict[str, str] | None = None,
    ) -> tuple[str | None, str]:
        """Fetch versioned template, enforce allowlist, and safely render content."""
        template = await self.repo.get_template_by_code(society_id, template_code)
        if not template:
            raise TemplateNotFoundError(f"Notification template '{template_code}' not found.")

        version = await self.repo.get_published_version(template.id, channel, locale)
        if not version:
            raise TemplateNotFoundError(
                f"No published template version for code '{template_code}', channel '{channel}', locale '{locale}'."
            )

        # Allowlisted variable validation
        allowlisted = (
            set(template.allowlisted_variables.split(","))
            if template.allowlisted_variables
            else set()
        )
        provided_vars = variables or {}

        # Validate that provided variable keys are allowlisted if an allowlist is configured
        if allowlisted:
            disallowed = set(provided_vars.keys()) - allowlisted
            if disallowed:
                raise TemplateRenderError(
                    f"Disallowed template variables provided: {', '.join(sorted(disallowed))}"
                )

        # Safe String Interpolation with HTML Escaping
        rendered_subject = version.subject_template
        rendered_body = version.body_template

        if provided_vars:
            for k, v in provided_vars.items():
                safe_val = html.escape(str(v))
                placeholder = f"{{{k}}}"
                if rendered_subject:
                    rendered_subject = rendered_subject.replace(placeholder, safe_val)
                rendered_body = rendered_body.replace(placeholder, safe_val)

        # Verify no un-rendered code/eval injections remain
        if re.search(r"\{\{.*\}\}", rendered_body) or re.search(r"<script", rendered_body, re.I):
            raise TemplateRenderError("Security check failed: unescaped template logic detected.")

        return rendered_subject, rendered_body
