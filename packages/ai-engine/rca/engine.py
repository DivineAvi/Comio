"""RCA Engine — AI-powered root cause analysis.

This is the orchestrator that:
1. Gathers context (metrics, logs, similar incidents)
2. Formats a prompt for the LLM
3. Calls the LLM with structured output
4. Parses the response into a Diagnosis
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from adapters import AdapterFactory, Message
from apps.api.models.incident import Incident
from .context_gatherer import ContextGatherer
from .schemas import Diagnosis, Evidence, Action, DiagnosisCategory

logger = logging.getLogger(__name__)

# ── System Prompt for RCA ─────────────────────────────

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer (SRE) performing root cause analysis on production incidents.

Your goal: Analyze incidents and provide actionable diagnoses.

Guidelines:
- Be specific and technical in your analysis
- Focus on observable evidence (metrics, logs, timing)
- Consider common failure modes: code bugs, infrastructure issues, configuration problems, dependency failures, load spikes
- Assign confidence scores honestly (0.0 = wild guess, 1.0 = certain)
- Suggest concrete actions, prioritized by impact
- If multiple root causes are possible, mention them in reasoning

Output format: JSON with this structure:
{
  "root_cause": "Clear explanation of what went wrong",
  "category": "code_bug" | "infra" | "config" | "dependency" | "load" | "unknown",
  "confidence": 0.85,
  "affected_components": ["api-server", "database"],
  "suggested_actions": [
    {
      "description": "What to do",
      "priority": "immediate" | "high" | "medium" | "low",
      "automated": false
    }
  ],
  "reasoning": "Step-by-step explanation of how you reached this conclusion"
}
"""


