"""Sandbox Chat Agent — the ReAct loop that powers Comio's AI coding assistant.

This is the core AI loop:
1. User sends a message
2. LLM analyzes it and decides what to do
3. If LLM wants to use tools → execute them in the sandbox → feed results back
4. Repeat until LLM produces a final text response
5. Yield events (text chunks, tool calls, diffs) for streaming to the frontend

The agent is STATELESS — conversation history is loaded from the database
each time. This means the agent can be restarted without losing context.

Key design decisions:
- Uses native LLM tool calling (not regex parsing)
- Max 15 iterations to prevent infinite loops
- Each tool result is fed back as a "tool" message
- The system prompt defines the agent's personality and capabilities
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from adapters.base import BaseLLMAdapter, Message, ToolDefinition, ToolCall, LLMResponse
from .tools import SANDBOX_TOOLS, ToolResult, execute_tool

logger = logging.getLogger(__name__)

# Maximum tool-call iterations before forcing a stop
MAX_ITERATIONS = 15


# ── Chat Events (streamed to frontend) ───────────────

class ChatEventType(str, Enum):
    """Types of events the agent can emit during processing."""
    TEXT = "text"                    # Text chunk from the LLM (streamed)
    TOOL_CALL = "tool_call"          # Agent is calling a tool
    TOOL_RESULT = "tool_result"      # Tool finished, here's the result
    FILE_CREATED = "file_created"    # A new file was created
    FILE_MODIFIED = "file_modified"  # An existing file was edited
    COMMAND_OUTPUT = "command_output" # Shell command output
    ERROR = "error"                  # Something went wrong
    DONE = "done"                    # Agent finished processing


@dataclass
class ChatEvent:
    """A single event emitted by the agent during message processing.

    The frontend receives a stream of these events via WebSocket:
        {"type": "tool_call", "tool": "create_file", "args": {"path": "main.py"}}
        {"type": "file_created", "file": "main.py"}
        {"type": "text", "content": "I've created the main.py file with..."}
        {"type": "done", "files_modified": ["main.py"]}
    """
    type: ChatEventType
    content: str = ""
    tool: str | None = None
    args: dict | None = None
    file: str | None = None
    files_modified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a dict for JSON serialization over WebSocket."""
        d = {"type": self.type.value}
        if self.content:
            d["content"] = self.content
        if self.tool:
            d["tool"] = self.tool
        if self.args:
            d["args"] = self.args
        if self.file:
            d["file"] = self.file
        if self.files_modified:
            d["files_modified"] = self.files_modified
        return d


# ── System Prompt ─────────────────────────────────────

SYSTEM_PROMPT = """You are Comio, an expert AI software engineer that works inside a project sandbox.

You can create, read, edit, and delete files, run shell commands, search the codebase, and manage git — all inside an isolated Docker container.

## Your capabilities:
- **Create projects from scratch**: When asked to build something, scaffold the complete project structure with all necessary files
- **Edit existing code**: Read files to understand context, then make targeted edits
- **Install dependencies**: Use pip, npm, or other package managers via run_command
- **Run tests and commands**: Execute any shell command inside the sandbox
- **Git operations**: Commit changes, check status

## Guidelines:
1. **Read before editing**: Always read a file before editing it to understand the current content
2. **Create complete files**: When creating files, write the full content — don't use placeholders or "..."
3. **Explain your work**: After making changes, briefly explain what you did and why
4. **Handle errors gracefully**: If a tool call fails, try to fix the issue or explain what went wrong
5. **Follow best practices**: Write clean, well-documented, production-quality code
6. **Be concise in tool calls**: Don't explain what you're about to do in excessive detail before doing it — just do it and explain after
7. **Project structure**: Create proper project structure with README, requirements/package.json, .gitignore, etc.

## Important:
- You are working inside /workspace in a Docker container
- Python 3.12, Node.js 20, and git are available
- Files persist across messages (Docker volume)
- Always use the tools provided — don't just describe what to do
"""


def _build_system_prompt(project_name: str, project_description: str | None = None, project_type: str | None = None) -> str:
    """Build a context-aware system prompt for the agent."""
    prompt = SYSTEM_PROMPT
    prompt += f"\n## Current project: {project_name}"
    if project_description:
        prompt += f"\nDescription: {project_description}"
    if project_type:
        prompt += f"\nProject type: {project_type}"
    return prompt


# ── The Agent ─────────────────────────────────────────

