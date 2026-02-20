"""Isolation Forest based anomaly detector."""
import numpy as np
from sklearn.ensemble import IsolationForest

try:
    from .base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore
except ImportError:
    from base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore


class IsolationForestDetector(BaseDetector):
    """
    Anomaly detection using Isolation Forest algorithm.
    
    Good at detecting outliers in multi-dimensional data.
    Does not assume normal distribution.
    """
    
    def __init__(
        self,
        threshold: float = 0.7,
        contamination: float = 0.05,
        n_estimators: int = 100,
    ):
        """
        Initialize Isolation Forest detector.
        
        Args:
            threshold: Anomaly score threshold
            contamination: Expected proportion of outliers (0.0-0.5)
            n_estimators: Number of trees in the forest
        """
        super().__init__(threshold, name="IsolationForest")
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.model: IsolationForest | None = None
        self.fitted = False
    
    async def fit(self, data: list[MetricPoint]) -> None:
        """Train Isolation Forest on historical data."""
        if not data or len(data) < 10:
            raise ValueError("Need at least 10 points to train Isolation Forest")
        
        # Extract features: value + time-based features
        X = self._extract_features(data)
        
        # Train model
        self.model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=42,
            n_jobs=-1,  # Use all CPU cores
        )
        self.model.fit(X)
        self.fitted = True
    
    def _extract_features(self, points: list[MetricPoint]) -> np.ndarray:
        """
        Extract features from metric points.
        
        Features:
        - value (normalized)
        - hour of day (cyclical)
        - day of week (cyclical)
        """
        features = []
        for point in points:
            hour = point.timestamp.hour
            day_of_week = point.timestamp.weekday()
            
            features.append([
                point.value,
                np.sin(2 * np.pi * hour / 24),  # Hour (cyclical)
                np.cos(2 * np.pi * hour / 24),
                np.sin(2 * np.pi * day_of_week / 7),  # Day (cyclical)
                np.cos(2 * np.pi * day_of_week / 7),
            ])
        
        return np.array(features)
    
    async def detect(self, point: MetricPoint) -> AnomalyResult:
        """Detect anomaly using Isolation Forest."""
        if not self.fitted or self.model is None:
            raise ValueError("Detector not fitted. Call fit() first.")
        
        # Extract features
        X = self._extract_features([point])
        
        # Predict (-1 = anomaly, 1 = normal)
        prediction = self.model.predict(X)[0]
        is_anomaly = prediction == -1
        
        # Get anomaly score (more negative = more anomalous)
        anomaly_score_raw = self.model.decision_function(X)[0]
        
        # Normalize to 0-1 (decision_function returns negative values for anomalies)
        # Typically ranges from -0.5 to 0.5
        score = max(0.0, min(1.0, -anomaly_score_raw + 0.5))
        
        severity = self._calculate_severity(score)
        
        explanation = (
            f"Isolation Forest score: {anomaly_score_raw:.3f}. "
            f"Value {point.value:.2f} at {point.timestamp.strftime('%H:%M on %A')}. "
            f"{'Anomalous' if is_anomaly else 'Normal'} pattern."
        )
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=score,
            severity=severity,
            confidence=0.85,  # IF is quite confident
            detector_name=self.name,
            metric_name=point.metric_name,
            actual_value=point.value,
            expected_range=None,  # IF doesn't give explicit ranges
            explanation=explanation,
        )
    
    async def detect_batch(self, points: list[MetricPoint]) -> list[AnomalyResult]:
        """Detect anomalies in batch."""
        return [await self.detect(point) for point in points]