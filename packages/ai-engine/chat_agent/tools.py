"""Sandbox tools — what the AI agent can do inside a project sandbox.

Each tool has:
1. A DEFINITION (ToolDefinition) — sent to the LLM so it knows what's available
2. An EXECUTOR function — actually runs the operation inside the sandbox container

The LLM sees the definitions and decides which tools to call.
The agent loop calls the executor with the LLM's chosen arguments.

Architecture:
    LLM decides: "I need to create main.py"
    → Returns: ToolCall(name="create_file", arguments={"path": "main.py", "content": "..."})
    → Agent calls: execute_tool("create_file", {"path": "main.py", "content": "..."}, ...)
    → Executor calls: file_ops.write_file(container_id, "main.py", "...")
    → Result sent back to LLM as a tool message
"""

import logging
from dataclasses import dataclass

from adapters.base import ToolDefinition

logger = logging.getLogger(__name__)


# ── Tool Definitions ──────────────────────────────────
# These are sent to the LLM with every request.
# The LLM reads these and decides which tools to call.
# Parameters use JSON Schema format (same as OpenAI function calling spec).

SANDBOX_TOOLS: list[ToolDefinition] = [
    # --- File Operations ---
    ToolDefinition(
        name="read_file",
        description="Read the contents of a file in the project. Returns file content, size, and line count.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to workspace root, e.g. 'src/main.py'",
                },
            },
            "required": ["path"],
        },
    ),
    ToolDefinition(
        name="create_file",
        description=(
            "Create a new file or overwrite an existing file with the given content. "
            "Parent directories are created automatically."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to workspace root",
                },
                "content": {
                    "type": "string",
                    "description": "The full file content to write",
                },
            },
            "required": ["path", "content"],
        },
    ),
    ToolDefinition(
        name="edit_file",
        description=(
            "Edit a file by replacing a specific string with new content. "
            "Use read_file first to see the current content, then use this to make targeted edits. "
            "old_string must match exactly (including whitespace and indentation)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to workspace root",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement string",
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
    ),
    ToolDefinition(
        name="delete_file",
        description="Delete a file or directory from the project.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to workspace root",
                },
            },
            "required": ["path"],
        },
    ),
    ToolDefinition(
        name="list_directory",
        description="List files and directories at a path. Shows file names, sizes, and types.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to workspace root. Use '.' for root.",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "If true, list all files recursively. Default false.",
                },
            },
            "required": ["path"],
        },
    ),
    ToolDefinition(
        name="search_codebase",
        description="Search for a text pattern across the entire codebase using ripgrep. Returns matching file paths, line numbers, and content.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search pattern (supports regex)",
                },
                "glob": {
                    "type": "string",
                    "description": "Optional file filter, e.g. '*.py' to only search Python files",
                },
            },
            "required": ["query"],
        },
    ),
    # --- Execution ---
    ToolDefinition(
        name="run_command",
        description=(
            "Run a shell command inside the project sandbox. "
            "Use for: installing dependencies (pip install, npm install), "
            "running tests (pytest, npm test), linting, building, etc. "
            "Commands run in /workspace as the sandbox user."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute, e.g. 'pip install fastapi'",
                },
            },
            "required": ["command"],
        },
    ),
    # --- Project Scaffolding ---
    ToolDefinition(
        name="create_directory",
        description="Create a directory (and any parent directories). Use before creating files in new directories.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to workspace root, e.g. 'src/models'",
                },
            },
            "required": ["path"],
        },
    ),
    # --- Git ---
    ToolDefinition(
        name="git_commit",
        description="Stage all changes and create a git commit with the given message.",
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message describing the changes",
                },
            },
            "required": ["message"],
        },
    ),
    ToolDefinition(
        name="git_status",
        description="Get the current git status showing modified, staged, and untracked files.",
        parameters={
            "type": "object",
            "properties": {},
        },
    ),
]


# ── Tool Executor ─────────────────────────────────────

@dataclass
class ToolResult:
    """Result of executing a tool inside the sandbox."""
    success: bool
    output: str           # Human-readable result to send back to LLM
    files_modified: list[str] | None = None   # Track which files changed


