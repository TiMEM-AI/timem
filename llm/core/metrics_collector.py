"""
Monitoring Metrics Collector

Collects and aggregates various metrics for LLM calls:
1. Request success rate, failure rate
2. Response time distribution (P50/P95/P99)
3. Circuit breaker state changes
4. QPS statistics
5. Token usage statistics
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque
import statistics

from timem.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMMetrics:
    """LLM call metrics"""
    provider: str
    model: str
    timestamp: float
    success: bool
    latency: float  # Response time (seconds)
    tokens: int = 0  # Token count
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregatedMetrics:
    """Aggregated metrics"""
    provider: str
    time_window: float  # Time window (seconds)
    
    # Request statistics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Latency statistics
    latencies: List[float] = field(default_factory=list)
    
    # Token statistics
    total_tokens: int = 0
    
    # Error statistics
    errors: Dict[str, int] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        """Success rate"""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    @property
    def failure_rate(self) -> float:
        """Failure rate"""
        return 1.0 - self.success_rate
    
    @property
    def avg_latency(self) -> float:
        """Average latency"""
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)
    
    @property
    def p50_latency(self) -> float:
        """P50 latency"""
        if not self.latencies:
            return 0.0
        return statistics.median(self.latencies)
    
    @property
    def p95_latency(self) -> float:
        """P95 latency"""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[index] if index < len(sorted_latencies) else 0.0
    
    @property
    def p99_latency(self) -> float:
        """P99 latency"""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[index] if index < len(sorted_latencies) else 0.0
    
    @property
    def qps(self) -> float:
        """QPS (requests per second)"""
        if self.time_window == 0:
            return 0.0
        return self.total_requests / self.time_window
    
    @property
    def tokens_per_request(self) -> float:
        """Average tokens per request"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_tokens / self.successful_requests


