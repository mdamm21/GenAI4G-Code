"""Interactive Issue schemas — structured warnings/errors with resolution choices.

These models define the contract between the core pipeline (which collects
issues) and the CLI layer (which presents them interactively). Core modules
never import input() — all interaction is driven by the CLI layer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IssueChoice(BaseModel):
    """A single resolution option presented to the user."""

    key: str
    label: str
    description: str | None = None
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)


class InteractiveIssue(BaseModel):
    """A canonical issue collected from validation, safety, or guardrail checks."""

    id: str
    code: str
    severity: Literal["info", "warning", "error"]
    category: str
    title: str
    message: str

    actionable: bool = False
    blocking: bool = False

    source_messages: list[str] = Field(default_factory=list)
    affected_operations: list[int] = Field(default_factory=list)

    context: dict[str, Any] = Field(default_factory=dict)
    choices: list[IssueChoice] = Field(default_factory=list)


class ResolutionDecision(BaseModel):
    """Record of a user's decision on an interactive issue."""

    issue_id: str
    issue_code: str
    action: str
    choice_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ignored: bool = False
