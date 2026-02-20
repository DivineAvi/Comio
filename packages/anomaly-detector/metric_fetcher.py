"""Fetch metrics from Prometheus for anomaly detection."""
import httpx
import logging
from datetime import datetime, timedelta
from typing import Any

try:
    from .detectors.base import MetricPoint
except ImportError:
    from detectors.base import MetricPoint

logger = logging.getLogger(__name__)


class MetricFetcher:
    """
    Fetch time-series metrics from Prometheus.
    
    Queries Prometheus API and converts results to MetricPoint objects.
    """
    
    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        """
        Initialize MetricFetcher.
        
        Args:
            prometheus_url: Base URL of Prometheus server
        """
        self.prometheus_url = prometheus_url.rstrip('/')
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
    
    async def query_range(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        step: str = "1h",
    ) -> list[MetricPoint]:
        """
        Query Prometheus for a time range.
        
        Args:
            query: PromQL query string
            start_time: Start of time range
            end_time: End of time range
            step: Query resolution (e.g., "1m", "5m", "1h")
            
        Returns:
            List of MetricPoint objects
        """
        url = f"{self.prometheus_url}/api/v1/query_range"
        
        params = {
            "query": query,
            "start": start_time.timestamp(),
            "end": end_time.timestamp(),
            "step": step,
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data["status"] != "success":
                logger.error("Prometheus query failed: %s", data.get("error"))
                return []
            
            return self._parse_response(data["data"]["result"], query)
            
        except Exception as e:
            logger.error("Error querying Prometheus: %s", e)
            return []
    
    async def query_instant(self, query: str, time: datetime | None = None) -> list[MetricPoint]:
        """
        Query Prometheus for an instant value.
        
        Args:
            query: PromQL query string
            time: Specific timestamp (defaults to now)
            
        Returns:
            List of MetricPoint objects (one per series)
        """
        url = f"{self.prometheus_url}/api/v1/query"
        
        params = {"query": query}
        if time:
            params["time"] = time.timestamp()
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data["status"] != "success":
                logger.error("Prometheus query failed: %s", data.get("error"))
                return []
            
            return self._parse_response(data["data"]["result"], query)
            
        except Exception as e:
            logger.error("Error querying Prometheus: %s", e)
            return []
    
    def _parse_response(self, results: list[dict[str, Any]], query: str) -> list[MetricPoint]:
        """
        Parse Prometheus response into MetricPoint objects.
        
        Args:
            results: Prometheus result array
            query: Original query (used as metric_name if no __name__ label)
            
        Returns:
            List of MetricPoint objects
        """
        points = []
        
        for result in results:
            metric_labels = result.get("metric", {})
            metric_name = metric_labels.get("__name__", query)
            
            # Remove __name__ from labels (it's redundant)
            labels = {k: v for k, v in metric_labels.items() if k != "__name__"}
            
            # Parse values (could be single value or range)
            values = result.get("values", [result.get("value", [])])
            
            for value_pair in values:
                if len(value_pair) != 2:
                    continue
                
                timestamp_unix, value_str = value_pair
                
                try:
                    timestamp = datetime.fromtimestamp(float(timestamp_unix))
                    value = float(value_str)
                    
                    points.append(MetricPoint(
                        timestamp=timestamp,
                        value=value,
                        metric_name=metric_name,
                        labels=labels,
                    ))
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse metric value: %s", e)
                    continue
        
        return points
    
    async def get_metrics_for_detection(
        self,
        queries: list[str],
        lookback_hours: int = 168,  # 1 week default
    ) -> dict[str, list[MetricPoint]]:
        """
        Fetch multiple metrics for anomaly detection.
        
        Args:
            queries: List of PromQL queries
            lookback_hours: How far back to look for training data
            
        Returns:
            Dict mapping query to list of MetricPoints
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=lookback_hours)
        
        results = {}
        
        for query in queries:
            points = await self.query_range(
                query=query,
                start_time=start_time,
                end_time=end_time,
                step="1h",  # Hourly resolution
            )
            results[query] = points
            logger.info("Fetched %d points for query: %s", len(points), query)
        
        return results