class SandboxChatAgent:
    """AI agent that can create, read, edit, and deploy code inside a sandbox.

    This is the core of Comio. It implements a ReAct (Reason + Act) loop:
    1. Send conversation + tools to LLM
    2. LLM either responds with text (done) or requests tool calls (continue)
    3. Execute requested tools inside the sandbox
    4. Feed tool results back to LLM
    5. Repeat until LLM produces final text response

    Usage:
        agent = SandboxChatAgent(llm_adapter, file_ops, sandbox_manager)
        events = await agent.process_message(
            container_id="abc123",
            conversation_history=[...],
            user_message="Build me a Flask API",
            project_name="my-api",
        )
        for event in events:
            send_to_websocket(event.to_dict())
    """

    def __init__(
        self,
        llm_adapter: BaseLLMAdapter,
        file_ops,           # FileOpsService — injected to avoid circular imports
        sandbox_manager,    # SandboxManager — injected to avoid circular imports
    ):
        self.llm = llm_adapter
        self.file_ops = file_ops
        self.sandbox_mgr = sandbox_manager

    async def process_message(
        self,
        container_id: str,
        conversation_history: list[Message],
        user_message: str,
        project_name: str = "project",
        project_description: str | None = None,
        project_type: str | None = None,
    ) -> list[ChatEvent]:
        """Process a user message through the ReAct loop.

        Args:
            container_id: Docker container ID of the sandbox
            conversation_history: Previous messages in this chat session
            user_message: The new message from the user
            project_name: Name of the project (for system prompt context)
            project_description: Project description (for system prompt context)
            project_type: Project type like "api", "web" (for system prompt context)

        Returns:
            List of ChatEvents (text, tool calls, file changes, etc.)
        """
        events: list[ChatEvent] = []
        all_files_modified: list[str] = []

        # Build the messages list for the LLM
        system_prompt = _build_system_prompt(project_name, project_description, project_type)
        messages: list[Message] = [
            Message(role="system", content=system_prompt),
            *conversation_history,
            Message(role="user", content=user_message),
        ]

        logger.info("Processing message for project '%s': %.100s...", project_name, user_message)

        # ── The ReAct Loop ──────────────────────────────
        for iteration in range(MAX_ITERATIONS):
            logger.debug("Agent iteration %d/%d", iteration + 1, MAX_ITERATIONS)

            # Step 1: Call the LLM
            start_time = time.time()
            response: LLMResponse = await self.llm.complete(
                messages=messages,
                tools=SANDBOX_TOOLS,
                temperature=0.2,     # Low temperature for more deterministic code generation
                max_tokens=4096,
            )
            elapsed = (time.time() - start_time) * 1000
            logger.debug("LLM responded in %.0fms (finish_reason=%s, tools=%d)",
                        elapsed, response.finish_reason, len(response.tool_calls))

            # Step 2: Check if LLM wants to call tools
            if response.tool_calls:
                # LLM wants to use tools — execute each one
                for tool_call in response.tool_calls:
                    logger.info("Tool call: %s(%s)", tool_call.name, 
                              json.dumps(tool_call.arguments)[:200])

                    # Emit tool_call event (frontend shows "Reading main.py...")
                    events.append(ChatEvent(
                        type=ChatEventType.TOOL_CALL,
                        tool=tool_call.name,
                        args=tool_call.arguments,
                    ))

                    # Execute the tool
                    tool_result: ToolResult = await execute_tool(
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                        container_id=container_id,
                        file_ops=self.file_ops,
                        sandbox_manager=self.sandbox_mgr,
                    )

                    # Emit tool_result event
                    events.append(ChatEvent(
                        type=ChatEventType.TOOL_RESULT,
                        tool=tool_call.name,
                        content=tool_result.output[:500],  # Truncate for frontend
                    ))

                    # Emit file events for the UI
                    if tool_result.files_modified:
                        for f in tool_result.files_modified:
                            event_type = ChatEventType.FILE_CREATED if tool_call.name == "create_file" else ChatEventType.FILE_MODIFIED
                            events.append(ChatEvent(type=event_type, file=f))
                            if f not in all_files_modified:
                                all_files_modified.append(f)

                    # Emit command output event
                    if tool_call.name == "run_command":
                        events.append(ChatEvent(
                            type=ChatEventType.COMMAND_OUTPUT,
                            content=tool_result.output[:2000],
                        ))

                # Add the assistant's tool calls to conversation
                messages.append(Message(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                ))

                # Add each tool result as a tool message
                for i, tool_call in enumerate(response.tool_calls):
                    # Get the corresponding result (we executed them in order)
                    # Find the tool_result event for this tool call
                    tool_result_events = [e for e in events if e.type == ChatEventType.TOOL_RESULT and e.tool == tool_call.name]
                    tool_output = tool_result_events[-1].content if tool_result_events else "Tool executed."

                    messages.append(Message(
                        role="tool",
                        content=tool_output,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    ))

                # Continue the loop — LLM needs to see the tool results
                continue

            # Step 3: LLM produced a text response (no tool calls) — we're done
            if response.content:
                events.append(ChatEvent(
                    type=ChatEventType.TEXT,
                    content=response.content,
                ))

            break  # Exit the loop

        else:
            # Hit MAX_ITERATIONS without finishing
            logger.warning("Agent hit max iterations (%d) for project '%s'", MAX_ITERATIONS, project_name)
            events.append(ChatEvent(
                type=ChatEventType.ERROR,
                content=f"I've reached the maximum number of steps ({MAX_ITERATIONS}). Here's what I've done so far. Let me know if you'd like me to continue.",
            ))

        # Emit the done event with all modified files
        events.append(ChatEvent(
            type=ChatEventType.DONE,
            files_modified=all_files_modified,
        ))

        logger.info("Agent finished: %d events, %d files modified", len(events), len(all_files_modified))
        return events