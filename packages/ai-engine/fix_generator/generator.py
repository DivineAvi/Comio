"""FixGenerator — LLM generates concrete fix from diagnosis + code context."""
import json
import logging
from typing import Any

from adapters import AdapterFactory, Message

from .schemas import FixResult, FixType, RiskLevel
from .safety import validate_diff

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert SRE/developer. Given a root-cause diagnosis of an incident, you propose a concrete fix.

Rules:
- Output only valid JSON. No markdown, no code fences.
- fix_type must be one of: code_change, config_change, infra_change, rollback, scale.
- risk_level must be one of: low, medium, high.
- diff must be a valid unified diff (e.g. --- file.txt / +++ file.txt with hunks).
- files_changed must list every file path that appears in the diff.
- If you cannot produce a code/config fix (e.g. infra or rollback), still output the structure; use explanation and test_suggestions, and set diff to "" and files_changed to [].
- Do not suggest changes to .env, secrets, or credential files.

Output JSON:
{
  "fix_type": "code_change",
  "diff": "unified diff string",
  "files_changed": ["path/to/file.py"],
  "explanation": "Why this fix works",
  "risk_level": "low",
  "test_suggestions": ["Run unit tests", "Check /health"],
  "confidence": 0.85
}
"""


class FixGenerator:
    """Generate a concrete fix proposal from a diagnosis and optional source code."""

    def __init__(self, llm_provider: str = "openai", llm_model: str = "gpt-4o-mini"):
        self.llm_provider = llm_provider
        self.llm_model = llm_model

    async def generate(
        self,
        diagnosis_summary: dict[str, Any],
        code_context: dict[str, str] | None = None,
    ) -> FixResult:
        """
        Generate a fix from diagnosis and optional code.

        diagnosis_summary: keys like root_cause, category, suggested_actions, reasoning.
        code_context: optional dict of file_path -> file_content (e.g. from sandbox).
        """
        code_context = code_context or {}
        prompt = self._build_prompt(diagnosis_summary, code_context)

        try:
            raw = await self._call_llm(prompt)
            data = json.loads(raw)
            result = self._parse_result(data)
            # Safety
            ok, err = validate_diff(result.diff, result.files_changed)
            if not ok:
                raise ValueError(f"Fix rejected by safety: {err}")
            return result
        except Exception as e:
            logger.error("Fix generation failed: %s", e)
            raise

    def _build_prompt(self, diagnosis_summary: dict[str, Any], code_context: dict[str, str]) -> str:
        parts = [
            "# Diagnosis",
            f"**Root cause:** {diagnosis_summary.get('root_cause', 'N/A')}",
            f"**Category:** {diagnosis_summary.get('category', 'N/A')}",
            f"**Confidence:** {diagnosis_summary.get('confidence', 0)}",
            "",
            "**Reasoning:**",
            diagnosis_summary.get("reasoning", "N/A"),
            "",
            "**Suggested actions from diagnosis:**",
        ]
        for a in diagnosis_summary.get("suggested_actions") or []:
            desc = a.get("description", a) if isinstance(a, dict) else str(a)
            parts.append(f"- {desc}")
        parts.append("")

        if code_context:
            parts.append("# Relevant source code (you may propose edits)")
            for path, content in list(code_context.items())[:15]:  # cap files
                parts.append(f"## {path}")
                parts.append("```")
                parts.append(content[:8000] if len(content) > 8000 else content)
                parts.append("```")
                parts.append("")
        else:
            parts.append("# No source code provided — propose a fix in explanation and test_suggestions; use empty diff and files_changed if no code change.")

        parts.append("# Task")
        parts.append("Produce a single JSON object with fix_type, diff, files_changed, explanation, risk_level, test_suggestions, confidence.")
        return "\n".join(parts)

    async def _call_llm(self, prompt: str) -> str:
        from apps.api.config import settings

        api_key = (
            settings.openai_api_key if self.llm_provider == "openai"
            else settings.anthropic_api_key
        )
        if not api_key:
            raise ValueError(f"API key not set for provider: {self.llm_provider}")

        adapter = AdapterFactory.create(
            provider=self.llm_provider,
            api_key=api_key,
            model=self.llm_model,
        )
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]
        response = await adapter.complete(
            messages=messages,
            temperature=0.2,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )
        if not response.content or not response.content.strip():
            raise ValueError("LLM returned empty response")
        return response.content

    def _parse_result(self, data: dict) -> FixResult:
        fix_type = data.get("fix_type", "code_change")
        if fix_type not in [e.value for e in FixType]:
            fix_type = FixType.CODE_CHANGE.value
        risk = data.get("risk_level", "medium")
        if risk not in [e.value for e in RiskLevel]:
            risk = RiskLevel.MEDIUM.value
        return FixResult(
            fix_type=fix_type,
            diff=data.get("diff", ""),
            files_changed=data.get("files_changed") or [],
            explanation=data.get("explanation", ""),
            risk_level=risk,
            test_suggestions=data.get("test_suggestions") or [],
            confidence=float(data.get("confidence", 0.5)),
        )
