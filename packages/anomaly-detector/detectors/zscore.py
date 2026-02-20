"""Z-Score based anomaly detector (statistical baseline)."""
import numpy as np

try:
    from .base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore
except ImportError:
    from base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore


class ZScoreDetector(BaseDetector):
    """
    Simple statistical anomaly detection using Z-score.
    
    Detects points that are more than N standard deviations from the mean.
    Fast and simple, good baseline detector.
    """
    
    def __init__(self, threshold: float = 0.7, z_threshold: float = 3.0):
        """
        Initialize Z-Score detector.
        
        Args:
            threshold: Anomaly score threshold
            z_threshold: Number of standard deviations for anomaly (default: 3)
        """
        super().__init__(threshold, name="ZScore")
        self.z_threshold = z_threshold
        self.mean: float | None = None
        self.std: float | None = None
        self.min_val: float | None = None
        self.max_val: float | None = None
    
    async def fit(self, data: list[MetricPoint]) -> None:
        """Calculate mean and std from historical data."""
        if not data:
            raise ValueError("Cannot fit with empty data")
        
        values = np.array([p.value for p in data])
        
        self.mean = float(np.mean(values))
        self.std = float(np.std(values))
        self.min_val = float(np.min(values))
        self.max_val = float(np.max(values))
        
        # Avoid division by zero
        if self.std < 1e-6:
            self.std = 1.0
    
    async def detect(self, point: MetricPoint) -> AnomalyResult:
        """Detect anomaly using Z-score."""
        if self.mean is None or self.std is None:
            raise ValueError("Detector not fitted. Call fit() first.")
        
        # Calculate Z-score
        z_score = abs(point.value - self.mean) / self.std
        
        # Normalize to 0-1 score (sigmoid-like)
        # score = 0 at z=0, score → 1 as z → infinity
        score = min(1.0, z_score / (self.z_threshold * 2))
        
        is_anomaly = z_score > self.z_threshold
        severity = self._calculate_severity(score)
        
        # Calculate expected range
        expected_min = self.mean - self.z_threshold * self.std
        expected_max = self.mean + self.z_threshold * self.std
        
        explanation = (
            f"Value {point.value:.2f} is {z_score:.2f} std devs from mean {self.mean:.2f} "
            f"(std: {self.std:.2f}). Expected range: [{expected_min:.2f}, {expected_max:.2f}]"
        )
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=score,
            severity=severity,
            confidence=min(0.9, score),  # Z-score is fairly confident but not perfect
            detector_name=self.name,
            metric_name=point.metric_name,
            actual_value=point.value,
            expected_range=(expected_min, expected_max),
            explanation=explanation,
        )
    
    async def detect_batch(self, points: list[MetricPoint]) -> list[AnomalyResult]:
        """Detect anomalies in batch."""
        return [await self.detect(point) for point in points]