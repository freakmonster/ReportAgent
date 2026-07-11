"""
User context service — preferences, templates, permissions.

Manages per-user state that is NOT part of the LangGraph State:
- Historical preferences
- Commonly used report templates
- Access level / permissions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class UserTier(str, Enum):
    """Access tier for users."""
    FREE = "free"          # Basic reports, limited features
    PRO = "pro"            # Full features, higher rate limits
    ADMIN = "admin"       # Admin access, no restrictions


@dataclass
class UserContext:
    """Per-user context for personalization and access control."""
    user_id: str
    tier: UserTier = UserTier.FREE
    preferred_language: str = "zh-CN"
    preferred_template: str = "deep_report"
    rate_limit_remaining: int = 1000
    rate_limit_reset_at: str = ""
    report_history: list[str] = field(default_factory=list)  # recent workflow_ids
    created_at: str = ""


@dataclass
class TemplatePreference:
    """User's preference for a specific report template."""
    template_name: str
    use_count: int = 0
    last_used: str = ""
    is_favorite: bool = False


# In-memory storage (simulating what would be a database table)
_user_contexts: dict[str, UserContext] = {}
_template_preferences: dict[str, list[TemplatePreference]] = {}


# ---------------------------------------------------------------------------
# Default templates
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATES: dict[UserTier, list[str]] = {
    UserTier.FREE: ["flash_news"],
    UserTier.PRO: ["deep_report", "flash_news", "earnings_analysis"],
    UserTier.ADMIN: ["deep_report", "flash_news", "earnings_analysis"],
}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def get_or_create_user(user_id: str, tier: UserTier = UserTier.FREE) -> UserContext:
    """Get existing user context or create a new one.

    Args:
        user_id: Unique user identifier.
        tier: Access tier (defaults to FREE for new users).

    Returns:
        Existing or new UserContext.
    """
    if user_id not in _user_contexts:
        _user_contexts[user_id] = UserContext(
            user_id=user_id,
            tier=tier,
            rate_limit_reset_at=datetime.now(timezone.utc).isoformat(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    return _user_contexts[user_id]


def get_available_templates(user_id: str) -> list[str]:
    """Get the list of report templates available to a user.

    Args:
        user_id: User identifier.

    Returns:
        List of template names the user can use.
    """
    ctx = get_or_create_user(user_id)
    return _DEFAULT_TEMPLATES.get(ctx.tier, _DEFAULT_TEMPLATES[UserTier.FREE])


def get_template_preferences(user_id: str) -> list[TemplatePreference]:
    """Get or initialize template preference tracking for a user.

    Args:
        user_id: User identifier.

    Returns:
        List of TemplatePreference objects.
    """
    if user_id not in _template_preferences:
        _template_preferences[user_id] = [
            TemplatePreference(template_name=name)
            for name in get_available_templates(user_id)
        ]
    return _template_preferences[user_id]


def record_template_usage(user_id: str, template_name: str) -> None:
    """Record a template usage for a user (updates use_count and last_used).

    Args:
        user_id: User identifier.
        template_name: Name of the template that was used.
    """
    prefs = get_template_preferences(user_id)
    for pref in prefs:
        if pref.template_name == template_name:
            pref.use_count += 1
            pref.last_used = datetime.now(timezone.utc).isoformat()
            return


def set_preferred_template(user_id: str, template_name: str) -> bool:
    """Set the user's preferred default template.

    Args:
        user_id: User identifier.
        template_name: The template to set as preferred.

    Returns:
        True if the template was valid and set, False otherwise.
    """
    available = get_available_templates(user_id)
    if template_name not in available:
        return False

    ctx = get_or_create_user(user_id)
    ctx.preferred_template = template_name
    return True


def check_rate_limit(user_id: str, max_requests: int | None = None) -> tuple[bool, int]:
    """Check if the user has remaining rate limit quota.

    Args:
        user_id: User identifier.
        max_requests: Optional custom max (defaults depend on tier).

    Returns:
        (allowed, remaining) tuple.
    """
    ctx = get_or_create_user(user_id)

    if max_requests is None:
        limits = {
            UserTier.FREE: 50,
            UserTier.PRO: 500,
            UserTier.ADMIN: 10_000,
        }
        max_requests = limits.get(ctx.tier, 50)

    ctx.rate_limit_remaining = max_requests  # reset on check for simplicity
    allowed = ctx.rate_limit_remaining > 0
    return allowed, ctx.rate_limit_remaining


def add_to_history(user_id: str, workflow_id: str, max_history: int = 20) -> None:
    """Add a workflow ID to the user's report history.

    Args:
        user_id: User identifier.
        workflow_id: The completed workflow ID.
        max_history: Maximum items to keep.
    """
    ctx = get_or_create_user(user_id)
    ctx.report_history.insert(0, workflow_id)
    if len(ctx.report_history) > max_history:
        ctx.report_history = ctx.report_history[:max_history]