async def execute_tool(
    tool_name: str,
    arguments: dict,
    container_id: str,
    file_ops,          # FileOpsService instance (passed in to avoid circular imports)
    sandbox_manager,   # SandboxManager instance
) -> ToolResult:
    """Execute a tool call inside the sandbox container.

    This is the bridge between the LLM's decisions and actual side effects.
    The LLM says "call create_file with these args" → this function does it.
    """
    try:
        if tool_name == "read_file":
            result = await file_ops.read_file(container_id, arguments["path"])
            return ToolResult(
                success=True,
                output=f"File: {result['path']} ({result['lines']} lines, {result['size']} bytes)\n\n{result['content']}",
            )

        elif tool_name == "create_file":
            await file_ops.write_file(container_id, arguments["path"], arguments["content"])
            return ToolResult(
                success=True,
                output=f"File created: {arguments['path']}",
                files_modified=[arguments["path"]],
            )

        elif tool_name == "edit_file":
            # Read current content, do the replacement, write back
            current = await file_ops.read_file(container_id, arguments["path"])
            old_string = arguments["old_string"]
            new_string = arguments["new_string"]

            if old_string not in current["content"]:
                return ToolResult(
                    success=False,
                    output=f"edit_file failed: old_string not found in {arguments['path']}. Use read_file to check the current content.",
                )

            updated = current["content"].replace(old_string, new_string, 1)
            await file_ops.write_file(container_id, arguments["path"], updated)
            return ToolResult(
                success=True,
                output=f"File edited: {arguments['path']}",
                files_modified=[arguments["path"]],
            )

        elif tool_name == "delete_file":
            await file_ops.delete_file(container_id, arguments["path"])
            return ToolResult(
                success=True,
                output=f"Deleted: {arguments['path']}",
                files_modified=[arguments["path"]],
            )

        elif tool_name == "list_directory":
            entries = await file_ops.list_files(
                container_id,
                arguments.get("path", "."),
                arguments.get("recursive", False),
            )
            if not entries:
                return ToolResult(success=True, output="Directory is empty.")

            lines = []
            for e in entries:
                prefix = "📁 " if e["is_directory"] else "📄 "
                size = f" ({e['size']} bytes)" if e.get("size") else ""
                lines.append(f"{prefix}{e['path']}{size}")
            return ToolResult(success=True, output="\n".join(lines))

        elif tool_name == "search_codebase":
            matches = await file_ops.search_files(
                container_id,
                arguments["query"],
                arguments.get("glob"),
            )
            if not matches:
                return ToolResult(success=True, output=f"No matches found for '{arguments['query']}'")

            lines = [f"Found {len(matches)} matches:\n"]
            for m in matches:
                lines.append(f"  {m['path']}:{m['line_number']}  {m['content']}")
            return ToolResult(success=True, output="\n".join(lines))

        elif tool_name == "run_command":
            result = await sandbox_manager.exec_command(
                container_id,
                ["bash", "-c", arguments["command"]],
                timeout=60,
            )
            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")
            output = "\n".join(output_parts) or "(no output)"

            return ToolResult(
                success=result.exit_code == 0,
                output=f"Exit code: {result.exit_code}\n{output}",
            )

        elif tool_name == "create_directory":
            await file_ops.create_directory(container_id, arguments["path"])
            return ToolResult(
                success=True,
                output=f"Directory created: {arguments['path']}",
            )

        elif tool_name == "git_commit":
            sha = await file_ops.commit_and_push(container_id, arguments["message"])
            return ToolResult(
                success=True,
                output=f"Committed: {sha[:12]} — {arguments['message']}",
            )

        elif tool_name == "git_status":
            status = await file_ops.git_status(container_id)
            lines = [f"Branch: {status['branch']}"]
            if status["staged"]:
                lines.append(f"Staged: {', '.join(status['staged'])}")
            if status["modified"]:
                lines.append(f"Modified: {', '.join(status['modified'])}")
            if status["untracked"]:
                lines.append(f"Untracked: {', '.join(status['untracked'])}")
            if not status["has_changes"]:
                lines.append("Working tree clean — no changes.")
            return ToolResult(success=True, output="\n".join(lines))

        else:
            return ToolResult(
                success=False,
                output=f"Unknown tool: {tool_name}",
            )

    except Exception as e:
        logger.error("Tool execution failed: %s(%s) → %s", tool_name, arguments, e)
        return ToolResult(
            success=False,
            output=f"Error: {str(e)}",
        )