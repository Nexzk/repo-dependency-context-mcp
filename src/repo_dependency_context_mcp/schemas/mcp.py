from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source_type: str
    title: str | None = None
    path_or_url: str
    symbol_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    snippet: str
    why_selected: str
    freshness_reason: str
    authority: str
    version_range: str | None = None


class SearchContextResponse(BaseModel):
    task_type: str
    clarify_needed: bool
    evidence: list[EvidenceItem]
    conflicts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class GetSourceResponse(BaseModel):
    path_or_url: str
    source_type: str
    title: str | None = None
    start_line: int
    end_line: int
    content: str


class RelatedChangesResponse(BaseModel):
    pull_requests: list[dict] = Field(default_factory=list)
    commits: list[dict] = Field(default_factory=list)
    issues: list[dict] = Field(default_factory=list)


class DependencyNotesResponse(BaseModel):
    evidence: list[EvidenceItem]
    conflicts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