class RCAEngine:
    """Root Cause Analysis engine using LLM."""

    def __init__(
        self,
        llm_provider: str = "openai",
        llm_model: str = "gpt-4",
        prometheus_url: str = "http://localhost:9090",
    ):
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.context_gatherer = ContextGatherer(prometheus_url)

    async def diagnose(
        self,
        db: AsyncSession,
        incident: Incident,
    ) -> Diagnosis:
        """Perform root cause analysis on an incident.

        Steps:
        1. Gather context (metrics, similar incidents, etc.)
        2. Build prompt with all evidence
        3. Call LLM for analysis
        4. Parse response into Diagnosis
        """
        logger.info("Starting RCA for incident %s (%s)", incident.id, incident.title)

        # Step 1: Gather context
        context = await self.context_gatherer.gather_context(db, incident)

        # Step 2: Build prompt
        prompt = self._build_prompt(context)

        # Step 3: Call LLM
        try:
            llm_response = await self._call_llm(prompt)
            diagnosis_dict = json.loads(llm_response)

            # Step 4: Parse into Diagnosis object
            diagnosis = self._parse_diagnosis(diagnosis_dict, context)

            logger.info(
                "RCA complete for incident %s: %s (confidence: %.2f)",
                incident.id,
                diagnosis.category.value,
                diagnosis.confidence,
            )

            return diagnosis

        except Exception as e:
            logger.error("RCA failed for incident %s: %s", incident.id, e)
            # Return a fallback diagnosis
            return Diagnosis(
                root_cause=f"RCA failed: {str(e)}",
                category=DiagnosisCategory.UNKNOWN,
                confidence=0.0,
                reasoning="RCA engine encountered an error during analysis",
            )

    def _build_prompt(self, context: dict) -> str:
        """Build the prompt for the LLM with all context."""
        prompt_parts = [
            "# Incident Analysis Request\n",
            f"## Incident Details",
            f"- **Title**: {context['title']}",
            f"- **Severity**: {context['severity']}",
            f"- **Occurred at**: {context['created_at']}",
            f"- **Project ID**: {context['project_id']}\n",
        ]

        # Add alert data
        if context.get("alert_data"):
            alert_payload = context["alert_data"].get("payload", {})
            prompt_parts.append("## Alert Information")
            prompt_parts.append(f"- **Alert name**: {alert_payload.get('alert_name', 'N/A')}")
            
            labels = alert_payload.get("labels", {})
            if labels:
                prompt_parts.append("- **Labels**:")
                for key, value in labels.items():
                    prompt_parts.append(f"  - {key}: {value}")
            
            annotations = alert_payload.get("annotations", {})
            if annotations:
                prompt_parts.append("- **Annotations**:")
                for key, value in annotations.items():
                    prompt_parts.append(f"  - {key}: {value}")
            prompt_parts.append("")

        # Add metrics evidence
        if context.get("metrics"):
            prompt_parts.append("## Metrics Evidence")
            for evidence in context["metrics"]:
                if isinstance(evidence, Evidence):
                    prompt_parts.append(
                        f"- **{evidence.description}**: {evidence.value}"
                    )
            prompt_parts.append("")

        # Add similar incidents
        if context.get("similar_incidents"):
            prompt_parts.append("## Similar Past Incidents")
            prompt_parts.append(
                f"Found {len(context['similar_incidents'])} similar incidents in the past:"
            )
            for inc in context["similar_incidents"]:
                prompt_parts.append(
                    f"- {inc['created_at']}: {inc['title']} "
                    f"(severity: {inc['severity']}, had_diagnosis: {inc['had_diagnosis']})"
                )
            prompt_parts.append("")

        # Add RAG retrieved context (runbooks, documentation)
        if context.get("rag_context"):
            prompt_parts.append("## Relevant Runbooks & Documentation")
            prompt_parts.append(
                f"Retrieved {len(context['rag_context'])} relevant documents:"
            )
            for idx, doc in enumerate(context["rag_context"], 1):
                prompt_parts.append(
                    f"\n### Document {idx} ({doc['content_type']}, similarity: {doc['similarity']:.2f})"
                )
                prompt_parts.append(f"**Source**: {doc['source']}")
                prompt_parts.append(f"**Content**:\n{doc['content']}")
            prompt_parts.append("")

        prompt_parts.append("## Your Task")
        prompt_parts.append(
            "Analyze this incident and provide a root cause diagnosis in JSON format as specified."
        )

        return "\n".join(prompt_parts)

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the analysis prompt."""
        # Get API key from environment/settings
        from apps.api.config import settings
        
        api_key = (
            settings.openai_api_key if self.llm_provider == "openai"
            else settings.anthropic_api_key
        )
        
        if not api_key:
            raise ValueError(f"API key not configured for provider: {self.llm_provider}")
        
        # Create LLM adapter
        adapter = AdapterFactory.create(
            provider=self.llm_provider,
            api_key=api_key,
            model=self.llm_model,
        )

        # Build messages
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]

        # Call LLM with JSON mode
        response = await adapter.complete(
            messages=messages,
            temperature=0.3,  # Lower temperature for more focused analysis
            max_tokens=2000,
            response_format={"type": "json_object"},  # Force JSON response from OpenAI
        )
        
        # Log the response for debugging
        logger.debug("LLM response content length: %d", len(response.content))
        
        if not response.content or not response.content.strip():
            raise ValueError("LLM returned empty response")
        
        return response.content

    def _parse_diagnosis(self, llm_output: dict, context: dict) -> Diagnosis:
        """Parse LLM JSON response into a Diagnosis object."""
        # Parse category
        category_str = llm_output.get("category", "unknown")
        try:
            category = DiagnosisCategory(category_str)
        except ValueError:
            category = DiagnosisCategory.UNKNOWN

        # Parse suggested actions
        actions = []
        for action_data in llm_output.get("suggested_actions", []):
            actions.append(
                Action(
                    description=action_data.get("description", ""),
                    priority=action_data.get("priority", "medium"),
                    automated=action_data.get("automated", False),
                )
            )

        # Add evidence from context
        evidence = context.get("metrics", [])

        # Build Diagnosis
        diagnosis = Diagnosis(
            root_cause=llm_output.get("root_cause", "Unknown"),
            category=category,
            confidence=float(llm_output.get("confidence", 0.5)),
            evidence=evidence,
            affected_components=llm_output.get("affected_components", []),
            suggested_actions=actions,
            similar_incidents=[
                inc["id"] for inc in context.get("similar_incidents", [])
            ],
            reasoning=llm_output.get("reasoning", ""),
        )

        return diagnosis

    async def close(self):
        """Cleanup resources."""
        await self.context_gatherer.close()