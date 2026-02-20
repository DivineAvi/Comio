"""Seasonal decomposition based anomaly detector."""
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import seasonal_decompose
from datetime import timedelta

try:
    from .base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore
except ImportError:
    from base import BaseDetector, MetricPoint, AnomalyResult, AnomalyScore


class SeasonalDetector(BaseDetector):
    """
    Anomaly detection using seasonal decomposition.
    
    Decomposes time-series into:
    - Trend: Long-term direction
    - Seasonal: Repeating patterns (daily/weekly)
    - Residual: What's left (where anomalies hide)
    
    Good for metrics with strong daily/weekly cycles.
    """
    
    def __init__(
        self,
        threshold: float = 0.7,
        period: int = 24,  # 24 hours for daily seasonality
        model: str = "additive",
    ):
        """
        Initialize Seasonal detector.
        
        Args:
            threshold: Anomaly score threshold
            period: Seasonal period (24 for hourly data with daily pattern)
            model: "additive" or "multiplicative"
        """
        super().__init__(threshold, name="Seasonal")
        self.period = period
        self.model = model
        self.seasonal_component: pd.Series | None = None
        self.trend_component: pd.Series | None = None
        self.residual_std: float | None = None
        self.residual_mean: float | None = None
        self.fitted = False
    
    async def fit(self, data: list[MetricPoint]) -> None:
        """Decompose time-series into seasonal components."""
        if len(data) < self.period * 2:
            raise ValueError(
                f"Need at least {self.period * 2} points for seasonal decomposition "
                f"(got {len(data)})"
            )
        
        # Sort by timestamp
        sorted_data = sorted(data, key=lambda p: p.timestamp)
        
        # Create pandas series
        timestamps = [p.timestamp for p in sorted_data]
        values = [p.value for p in sorted_data]
        series = pd.Series(values, index=pd.DatetimeIndex(timestamps))
        
        # Resample to ensure regular intervals (fill gaps with interpolation)
        series = series.resample('1h').mean().interpolate(method='linear')
        
        # Perform seasonal decomposition
        try:
            decomposition = seasonal_decompose(
                series,
                model=self.model,
                period=self.period,
                extrapolate_trend='freq',
            )
            
            self.seasonal_component = decomposition.seasonal
            self.trend_component = decomposition.trend
            
            # Calculate statistics on residuals
            residuals = decomposition.resid.dropna()
            self.residual_mean = float(residuals.mean())
            self.residual_std = float(residuals.std())
            
            # Avoid division by zero
            if self.residual_std < 1e-6:
                self.residual_std = 1.0
            
            self.fitted = True
            
        except Exception as e:
            raise ValueError(f"Seasonal decomposition failed: {e}")
    
    async def detect(self, point: MetricPoint) -> AnomalyResult:
        """Detect anomaly by analyzing residual component."""
        if not self.fitted:
            raise ValueError("Detector not fitted. Call fit() first.")
        
        # Get seasonal component for this time
        hour_of_day = point.timestamp.hour
        day_of_week = point.timestamp.weekday()
        
        # Find matching seasonal pattern (same hour and day of week)
        # Since seasonal component is periodic, we can wrap around
        seasonal_idx = (day_of_week * 24 + hour_of_day) % len(self.seasonal_component)
        expected_seasonal = float(self.seasonal_component.iloc[seasonal_idx])
        
        # Estimate trend (use last known trend value)
        expected_trend = float(self.trend_component.iloc[-1])
        
        # Calculate expected value
        if self.model == "additive":
            expected_value = expected_trend + expected_seasonal
            residual = point.value - expected_value
        else:  # multiplicative
            expected_value = expected_trend * expected_seasonal
            residual = point.value / expected_value if expected_value != 0 else point.value
        
        # Calculate Z-score of residual
        z_score = abs(residual - self.residual_mean) / self.residual_std
        
        # Normalize to 0-1 score
        score = min(1.0, z_score / 6.0)  # 6 sigma = score of 1.0
        
        is_anomaly = z_score > 3.0
        severity = self._calculate_severity(score)
        
        # Calculate expected range
        margin = 3 * self.residual_std
        if self.model == "additive":
            expected_min = expected_value - margin
            expected_max = expected_value + margin
        else:
            expected_min = expected_value * (1 - margin / expected_value)
            expected_max = expected_value * (1 + margin / expected_value)
        
        day_name = point.timestamp.strftime("%A")
        explanation = (
            f"Value {point.value:.2f} at {hour_of_day}:00 on {day_name}. "
            f"Expected: {expected_value:.2f} (trend: {expected_trend:.2f}, "
            f"seasonal: {expected_seasonal:.2f}). "
            f"Residual Z-score: {z_score:.2f}"
        )
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=score,
            severity=severity,
            confidence=0.80,  # Seasonal is quite reliable for cyclic patterns
            detector_name=self.name,
            metric_name=point.metric_name,
            actual_value=point.value,
            expected_range=(expected_min, expected_max),
            explanation=explanation,
        )
    
    async def detect_batch(self, points: list[MetricPoint]) -> list[AnomalyResult]:
        """Detect anomalies in batch."""
        return [await self.detect(point) for point in points]