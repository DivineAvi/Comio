"""Fix generation — LLM produces concrete fix proposals from diagnosis."""
from .schemas import FixType, RiskLevel, FixResult
from .safety import is_path_allowed, validate_diff, DENY_LIST, MAX_DIFF_SIZE, MAX_FILES_CHANGED
from .generator import FixGenerator

__all__ = [
    "FixType",
    "RiskLevel",
    "FixResult",
    "FixGenerator",
    "is_path_allowed",
    "validate_diff",
    "DENY_LIST",
    "MAX_DIFF_SIZE",
    "MAX_FILES_CHANGED",
]
