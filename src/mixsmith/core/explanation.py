"""Curation Explainability Engine for Mixsmith.

Generates structured, deterministic explanation reports detailing why tracks
were selected, excluded, or placed at specific positions, and which constraints
governed each decision.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from mixsmith.core.models import ConstraintResult, Track


@dataclass
class TrackCurationDecision:
    """Deterministic explanation record for a single track's lifecycle in the curation pipeline."""
    track_id: str
    track_name: str
    artists: List[str]
    selected: bool
    position: Optional[int] = None  # 1-based playlist index
    selection_reasons: List[str] = field(default_factory=list)
    exclusion_reasons: List[str] = field(default_factory=list)
    placement_reason: str = ""
    constraints_applied: List[str] = field(default_factory=list)
    constraints_relaxed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CurationExplanation:
    """Comprehensive audit and explainability report for a curated playlist."""
    playlist_name: str
    source_track_count: int
    final_track_count: int
    duration_achieved_ms: int
    duration_target_minutes: Optional[int]
    constraint_audits: List[ConstraintResult] = field(default_factory=list)
    track_decisions: List[TrackCurationDecision] = field(default_factory=list)
    diff_summary: str = ""

    @property
    def duration_formatted(self) -> str:
        total_seconds = self.duration_achieved_ms // 1000
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        if h > 0:
            return f"{h}h {m}m {s}s"
        return f"{m}m {s}s"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "playlist_name": self.playlist_name,
            "source_track_count": self.source_track_count,
            "final_track_count": self.final_track_count,
            "duration_achieved": self.duration_formatted,
            "duration_target_minutes": self.duration_target_minutes,
            "diff_summary": self.diff_summary,
            "constraint_audits": [
                {
                    "name": c.name,
                    "satisfied": c.satisfied,
                    "severity": c.severity,
                    "details": c.details
                }
                for c in self.constraint_audits
            ],
            "track_decisions": [d.to_dict() for d in self.track_decisions]
        }

    def to_json(self, indent: int = 2) -> str:
        """Serializes explanation report to JSON."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Renders explanation report as human-readable GitHub Flavored Markdown."""
        lines = [
            f"# Curation Explanation Report: {self.playlist_name}",
            "",
            "## 1. Overview & Verification",
            f"- **Source Track Pool**: {self.source_track_count} tracks",
            f"- **Final Curated Count**: {self.final_track_count} tracks",
            f"- **Total Runtime**: {self.duration_formatted}" + (f" (Target: {self.duration_target_minutes} min)" if self.duration_target_minutes else ""),
            f"- **Diff Summary**: {self.diff_summary}",
            "",
            "## 2. Independent Constraint Audits",
            "| Constraint | Status | Severity | Audit Details |",
            "| :--- | :---: | :---: | :--- |"
        ]

        for c in self.constraint_audits:
            status = "PASS" if c.satisfied else "FAIL"
            lines.append(f"| `{c.name}` | **{status}** | `{c.severity}` | {c.details} |")

        lines.extend([
            "",
            "## 3. Track Sequencing Decisions (Selected Tracks)",
            "| # | Track Name | Artist(s) | Placement Rationale | Constraints Applied |",
            "| --: | :--- | :--- | :--- | :--- |"
        ])

        selected = [d for d in self.track_decisions if d.selected]
        selected.sort(key=lambda d: d.position or 9999)

        for d in selected:
            pos = d.position or "-"
            artists_str = ", ".join(d.artists)
            applied = ", ".join(d.constraints_applied) or "standard"
            lines.append(f"| {pos} | {d.track_name} | {artists_str} | {d.placement_reason} | `{applied}` |")

        excluded = [d for d in self.track_decisions if not d.selected]
        if excluded:
            lines.extend([
                "",
                f"## 4. Excluded Tracks ({len(excluded)} tracks omitted)",
                "| Track Name | Artist(s) | Primary Exclusion Reason |",
                "| :--- | :--- | :--- |"
            ])
            for d in excluded[:40]:  # Limit display to top 40 exclusions
                artists_str = ", ".join(d.artists)
                reason = d.exclusion_reasons[0] if d.exclusion_reasons else "Omitted by optimization"
                lines.append(f"| {d.track_name} | {artists_str} | {reason} |")
            if len(excluded) > 40:
                lines.append(f"| *...and {len(excluded) - 40} more tracks omitted* | | |")

        return "\n".join(lines)
