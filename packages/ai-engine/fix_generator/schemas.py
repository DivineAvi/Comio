"""Fix generator output — structured fix proposal."""
from dataclasses import dataclass
from enum import Enum


class FixType(str, Enum):
    """Type of fix."""
    CODE_CHANGE = "code_change"
    CONFIG_CHANGE = "config_change"
    INFRA_CHANGE = "infra_change"
    ROLLBACK = "rollback"
    SCALE = "scale"


class RiskLevel(str, Enum):
    """Risk level of the fix."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class FixResult:
    """Result of fix generation — maps to Remediation model."""
    fix_type: str          # FixType value
    diff: str              # Unified diff format
    files_changed: list[str]
    explanation: str
    risk_level: str        # RiskLevel value
    test_suggestions: list[str]  # What to verify after applying
    confidence: float      # 0.0 - 1.0