class MetricsCollector:
    """
    Metrics collector
    
    Collects and aggregates various metrics for LLM calls.
    """
    
    def __init__(
        self,
        time_window: float = 60.0,
        max_samples: int = 1000
    ):
        """
        Initialize metrics collector
        
        Args:
            time_window: Statistics time window (seconds)
            max_samples: Maximum sample count
        """
        self.time_window = time_window
        self.max_samples = max_samples
        
        # Metrics queue (grouped by provider)
        self._metrics: Dict[str, deque[LLMMetrics]] = {}
        
        # Global statistics
        self._global_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_tokens": 0,
        }
        
        logger.info(
            f"Metrics collector initialized: time_window={time_window}s, max_samples={max_samples}"
        )
    
    def record(self, metric: LLMMetrics):
        """
        Record a metric
        
        Args:
            metric: LLM call metric
        """
        provider = metric.provider
        
        # Initialize queue
        if provider not in self._metrics:
            self._metrics[provider] = deque(maxlen=self.max_samples)
        
        # Add metric
        self._metrics[provider].append(metric)
        
        # Update global statistics
        self._global_stats["total_requests"] += 1
        if metric.success:
            self._global_stats["successful_requests"] += 1
            self._global_stats["total_tokens"] += metric.tokens
        else:
            self._global_stats["failed_requests"] += 1
        
        logger.debug(
            f"Record metric: provider={provider}, success={metric.success}, "
            f"latency={metric.latency:.3f}s, tokens={metric.tokens}"
        )
    
    def _clean_old_metrics(self, provider: str):
        """Clean old metrics"""
        if provider not in self._metrics:
            return
        
        now = time.time()
        cutoff = now - self.time_window
        
        metrics = self._metrics[provider]
        while metrics and metrics[0].timestamp < cutoff:
            metrics.popleft()
    
    def get_aggregated_metrics(
        self,
        provider: Optional[str] = None
    ) -> Dict[str, AggregatedMetrics]:
        """
        Get aggregated metrics
        
        Args:
            provider: Provider name (None means all providers)
            
        Returns:
            Aggregated metrics dictionary
        """
        if provider:
            # Single provider
            self._clean_old_metrics(provider)
            return {provider: self._aggregate_provider_metrics(provider)}
        else:
            # All providers
            result = {}
            for prov in self._metrics.keys():
                self._clean_old_metrics(prov)
                result[prov] = self._aggregate_provider_metrics(prov)
            return result
    
    def _aggregate_provider_metrics(self, provider: str) -> AggregatedMetrics:
        """Aggregate metrics for single provider"""
        if provider not in self._metrics:
            return AggregatedMetrics(
                provider=provider,
                time_window=self.time_window
            )
        
        metrics = list(self._metrics[provider])
        
        if not metrics:
            return AggregatedMetrics(
                provider=provider,
                time_window=self.time_window
            )
        
        # Calculate actual time window
        now = time.time()
        oldest_timestamp = metrics[0].timestamp
        actual_window = now - oldest_timestamp
        
        # Aggregate
        aggregated = AggregatedMetrics(
            provider=provider,
            time_window=actual_window if actual_window > 0 else self.time_window
        )
        
        for metric in metrics:
            aggregated.total_requests += 1
            
            if metric.success:
                aggregated.successful_requests += 1
                aggregated.latencies.append(metric.latency)
                aggregated.total_tokens += metric.tokens
            else:
                aggregated.failed_requests += 1
                error = metric.error or "Unknown"
                aggregated.errors[error] = aggregated.errors.get(error, 0) + 1
        
        return aggregated
    
    def get_stats_dict(
        self,
        provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get statistics dictionary
        
        Args:
            provider: Provider name (None means all providers)
            
        Returns:
            Statistics dictionary
        """
        aggregated = self.get_aggregated_metrics(provider)
        
        result = {}
        for prov, metrics in aggregated.items():
            result[prov] = {
                "time_window": metrics.time_window,
                "total_requests": metrics.total_requests,
                "successful_requests": metrics.successful_requests,
                "failed_requests": metrics.failed_requests,
                "success_rate": metrics.success_rate,
                "failure_rate": metrics.failure_rate,
                "qps": metrics.qps,
                "latency": {
                    "avg": metrics.avg_latency,
                    "p50": metrics.p50_latency,
                    "p95": metrics.p95_latency,
                    "p99": metrics.p99_latency,
                },
                "tokens": {
                    "total": metrics.total_tokens,
                    "per_request": metrics.tokens_per_request,
                },
                "errors": metrics.errors,
            }
        
        return result
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Get global statistics"""
        return {
            "total_requests": self._global_stats["total_requests"],
            "successful_requests": self._global_stats["successful_requests"],
            "failed_requests": self._global_stats["failed_requests"],
            "success_rate": (
                self._global_stats["successful_requests"] / self._global_stats["total_requests"]
                if self._global_stats["total_requests"] > 0 else 0.0
            ),
            "total_tokens": self._global_stats["total_tokens"],
            "providers": list(self._metrics.keys()),
        }
    
    def reset(self, provider: Optional[str] = None):
        """
        Reset statistics
        
        Args:
            provider: Provider name (None means reset all)
        """
        if provider:
            if provider in self._metrics:
                self._metrics[provider].clear()
                logger.info(f"Reset metrics for provider {provider}")
        else:
            self._metrics.clear()
            self._global_stats = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_tokens": 0,
            }
            logger.info("Reset all metrics")
    
    def export_prometheus_format(self) -> str:
        """
        Export metrics in Prometheus format
        
        Returns:
            Prometheus format metrics text
        """
        lines = []
        
        # Add HELP and TYPE comments
        lines.append("# HELP llm_requests_total Total number of LLM requests")
        lines.append("# TYPE llm_requests_total counter")
        
        lines.append("# HELP llm_requests_success Total number of successful LLM requests")
        lines.append("# TYPE llm_requests_success counter")
        
        lines.append("# HELP llm_requests_failed Total number of failed LLM requests")
        lines.append("# TYPE llm_requests_failed counter")
        
        lines.append("# HELP llm_latency_seconds LLM request latency in seconds")
        lines.append("# TYPE llm_latency_seconds summary")
        
        lines.append("# HELP llm_tokens_total Total number of tokens used")
        lines.append("# TYPE llm_tokens_total counter")
        
        # Export metrics
        stats = self.get_stats_dict()
        for provider, metrics in stats.items():
            # Request count
            lines.append(
                f'llm_requests_total{{provider="{provider}"}} {metrics["total_requests"]}'
            )
            lines.append(
                f'llm_requests_success{{provider="{provider}"}} {metrics["successful_requests"]}'
            )
            lines.append(
                f'llm_requests_failed{{provider="{provider}"}} {metrics["failed_requests"]}'
            )
            
            # Latency
            latency = metrics["latency"]
            lines.append(
                f'llm_latency_seconds{{provider="{provider}",quantile="0.5"}} {latency["p50"]}'
            )
            lines.append(
                f'llm_latency_seconds{{provider="{provider}",quantile="0.95"}} {latency["p95"]}'
            )
            lines.append(
                f'llm_latency_seconds{{provider="{provider}",quantile="0.99"}} {latency["p99"]}'
            )
            
            # Token count
            lines.append(
                f'llm_tokens_total{{provider="{provider}"}} {metrics["tokens"]["total"]}'
            )
        
        return "\n".join(lines)


# Global metrics collector (singleton)
_global_metrics_collector: Optional[MetricsCollector] = None


def get_global_metrics_collector() -> MetricsCollector:
    """
    Get global metrics collector (singleton)
    
    Returns:
        MetricsCollector instance
    """
    global _global_metrics_collector
    
    if _global_metrics_collector is None:
        _global_metrics_collector = MetricsCollector(
            time_window=60.0,
            max_samples=1000
        )
        logger.info("Global metrics collector initialized")
    
    return _global_metrics_collector

