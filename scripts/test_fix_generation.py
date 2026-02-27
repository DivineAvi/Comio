"""Test fix generation with minimal LLM usage.

Seeds user, project, incident + diagnosis in DB (no LLM), then calls
generate_fix_for_incident() directly = 1 LLM call only.
Set COMIO_DEFAULT_LLM_MODEL=gpt-4o-mini to minimize tokens (optional).
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

root = Path(__file__).parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "packages" / "ai-engine"))

from sqlalchemy import select
from apps.api.database import async_session_factory
from apps.api.models.user import User
from apps.api.models.project import Project, ProjectOrigin, ProjectType
from apps.api.models.incident import Incident, Diagnosis, Severity, IncidentStatus
from apps.api.auth import hash_password


async def seed_and_generate():
    """Create user, project, incident, diagnosis; then run fix generation (1 LLM call)."""
    async with async_session_factory() as db:
        # Get or create test user
        r = await db.execute(select(User).where(User.email == "fix-test@comio.test"))
        user = r.scalar_one_or_none()
        if not user:
            user = User(
                email="fix-test@comio.test",
                hashed_password=hash_password("FixTestPass123!"),
                full_name="Fix Test",
            )
            db.add(user)
            await db.flush()

        # Get or create project
        r = await db.execute(select(Project).where(Project.owner_id == user.id, Project.name == "fix-test-project"))
        project = r.scalar_one_or_none()
        if not project:
            project = Project(
                name="fix-test-project",
                description="For fix generation test",
                origin=ProjectOrigin.CREATED,
                project_type=ProjectType.API,
                owner_id=user.id,
            )
            db.add(project)
            await db.flush()

        # Create incident + diagnosis (minimal text to keep prompt small)
        incident = Incident(
            project_id=project.id,
            title="High latency on /api/orders",
            description="P95 latency above 2s.",
            severity=Severity.HIGH,
            status=IncidentStatus.OPEN,
            source="manual_test",
            alert_data={},
        )
        db.add(incident)
        await db.flush()

        diagnosis = Diagnosis(
            incident_id=incident.id,
            root_cause="DB connection pool exhausted under load.",
            category="config",
            confidence=0.85,
            explanation="Metrics show pool saturation. Increase pool size or add timeouts.",
            suggested_actions=[
                {"description": "Increase DB pool size", "priority": "high", "automated": False},
            ],
        )
        db.add(diagnosis)
        await db.commit()
        incident_id = incident.id

    # Call fix service directly (1 LLM call; no code_context = smaller prompt)
    from apps.api.services.fix_service import generate_fix_for_incident

    async with async_session_factory() as db:
        remediation = await generate_fix_for_incident(db, incident_id, code_context=None)
        await db.commit()
        await db.refresh(remediation)

    print("OK: remediation created")
    print(f"  fix_type: {remediation.fix_type}")
    print(f"  risk_level: {remediation.risk_level}")
    print(f"  status: {remediation.status}")
    print(f"  explanation (first 250 chars): {(remediation.explanation or '')[:250]}...")
    return 0


def main():
    print("Fix generation test (1 LLM call, no code_context)")
    if os.environ.get("COMIO_DEFAULT_LLM_MODEL"):
        print(f"  Using model: {os.environ['COMIO_DEFAULT_LLM_MODEL']}")
    print()
    return asyncio.run(seed_and_generate())


if __name__ == "__main__":
    exit(main())