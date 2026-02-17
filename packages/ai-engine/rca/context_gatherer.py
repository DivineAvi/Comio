"""Context gatherer — collects evidence for RCA analysis.

The RCA engine needs context to make good diagnoses:
- Metrics: error rate, latency, resource usage
- Recent deploys: did new code cause this?
- Similar incidents: have we seen this before?
- RAG retrieval: relevant runbooks and documentation
- Logs: what errors were logged? (future)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.incident import Incident
from .schemas import Evidence

logger = logging.getLogger(__name__)


class ContextGatherer:
    """Gathers contextual data for RCA analysis."""

    def __init__(
        self, 
        prometheus_url: str = "http://localhost:9090",
        enable_rag: bool = True,
    ):
        self.prometheus_url = prometheus_url
        self.enable_rag = enable_rag
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def gather_context(
        self,
        db: AsyncSession,
        incident: Incident,
    ) -> dict[str, Any]:
        """Gather all relevant context for diagnosing this incident.

        Returns a dictionary with:
        - metrics: Recent metrics around incident time
        - recent_deploys: Any deploys in the last hour
        - similar_incidents: Past incidents with same symptoms
        - alert_data: The original alert that triggered this
        """
        context = {
            "incident_id": str(incident.id),
            "title": incident.title,
            "severity": incident.severity.value,
            "created_at": incident.created_at.isoformat(),
            "project_id": str(incident.project_id),
            "alert_data": incident.alert_data,
            "metrics": [],
            "recent_deploys": [],
            "similar_incidents": [],
            "rag_context": [],  # Retrieved runbooks and documentation
        }

        # Gather metrics from Prometheus
        metrics = await self._fetch_metrics(incident)
        context["metrics"] = metrics

        # Find similar past incidents
        similar = await self._find_similar_incidents(db, incident)
        context["similar_incidents"] = similar

        # Retrieve relevant context from RAG (runbooks, past resolutions)
        if self.enable_rag:
            rag_results = await self._retrieve_rag_context(db, incident)
            context["rag_context"] = rag_results

        # TODO: Fetch recent deploys from GitHub (Day 12+)
        # TODO: Fetch logs from Loki (Day 12+)

        return context

    async def _fetch_metrics(self, incident: Incident) -> list[Evidence]:
        """Fetch relevant metrics from Prometheus around incident time."""
        evidence = []

        try:
            # Extract project_id and service from alert labels
            alert_data = incident.alert_data or {}
            labels = alert_data.get("payload", {}).get("labels", {})
            job = labels.get("job", "demo-app")
            project_id = labels.get("comio_project_id", "")

            # Time window: 5 minutes before and after incident
            incident_time = incident.created_at
            start_time = incident_time - timedelta(minutes=5)
            end_time = incident_time + timedelta(minutes=2)

            # Query error rate
            error_rate_query = f'rate(http_requests_total{{status_code=~"5..",job="{job}"}}[1m]) / rate(http_requests_total{{job="{job}"}}[1m])'
            error_rate = await self._query_prometheus(error_rate_query, end_time)
            if error_rate is not None:
                evidence.append(
                    Evidence(
                        type="metric",
                        source="prometheus",
                        description="Error rate at incident time",
                        value=float(error_rate),
                        timestamp=end_time.isoformat(),
                    )
                )

            # Query P95 latency
            latency_query = f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{job="{job}"}}[1m]))'
            latency = await self._query_prometheus(latency_query, end_time)
            if latency is not None:
                evidence.append(
                    Evidence(
                        type="metric",
                        source="prometheus",
                        description="P95 latency at incident time",
                        value=float(latency),
                        timestamp=end_time.isoformat(),
                    )
                )

            # Query request rate
            request_rate_query = f'rate(http_requests_total{{job="{job}"}}[1m])'
            request_rate = await self._query_prometheus(request_rate_query, end_time)
            if request_rate is not None:
                evidence.append(
                    Evidence(
                        type="metric",
                        source="prometheus",
                        description="Request rate (req/sec) at incident time",
                        value=float(request_rate),
                        timestamp=end_time.isoformat(),
                    )
                )

            logger.info(
                "Gathered %d metric evidence items for incident %s",
                len(evidence),
                incident.id,
            )

        except Exception as e:
            logger.error("Error fetching metrics from Prometheus: %s", e)

        return evidence

    async def _query_prometheus(
        self, query: str, timestamp: datetime
    ) -> float | None:
        """Execute a PromQL query at a specific time."""
        try:
            url = f"{self.prometheus_url}/api/v1/query"
            params = {
                "query": query,
                "time": timestamp.isoformat(),
            }

            response = await self.http_client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            if data["status"] == "success" and data["data"]["result"]:
                # Extract the value from the first result
                result = data["data"]["result"][0]
                value = result["value"][1]  # [timestamp, value]
                return float(value)

        except Exception as e:
            logger.debug("Prometheus query failed: %s", e)

        return None

    async def _find_similar_incidents(
        self, db: AsyncSession, incident: Incident
    ) -> list[dict]:
        """Find past incidents with similar symptoms (same project + title)."""
        try:
            # Find incidents in same project with same title
            result = await db.execute(
                select(Incident)
                .where(
                    Incident.project_id == incident.project_id,
                    Incident.title == incident.title,
                    Incident.id != incident.id,  # Exclude current incident
                )
                .order_by(Incident.created_at.desc())
                .limit(5)
            )
            similar = result.scalars().all()

            return [
                {
                    "id": str(inc.id),
                    "title": inc.title,
                    "severity": inc.severity.value,
                    "status": inc.status.value,
                    "created_at": inc.created_at.isoformat(),
                    "had_diagnosis": inc.diagnosis is not None,
                }
                for inc in similar
            ]

        except Exception as e:
            logger.error("Error finding similar incidents: %s", e)
            return []

    async def _retrieve_rag_context(
        self,
        db: AsyncSession,
        incident: Incident,
    ) -> list[dict]:
        """Retrieve relevant context from RAG (runbooks, documentation).
        
        Uses the incident title and description to search for relevant
        runbooks and past incident resolutions.
        """
        try:
            from rag import RAGRetriever
            from apps.api.config import settings

            # Build query from incident details
            query = f"{incident.title}. {incident.description or ''}"
            
            # Get API key for embeddings
            api_key = settings.openai_api_key
            if not api_key:
                logger.warning("No OpenAI API key configured, skipping RAG retrieval")
                return []

            retriever = RAGRetriever(
                embedding_provider="openai",
                embedding_model="text-embedding-3-small",
            )

            # Retrieve relevant runbooks and incident reports
            results = await retriever.retrieve(
                db=db,
                query=query,
                api_key=api_key,
                top_k=3,  # Get top 3 most relevant chunks
                content_types=["runbook", "incident"],  # Only runbooks and past incidents
                project_id=str(incident.project_id),
            )

            logger.info(
                "Retrieved %d RAG context items for incident %s",
                len(results),
                incident.id,
            )

            return results

        except Exception as e:
            logger.error("Error retrieving RAG context: %s", e)
            return []

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()