"""Test anomaly detection system."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

# Add anomaly-detector package to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "anomaly-detector"))

from detectors.base import MetricPoint
from detectors.zscore import ZScoreDetector
from detectors.isolation_forest import IsolationForestDetector
from detectors.seasonal import SeasonalDetector
from detectors.prophet import ProphetDetector
from pipeline import AnomalyPipeline


async def test_anomaly_detection():
    """Test the anomaly detection pipeline with synthetic data."""
    
    print("🔬 Testing Anomaly Detection System\n")
    print("=" * 80)
    
    # Generate synthetic training data: normal pattern with daily seasonality
    print("\n📊 Generating synthetic training data...")
    training_data = []
    base_time = datetime.utcnow() - timedelta(days=7)
    
    for hour in range(168):  # 7 days * 24 hours
        timestamp = base_time + timedelta(hours=hour)
        hour_of_day = timestamp.hour
        
        # Base value with daily pattern
        # High traffic during work hours (9am-5pm), low at night
        if 9 <= hour_of_day <= 17:
            base_value = 500.0
        elif 0 <= hour_of_day <= 6:
            base_value = 50.0
        else:
            base_value = 200.0
        
        # Add some random noise
        value = base_value + np.random.normal(0, 20)
        
        training_data.append(MetricPoint(
            timestamp=timestamp,
            value=value,
            metric_name="http_requests_per_minute",
            labels={"service": "api", "env": "prod"},
        ))
    
    print(f"✓ Generated {len(training_data)} training points")
    
    # Create pipeline with all detectors
    print("\n🤖 Initializing detectors...")
    pipeline = AnomalyPipeline(
        detectors=[
            ZScoreDetector(threshold=0.7),
            IsolationForestDetector(threshold=0.7, contamination=0.05),
            SeasonalDetector(threshold=0.7, period=24),
            ProphetDetector(threshold=0.7),
        ],
        weights=[0.2, 0.3, 0.2, 0.3],
        ensemble_threshold=0.65,
    )
    
    # Train the pipeline
    print("🎓 Training detectors on historical data...")
    await pipeline.fit_all(training_data)
    print("✓ All detectors trained")
    
    # Test Case 1: Normal value
    print("\n" + "=" * 80)
    print("Test Case 1: Normal Traffic (2pm on a weekday)")
    print("=" * 80)
    
    normal_point = MetricPoint(
        timestamp=datetime.utcnow().replace(hour=14, minute=0),
        value=510.0,  # Expected ~500 at 2pm
        metric_name="http_requests_per_minute",
        labels={"service": "api", "env": "prod"},
    )
    
    ensemble_result, individual_results = await pipeline.detect(normal_point)
    
    print(f"\n📌 Value: {normal_point.value:.2f} at 14:00")
    print(f"🎯 Ensemble Score: {ensemble_result.score:.3f}")
    print(f"🚦 Status: {ensemble_result.severity.value.upper()}")
    print(f"📊 Is Anomaly: {'❌ NO' if not ensemble_result.is_anomaly else '✅ YES'}")
    print(f"\n{ensemble_result.explanation}")
    
    # Test Case 2: Anomalous spike
    print("\n" + "=" * 80)
    print("Test Case 2: Anomalous Traffic Spike (2pm on a weekday)")
    print("=" * 80)
    
    anomaly_point = MetricPoint(
        timestamp=datetime.utcnow().replace(hour=14, minute=0),
        value=2000.0,  # 4x normal! Clear anomaly
        metric_name="http_requests_per_minute",
        labels={"service": "api", "env": "prod"},
    )
    
    ensemble_result, individual_results = await pipeline.detect(anomaly_point)
    
    print(f"\n📌 Value: {anomaly_point.value:.2f} at 14:00")
    print(f"🎯 Ensemble Score: {ensemble_result.score:.3f}")
    print(f"🚦 Status: {ensemble_result.severity.value.upper()}")
    print(f"📊 Is Anomaly: {'❌ NO' if not ensemble_result.is_anomaly else '🚨 YES'}")
    print(f"\n{ensemble_result.explanation}")
    
    print("\n" + "=" * 80)
    print("Individual Detector Breakdown:")
    print("=" * 80)
    for result in individual_results:
        icon = "🚨" if result.is_anomaly else "✅"
        print(f"{icon} {result.detector_name:20s} | Score: {result.score:.3f} | {result.explanation[:60]}...")
    
    # Test Case 3: Low traffic at night (expected pattern)
    print("\n" + "=" * 80)
    print("Test Case 3: Low Traffic at Night (expected pattern)")
    print("=" * 80)
    
    night_point = MetricPoint(
        timestamp=datetime.utcnow().replace(hour=3, minute=0),
        value=45.0,  # Low traffic expected at 3am
        metric_name="http_requests_per_minute",
        labels={"service": "api", "env": "prod"},
    )
    
    ensemble_result, individual_results = await pipeline.detect(night_point)
    
    print(f"\n📌 Value: {night_point.value:.2f} at 03:00")
    print(f"🎯 Ensemble Score: {ensemble_result.score:.3f}")
    print(f"🚦 Status: {ensemble_result.severity.value.upper()}")
    print(f"📊 Is Anomaly: {'❌ NO' if not ensemble_result.is_anomaly else '✅ YES'}")
    print(f"\n{ensemble_result.explanation}")
    
    print("\n" + "=" * 80)
    print("✅ Anomaly Detection Test Complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_anomaly_detection())