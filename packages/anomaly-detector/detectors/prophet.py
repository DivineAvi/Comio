"""Facebook Prophet based anomaly detector."""
import numpy as np
import pandas as pd
from prophet import Prophet
from datetime import timedelta

try:
    from .base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore
except ImportError:
    from base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore


class ProphetDetector(BaseDetector):
    """
    Anomaly detection using Facebook Prophet.
    
    Prophet is designed for business time-series with:
    - Multiple seasonality (daily, weekly, yearly)
    - Holiday effects
    - Trend changes
    - Missing data tolerance
    
    Best for production metrics with complex patterns.
    """
    
    def __init__(
        self,
        threshold: float = 0.7,
        interval_width: float = 0.95,
        changepoint_prior_scale: float = 0.05,
    ):
        """
        Initialize Prophet detector.
        
        Args:
            threshold: Anomaly score threshold
            interval_width: Uncertainty interval width (0.95 = 95% confidence)
            changepoint_prior_scale: Trend flexibility (higher = more flexible)
        """
        super().__init__(threshold, name="Prophet")
        self.interval_width = interval_width
        self.changepoint_prior_scale = changepoint_prior_scale
        self.model: Prophet | None = None
        self.fitted = False
        self.uncertainty_std: float | None = None
    
    async def fit(self, data: list[MetricPoint]) -> None:
        """Train Prophet model on historical data."""
        if len(data) < 48:  # At least 2 days of hourly data
            raise ValueError(
                f"Prophet needs at least 48 points (2 days) for training "
                f"(got {len(data)})"
            )
        
        # Sort by timestamp
        sorted_data = sorted(data, key=lambda p: p.timestamp)
        
        # Create DataFrame in Prophet format (ds, y)
        df = pd.DataFrame({
            'ds': [p.timestamp for p in sorted_data],
            'y': [p.value for p in sorted_data],
        })
        
        # Initialize Prophet with custom settings
        self.model = Prophet(
            interval_width=self.interval_width,
            changepoint_prior_scale=self.changepoint_prior_scale,
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,  # Need at least 1 year of data for this
            seasonality_mode='additive',
            uncertainty_samples=100,
        )
        
        # Suppress Prophet's verbose output
        import logging
        logging.getLogger('prophet').setLevel(logging.WARNING)
        
        # Fit model
        self.model.fit(df)
        
        # Calculate uncertainty std from training data
        forecast = self.model.predict(df)
        forecast['residual'] = df['y'] - forecast['yhat']
        self.uncertainty_std = float(forecast['residual'].std())
        
        self.fitted = True
    
    async def detect(self, point: MetricPoint) -> AnomalyResult:
        """Detect anomaly using Prophet forecast."""
        if not self.fitted or self.model is None:
            raise ValueError("Detector not fitted. Call fit() first.")
        
        # Create future DataFrame for this point
        future = pd.DataFrame({'ds': [point.timestamp]})
        
        # Make prediction
        forecast = self.model.predict(future)
        
        # Extract prediction and uncertainty bounds
        yhat = float(forecast['yhat'].iloc[0])  # Predicted value
        yhat_lower = float(forecast['yhat_lower'].iloc[0])  # Lower bound
        yhat_upper = float(forecast['yhat_upper'].iloc[0])  # Upper bound
        
        # Calculate how far outside the prediction interval
        if point.value < yhat_lower:
            deviation = yhat_lower - point.value
            direction = "below"
        elif point.value > yhat_upper:
            deviation = point.value - yhat_upper
            direction = "above"
        else:
            deviation = 0.0
            direction = "within"
        
        # Normalize deviation to score (0-1)
        if self.uncertainty_std and self.uncertainty_std > 0:
            score = min(1.0, deviation / (3 * self.uncertainty_std))
        else:
            score = 1.0 if deviation > 0 else 0.0
        
        is_anomaly = point.value < yhat_lower or point.value > yhat_upper
        severity = self._calculate_severity(score)
        
        day_name = point.timestamp.strftime("%A")
        time_str = point.timestamp.strftime("%H:%M")
        
        explanation = (
            f"Value {point.value:.2f} at {time_str} on {day_name}. "
            f"Prophet predicted: {yhat:.2f} "
            f"(95% interval: [{yhat_lower:.2f}, {yhat_upper:.2f}]). "
            f"Actual is {direction} forecast."
        )
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=score,
            severity=severity,
            confidence=0.90,  # Prophet is highly confident with good training data
            detector_name=self.name,
            metric_name=point.metric_name,
            actual_value=point.value,
            expected_range=(yhat_lower, yhat_upper),
            explanation=explanation,
        )
    
    async def detect_batch(self, points: list[MetricPoint]) -> list[AnomalyResult]:
        """Detect anomalies in batch (more efficient with Prophet)."""
        if not self.fitted or self.model is None:
            raise ValueError("Detector not fitted. Call fit() first.")
        
        # Create future DataFrame for all points
        future = pd.DataFrame({'ds': [p.timestamp for p in points]})
        
        # Make predictions for all points at once
        forecast = self.model.predict(future)
        
        # Build results
        results = []
        for i, point in enumerate(points):
            yhat = float(forecast['yhat'].iloc[i])
            yhat_lower = float(forecast['yhat_lower'].iloc[i])
            yhat_upper = float(forecast['yhat_upper'].iloc[i])
            
            if point.value < yhat_lower:
                deviation = yhat_lower - point.value
                direction = "below"
            elif point.value > yhat_upper:
                deviation = point.value - yhat_upper
                direction = "above"
            else:
                deviation = 0.0
                direction = "within"
            
            if self.uncertainty_std and self.uncertainty_std > 0:
                score = min(1.0, deviation / (3 * self.uncertainty_std))
            else:
                score = 1.0 if deviation > 0 else 0.0
            
            is_anomaly = point.value < yhat_lower or point.value > yhat_upper
            severity = self._calculate_severity(score)
            
            day_name = point.timestamp.strftime("%A")
            time_str = point.timestamp.strftime("%H:%M")
            
            results.append(AnomalyResult(
                is_anomaly=is_anomaly,
                score=score,
                severity=severity,
                confidence=0.90,
                detector_name=self.name,
                metric_name=point.metric_name,
                actual_value=point.value,
                expected_range=(yhat_lower, yhat_upper),
                explanation=(
                    f"Value {point.value:.2f} at {time_str} on {day_name}. "
                    f"Prophet predicted: {yhat:.2f} "
                    f"(95% interval: [{yhat_lower:.2f}, {yhat_upper:.2f}]). "
                    f"Actual is {direction} forecast."
                ),
            ))
        
        return results