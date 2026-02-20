"""Anomaly detection pipeline with ensemble voting."""
import logging
from typing import Any

try:
    from .detectors.base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore
except ImportError:
    from detectors.base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore

logger = logging.getLogger(__name__)


class AnomalyPipeline:
    """
    Ensemble anomaly detection pipeline.
    
    Combines multiple detectors using weighted voting to reduce false positives
    and improve detection accuracy.
    """
    
    def __init__(
        self,
        detectors: list[BaseDetector],
        weights: list[float] | None = None,
        ensemble_threshold: float = 0.6,
    ):
        """
        Initialize pipeline.
        
        Args:
            detectors: List of detector instances
            weights: Weight for each detector (defaults to equal weights)
            ensemble_threshold: Final score threshold for alerting
        """
        if not detectors:
            raise ValueError("At least one detector is required")
        
        self.detectors = detectors
        
        # Default to equal weights if not specified
        if weights is None:
            self.weights = [1.0 / len(detectors)] * len(detectors)
        else:
            if len(weights) != len(detectors):
                raise ValueError("Number of weights must match number of detectors")
            # Normalize weights to sum to 1.0
            total = sum(weights)
            self.weights = [w / total for w in weights]
        
        self.ensemble_threshold = ensemble_threshold
    
    async def fit_all(self, training_data: list[MetricPoint]) -> None:
        """
        Train all detectors on historical data.
        
        Args:
            training_data: Historical metric points for training
        """
        if not training_data:
            raise ValueError("Training data cannot be empty")
        
        logger.info("Training %d detectors on %d data points", len(self.detectors), len(training_data))
        
        for detector in self.detectors:
            try:
                await detector.fit(training_data)
                logger.info("✓ %s trained successfully", detector.name)
            except Exception as e:
                logger.error("✗ Failed to train %s: %s", detector.name, e)
                raise
    
    async def detect(self, point: MetricPoint) -> tuple[AnomalyResult, list[AnomalyResult]]:
        """
        Run ensemble detection on a single point.
        
        Args:
            point: Current metric point to analyze
            
        Returns:
            Tuple of (ensemble_result, individual_results)
        """
        individual_results = []
        
        # Run all detectors
        for detector in self.detectors:
            try:
                result = await detector.detect(point)
                individual_results.append(result)
            except Exception as e:
                logger.error("Detector %s failed: %s", detector.name, e)
                # Continue with other detectors
        
        if not individual_results:
            raise RuntimeError("All detectors failed")
        
        # Ensemble voting: weighted average of scores
        ensemble_result = self._compute_ensemble(point, individual_results)
        
        return ensemble_result, individual_results
    
    async def detect_batch(
        self,
        points: list[MetricPoint],
    ) -> list[tuple[AnomalyResult, list[AnomalyResult]]]:
        """
        Run ensemble detection on multiple points.
        
        Args:
            points: List of metric points to analyze
            
        Returns:
            List of (ensemble_result, individual_results) tuples
        """
        return [await self.detect(point) for point in points]
    
    def _compute_ensemble(
        self,
        point: MetricPoint,
        individual_results: list[AnomalyResult],
    ) -> AnomalyResult:
        """
        Compute ensemble result from individual detector results.
        
        Uses weighted voting based on detector scores and confidences.
        """
        # Weighted average of scores
        ensemble_score = sum(
            result.score * weight * result.confidence
            for result, weight in zip(individual_results, self.weights)
        )
        
        # Weighted average of confidences
        ensemble_confidence = sum(
            result.confidence * weight
            for result, weight in zip(individual_results, self.weights)
        )
        
        # Count how many detectors flagged as anomaly
        anomaly_count = sum(1 for r in individual_results if r.is_anomaly)
        
        # Final decision: threshold on ensemble score
        is_anomaly = ensemble_score >= self.ensemble_threshold
        
        # Calculate severity
        if ensemble_score < self.ensemble_threshold:
            severity = AnomalyScore.NORMAL
        elif ensemble_score < 0.8:
            severity = AnomalyScore.WARNING
        else:
            severity = AnomalyScore.CRITICAL
        
        # Build explanation
        detector_votes = [
            f"{r.detector_name}: {r.score:.2f} ({'✓' if r.is_anomaly else '✗'})"
            for r in individual_results
        ]
        
        explanation = (
            f"Ensemble score: {ensemble_score:.2f} "
            f"({anomaly_count}/{len(individual_results)} detectors agree). "
            f"Votes: {', '.join(detector_votes)}"
        )
        
        # Aggregate expected ranges (use most conservative)
        expected_ranges = [r.expected_range for r in individual_results if r.expected_range]
        if expected_ranges:
            min_lower = min(r[0] for r in expected_ranges)
            max_upper = max(r[1] for r in expected_ranges)
            expected_range = (min_lower, max_upper)
        else:
            expected_range = None
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=ensemble_score,
            severity=severity,
            confidence=ensemble_confidence,
            detector_name="Ensemble",
            metric_name=point.metric_name,
            actual_value=point.value,
            expected_range=expected_range,
            explanation=explanation,
        )