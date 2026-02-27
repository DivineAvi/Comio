"""Safety guardrails for generated fixes."""
import re

# Files we never allow the LLM to modify (secrets, config with credentials)
DENY_LIST = (
    ".env",
    ".env.local",
    ".env.production",
    "secrets.yaml",
    "secrets.yml",
    "credentials.json",
    ".credentials",
    "id_rsa",
    "id_ed25519",
)

# Max size of a single diff (characters) — prevent huge patches
MAX_DIFF_SIZE = 50_000

# Max number of files in one fix
MAX_FILES_CHANGED = 20


def is_path_allowed(file_path: str) -> bool:
    """Return True if the file is allowed to be modified."""
    base = file_path.split("/")[-1].split("\\")[-1].lower()
    return not any(base == d or base.endswith("." + d) for d in DENY_LIST)


def validate_diff(diff: str, files_changed: list[str]) -> tuple[bool, str]:
    """
    Validate generated diff and file list.
    Returns (ok, error_message).
    """
    if len(diff) > MAX_DIFF_SIZE:
        return False, f"Diff too large ({len(diff)} chars, max {MAX_DIFF_SIZE})"
    if len(files_changed) > MAX_FILES_CHANGED:
        return False, f"Too many files ({len(files_changed)}, max {MAX_FILES_CHANGED})"
    for path in files_changed:
        if not is_path_allowed(path):
            return False, f"File not allowed: {path}"
    return True, ""