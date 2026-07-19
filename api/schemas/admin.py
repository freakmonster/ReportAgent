"""Admin API schemas for feature flag management and system administration."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FeatureFlagItem(BaseModel):
    """A single feature flag state."""

    name: str = Field(..., description="Flag name")
    enabled: bool = Field(..., description="Current effective state")
    source: str = Field(default="default", description="'default' (YAML) or 'redis' (override)")


class FeatureFlagsResponse(BaseModel):
    """Response for GET /admin/flags — all flags with their states."""

    flags: dict[str, FeatureFlagItem] = Field(
        default_factory=dict,
        description="Map of flag name → state",
    )
    total: int = Field(default=0)


class FeatureFlagUpdateRequest(BaseModel):
    """Request body for PUT /admin/flags/{name}."""

    enabled: bool = Field(..., description="New state for the flag")


class FeatureFlagUpdateResponse(BaseModel):
    """Response for PUT /admin/flags/{name}."""

    name: str
    enabled: bool
    message: str


class FeatureFlagResetResponse(BaseModel):
    """Response for DELETE /admin/flags/{name}."""

    name: str
    message: str
    reset_to: bool = Field(..., description="Reverted default value")


class AdminStatusResponse(BaseModel):
    """System status summary for the admin dashboard."""

    app_name: str
    app_version: str
    environment: str
    feature_flags: dict[str, bool]
    services: dict[str, str] = Field(default_factory=dict)
