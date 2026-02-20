"""Base detector interface for anomaly detection strategies."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AnomalyScore(str, Enum):
    """Anomaly severity levels."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MetricPoint:
    """Single time-series data point."""
    timestamp: datetime
    value: float
    metric_name: str
    labels: dict[str, str]


@dataclass
class AnomalyResult:
    """Result of anomaly detection."""
    is_anomaly: bool
    score: float  # 0.0 to 1.0
    severity: AnomalyScore
    confidence: float  # 0.0 to 1.0
    detector_name: str
    metric_name: str
    actual_value: float
    expected_range: tuple[float, float] | None = None
    explanation: str = ""


class BaseDetector(ABC):
    """Abstract base class for anomaly detectors."""
    
    def __init__(self, threshold: float = 0.7, name: str | None = None):
        """
        Initialize detector.
        
        Args:
            threshold: Anomaly score threshold (0.0-1.0)
            name: Detector name for identification
        """
        self.threshold = threshold
        self.name = name or self.__class__.__name__
    
    @abstractmethod
    async def fit(self, data: list[MetricPoint]) -> None:
        """
        Train/fit the detector on historical data.
        
        Args:
            data: Historical metric points for training
        """
        pass
    
    @abstractmethod
    async def detect(self, point: MetricPoint) -> AnomalyResult:
        """
        Detect if a single point is anomalous.
        
        Args:
            point: Current metric point to check
            
        Returns:
            AnomalyResult with detection details
        """
        pass
    
    @abstractmethod
    async def detect_batch(self, points: list[MetricPoint]) -> list[AnomalyResult]:
        """
        Detect anomalies in a batch of points.
        
        Args:
            points: List of metric points to check
            
        Returns:
            List of AnomalyResults
        """
        pass
    
    def _calculate_severity(self, score: float) -> AnomalyScore:
        """Calculate severity level from anomaly score."""
        if score < self.threshold:
            return AnomalyScore.NORMAL
        elif score < 0.85:
            return AnomalyScore.WARNING
        else:
            return AnomalyScore.CRITICAL