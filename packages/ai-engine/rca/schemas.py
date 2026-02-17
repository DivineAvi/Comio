"""RCA data structures — not database models, just Python dataclasses."""

from dataclasses import dataclass, field
from enum import Enum


class DiagnosisCategory(str, Enum):
    """Categories of root causes."""
    CODE_BUG = "code_bug"           # Bug in application code
    INFRASTRUCTURE = "infra"         # Infrastructure issue (DB, network, disk)
    CONFIGURATION = "config"         # Misconfiguration (env vars, limits)
    DEPENDENCY = "dependency"        # External service failure
    LOAD = "load"                    # Traffic/load spike
    UNKNOWN = "unknown"              # Can't determine


@dataclass
class Evidence:
    """A piece of evidence supporting the diagnosis."""
    type: str                        # "metric" | "log" | "deploy" | "incident"
    source: str                      # Where this came from (e.g., "prometheus", "loki")
    description: str                 # Human-readable description
    value: str | float | None = None # The actual value (e.g., error rate = 0.65)
    timestamp: str | None = None     # When this was observed


@dataclass
class Action:
    """A suggested action to resolve the incident."""
    description: str                 # What to do
    priority: str                    # "immediate" | "high" | "medium" | "low"
    automated: bool = False          # Can Comio auto-apply this?


@dataclass
class Diagnosis:
    """The result of root cause analysis."""
    root_cause: str                  # Human-readable explanation
    category: DiagnosisCategory
    confidence: float                # 0.0 - 1.0
    evidence: list[Evidence] = field(default_factory=list)
    affected_components: list[str] = field(default_factory=list)
    suggested_actions: list[Action] = field(default_factory=list)
    similar_incidents: list[str] = field(default_factory=list)  # UUIDs
    reasoning: str = ""              # LLM's chain-of-thought

    def to_dict(self) -> dict:
        """Serialize for storage in database (JSONB field)."""
        return {
            "root_cause": self.root_cause,
            "category": self.category.value,
            "confidence": self.confidence,
            "evidence": [
                {
                    "type": e.type,
                    "source": e.source,
                    "description": e.description,
                    "value": e.value,
                    "timestamp": e.timestamp,
                }
                for e in self.evidence
            ],
            "affected_components": self.affected_components,
            "suggested_actions": [
                {
                    "description": a.description,
                    "priority": a.priority,
                    "automated": a.automated,
                }
                for a in self.suggested_actions
            ],
            "similar_incidents": self.similar_incidents,
            "reasoning": self.reasoning,
        }