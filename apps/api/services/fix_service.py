"""Service: generate fix from diagnosis and create Remediation."""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.config import settings
from apps.api.models.incident import Incident, Remediation, RemediationStatus

logger = logging.getLogger(__name__)


async def generate_fix_for_incident(
    db: AsyncSession,
    incident_id: UUID,
    code_context: dict[str, str] | None = None,
) -> Remediation:
    """
    Load incident + diagnosis, run FixGenerator, create Remediation.
    Caller must commit the session.
    """
    from fix_generator import FixGenerator

    result = await db.execute(
        select(Incident)
        .where(Incident.id == incident_id)
        .options(
            selectinload(Incident.diagnosis),
            selectinload(Incident.remediation),
        )
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise ValueError(f"Incident {incident_id} not found")
    if not incident.diagnosis:
        raise ValueError(f"Incident {incident_id} has no diagnosis; run RCA first")
    if incident.remediation:
        raise ValueError(f"Incident {incident_id} already has a remediation")

    diagnosis = incident.diagnosis
    diagnosis_summary = {
        "root_cause": diagnosis.root_cause,
        "category": diagnosis.category,
        "confidence": diagnosis.confidence,
        "reasoning": diagnosis.explanation,
        "suggested_actions": diagnosis.suggested_actions or [],
    }

    generator = FixGenerator(
        llm_provider=settings.default_llm_provider,
        llm_model=settings.default_llm_model,
    )
    fix_result = await generator.generate(diagnosis_summary, code_context)

    explanation = fix_result.explanation
    if fix_result.test_suggestions:
        explanation += "\n\n**Test suggestions:** " + "; ".join(fix_result.test_suggestions)

    remediation = Remediation(
        incident_id=incident.id,
        fix_type=fix_result.fix_type,
        diff=fix_result.diff,
        files_changed=fix_result.files_changed,
        explanation=explanation,
        risk_level=fix_result.risk_level,
        status=RemediationStatus.PENDING,
    )
    db.add(remediation)
    logger.info("Created remediation for incident %s (fix_type=%s)", incident_id, fix_result.fix_type)
    return remediation
