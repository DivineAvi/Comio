"""Background worker for periodic anomaly detection."""
import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import json
import redis.asyncio as redis
from typing import Any

from .metric_fetcher import MetricFetcher
from .pipeline import AnomalyPipeline
from .detectors import (
    ZScoreDetector,
    IsolationForestDetector,
    SeasonalDetector,
    ProphetDetector,
)

logger = logging.getLogger(__name__)


class AnomalyWorker:
    """
    Background worker for continuous anomaly detection.
    
    Periodically fetches metrics, runs detection, and emits alerts
    when anomalies are found.
    """
    
    def __init__(
        self,
        prometheus_url: str,
        redis_url: str,
        event_bus: Any,  # BaseEventBus type
        check_interval_minutes: int = 5,
        training_lookback_hours: int = 168,  # 1 week
    ):
        """
        Initialize worker.
        
        Args:
            prometheus_url: Prometheus server URL
            redis_url: Redis URL for caching model state
            event_bus: Event bus for publishing alerts
            check_interval_minutes: How often to check for anomalies
            training_lookback_hours: Historical data for training (default: 1 week)
        """
        self.prometheus_url = prometheus_url
        self.redis_url = redis_url
        self.event_bus = event_bus
        self.check_interval_minutes = check_interval_minutes
        self.training_lookback_hours = training_lookback_hours
        
        self.metric_fetcher = MetricFetcher(prometheus_url)
        self.scheduler = AsyncIOScheduler()
        self.redis_client: redis.Redis | None = None
        self.pipeline: AnomalyPipeline | None = None
        
        # Metrics to monitor (PromQL queries)
        self.monitored_queries = [
            'rate(http_requests_total{job="demo-app"}[5m])',
            'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="demo-app"}[5m]))',
            'rate(http_requests_total{job="demo-app",status=~"5.."}[5m])',
            'process_resident_memory_bytes{job="demo-app"}',
        ]
        
        self._running = False
    
    async def start(self) -> None:
        """Start the background worker."""
        if self._running:
            logger.warning("Worker already running")
            return
        
        logger.info("Starting anomaly detection worker...")
        
        # Connect to Redis
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        await self.redis_client.ping()
        logger.info("Connected to Redis")
        
        # Initialize pipeline with all detectors
        self.pipeline = AnomalyPipeline(
            detectors=[
                ZScoreDetector(threshold=0.7),
                IsolationForestDetector(threshold=0.7, contamination=0.05),
                SeasonalDetector(threshold=0.7, period=24),
                ProphetDetector(threshold=0.7),
            ],
            weights=[0.2, 0.3, 0.2, 0.3],  # Favor ML detectors slightly
            ensemble_threshold=0.65,
        )
        
        # Initial training
        await self._train_models()
        
        # Schedule periodic checks
        self.scheduler.add_job(
            self._check_for_anomalies,
            trigger=IntervalTrigger(minutes=self.check_interval_minutes),
            id="anomaly_check",
            name="Periodic Anomaly Check",
            replace_existing=True,
        )
        
        # Schedule daily retraining (at 2am)
        self.scheduler.add_job(
            self._train_models,
            trigger='cron',
            hour=2,
            minute=0,
            id="model_retrain",
            name="Daily Model Retraining",
            replace_existing=True,
        )
        
        self.scheduler.start()
        self._running = True
        
        logger.info(
            "Worker started. Checking every %d minutes.",
            self.check_interval_minutes,
        )
    
    async def stop(self) -> None:
        """Stop the background worker."""
        if not self._running:
            return
        
        logger.info("Stopping anomaly detection worker...")
        
        self.scheduler.shutdown(wait=True)
        
        if self.redis_client:
            await self.redis_client.aclose()
        
        await self.metric_fetcher.close()
        
        self._running = False
        logger.info("Worker stopped")
    
    async def _train_models(self) -> None:
        """Train all detection models on historical data."""
        logger.info("Training models on %d hours of historical data...", self.training_lookback_hours)
        
        try:
            # Fetch historical data for all monitored metrics
            metrics_data = await self.metric_fetcher.get_metrics_for_detection(
                queries=self.monitored_queries,
                lookback_hours=self.training_lookback_hours,
            )
            
            # Train pipeline on each metric separately
            for query, data_points in metrics_data.items():
                if len(data_points) < 50:
                    logger.warning("Not enough data for %s (got %d points)", query, len(data_points))
                    continue
                
                try:
                    await self.pipeline.fit_all(data_points)
                    
                    # Cache trained state in Redis
                    cache_key = f"anomaly_model:{query}"
                    cache_value = {
                        "trained_at": datetime.utcnow().isoformat(),
                        "data_points": len(data_points),
                        "query": query,
                    }
                    await self.redis_client.setex(
                        cache_key,
                        timedelta(days=1),
                        json.dumps(cache_value),
                    )
                    
                    logger.info("✓ Trained models for: %s", query)
                    
                except Exception as e:
                    logger.error("Failed to train for %s: %s", query, e)
            
            logger.info("Model training complete")
            
        except Exception as e:
            logger.error("Model training failed: %s", e)
    
    async def _check_for_anomalies(self) -> None:
        """Check current metrics for anomalies."""
        logger.debug("Running anomaly detection check...")
        
        try:
            # Fetch current metric values
            current_time = datetime.utcnow()
            
            for query in self.monitored_queries:
                # Get instant value
                points = await self.metric_fetcher.query_instant(query, current_time)
                
                if not points:
                    logger.debug("No data for query: %s", query)
                    continue
                
                # Run detection on each series
                for point in points:
                    try:
                        ensemble_result, individual_results = await self.pipeline.detect(point)
                        
                        # Log result
                        if ensemble_result.is_anomaly:
                            logger.warning(
                                "🚨 ANOMALY DETECTED: %s = %.2f (score: %.2f, severity: %s)",
                                point.metric_name,
                                point.value,
                                ensemble_result.score,
                                ensemble_result.severity.value,
                            )
                            logger.info("Details: %s", ensemble_result.explanation)
                            
                            # Publish alert event
                            await self._emit_alert(point, ensemble_result, individual_results)
                        else:
                            logger.debug(
                                "✓ Normal: %s = %.2f (score: %.2f)",
                                point.metric_name,
                                point.value,
                                ensemble_result.score,
                            )
                    
                    except Exception as e:
                        logger.error("Detection failed for %s: %s", point.metric_name, e)
        
        except Exception as e:
            logger.error("Anomaly check failed: %s", e)
    
    async def _emit_alert(
        self,
        point: Any,
        ensemble_result: Any,
        individual_results: list[Any],
    ) -> None:
        """
        Emit alert event when anomaly is detected.
        
        Creates an AlertEvent and publishes to the event bus,
        which will trigger incident creation and RCA.
        """
        # Import here to avoid circular dependency
        from events.schemas import AlertEvent, EventType
        
        # Map severity to alert severity
        severity_map = {
            "normal": "info",
            "warning": "warning",
            "critical": "critical",
        }
        
        # Build detailed description
        detector_details = "\n".join([
            f"- {r.detector_name}: {r.explanation}"
            for r in individual_results
        ])
        
        alert = AlertEvent(
            event_type=EventType.ALERT_RECEIVED,
            source="anomaly_detector",
            labels={
                "alertname": f"AnomalyDetected_{point.metric_name}",
                "severity": severity_map.get(ensemble_result.severity.value, "warning"),
                "metric": point.metric_name,
                **point.labels,
            },
            annotations={
                "summary": f"Anomaly detected in {point.metric_name}",
                "description": (
                    f"Ensemble anomaly detection (score: {ensemble_result.score:.2f}) "
                    f"flagged metric '{point.metric_name}' with value {point.value:.2f}.\n\n"
                    f"{ensemble_result.explanation}\n\n"
                    f"Individual Detector Results:\n{detector_details}"
                ),
                "value": str(point.value),
                "expected_range": str(ensemble_result.expected_range) if ensemble_result.expected_range else "N/A",
            },
            startsAt=point.timestamp.isoformat(),
        )
        
        # Publish to event bus
        try:
            await self.event_bus.publish("alert.received", alert)
            logger.info("Alert event published for %s", point.metric_name)
        except Exception as e:
            logger.error("Failed to publish alert: %s", e)