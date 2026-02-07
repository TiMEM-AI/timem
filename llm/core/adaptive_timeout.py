"""
Adaptive Timeout Manager

Dynamically adjust timeout based on historical latency to avoid fixed timeout being too long or too short.
"""

import time
import statistics
from collections import deque
from typing import Dict, Optional
from dataclasses import dataclass

from timem.utils.logging import get_logger
from timem.utils.config_manager import get_llm_config

logger = get_logger(__name__)


@dataclass
class TimeoutConfig:
    """Timeout configuration"""
    min_timeout: float = 30.0      # Minimum timeout (seconds)
    max_timeout: float = 60.0      # Maximum timeout (seconds)
    percentile: float = 0.95       # Based on P95 latency
    safety_margin: float = 1.5     # Safety margin
    history_size: int = 100        # History record count
    min_samples: int = 10          # Minimum sample count


class AdaptiveTimeout:
    """Adaptive timeout manager"""
    
    def __init__(self, config: Optional[TimeoutConfig] = None):
        """
        Initialize adaptive timeout manager
        
        Args:
            config: Timeout configuration
        """
        self.config = config or TimeoutConfig()
        
        # Latency history for each provider and model
        self._latency_history: Dict[str, deque] = {}
        
        # Default timeout configuration
        self._default_timeouts = {
            "zhipuai:glm-4-flash": 20.0,
            "zhipuai:glm-4": 30.0,
            "openai:gpt-4o-mini": 15.0,
            "openai:gpt-4": 45.0,
        }
        
        logger.info(
            f"Adaptive timeout manager initialized: min={self.config.min_timeout}s, "
            f"max={self.config.max_timeout}s, percentile=P{self.config.percentile*100:.0f}"
        )
    
    def record_latency(self, provider: str, model: str, latency: float):
        """
        Record request latency
        
        Args:
            provider: Provider name
            model: Model name
            latency: Latency (seconds)
        """
        key = f"{provider}:{model}"
        
        if key not in self._latency_history:
            self._latency_history[key] = deque(maxlen=self.config.history_size)
        
        self._latency_history[key].append(latency)
        
        logger.debug(
            f"Record latency: {key}, latency={latency:.2f}s, "
            f"history count={len(self._latency_history[key])}"
        )
    
    def get_timeout(self, provider: str, model: str, default: Optional[float] = None) -> float:
        """
        Get adaptive timeout
        
        Args:
            provider: Provider name
            model: Model name
            default: Default timeout (if no history data)
            
        Returns:
            Timeout (seconds)
        """
        key = f"{provider}:{model}"
        
        # Check if sufficient history data exists
        if key not in self._latency_history or len(self._latency_history[key]) < self.config.min_samples:
            # Use default timeout
            timeout = default or self._default_timeouts.get(key, self.config.max_timeout)
            logger.debug(f"Use default timeout: {key} = {timeout:.1f}s (insufficient samples)")
            return timeout
        
        # Calculate timeout based on percentile
        latencies = sorted(self._latency_history[key])
        percentile_index = int(len(latencies) * self.config.percentile)
        percentile_latency = latencies[min(percentile_index, len(latencies) - 1)]
        
        # Apply safety margin
        timeout = percentile_latency * self.config.safety_margin
        
        # Limit to min and max range
        timeout = max(self.config.min_timeout, min(timeout, self.config.max_timeout))
        
        logger.debug(
            f"Adaptive timeout: {key} = {timeout:.1f}s "
            f"(P{self.config.percentile*100:.0f}={percentile_latency:.2f}s)"
        )
        
        return timeout
    
    def get_streaming_timeout(self, provider: str, model: str) -> float:
        """
        Get timeout for streaming requests (first byte timeout)
        
        Streaming request timeout should be shorter because we expect to receive the first chunk quickly
        
        Args:
            provider: Provider name
            model: Model name
            
        Returns:
            Streaming timeout (seconds)
        """
        base_timeout = self.get_timeout(provider, model)
        
        # Streaming timeout = base timeout * 0.3, min 5s, max 15s
        streaming_timeout = base_timeout * 0.3
        streaming_timeout = max(5.0, min(streaming_timeout, 15.0))
        
        logger.debug(
            f"Streaming timeout: {provider}:{model} = {streaming_timeout:.1f}s "
            f"(base timeout={base_timeout:.1f}s)"
        )
        
        return streaming_timeout
    
    def get_statistics(self, provider: str, model: str) -> Dict[str, float]:
        """
        Get latency statistics
        
        Args:
            provider: Provider name
            model: Model name
            
        Returns:
            Statistics dictionary
        """
        key = f"{provider}:{model}"
        
        if key not in self._latency_history or not self._latency_history[key]:
            return {}
        
        latencies = list(self._latency_history[key])
        
        return {
            "count": len(latencies),
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "stdev": statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
            "min": min(latencies),
            "max": max(latencies),
            "p50": statistics.median(latencies),
            "p95": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0],
            "p99": sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) > 1 else latencies[0],
        }
    
    def clear_history(self, provider: Optional[str] = None, model: Optional[str] = None):
        """
        Clear history records
        
        Args:
            provider: Provider name (None means all)
            model: Model name (None means all)
        """
        if provider is None and model is None:
            self._latency_history.clear()
            logger.info("Cleared all latency history records")
        elif provider and model:
            key = f"{provider}:{model}"
            if key in self._latency_history:
                self._latency_history[key].clear()
                logger.info(f"Cleared latency history: {key}")
        elif provider:
            keys_to_clear = [k for k in self._latency_history.keys() if k.startswith(f"{provider}:")]
            for key in keys_to_clear:
                self._latency_history[key].clear()
            logger.info(f"Cleared all latency history for provider {provider}")


# Global adaptive timeout manager (singleton)
_global_adaptive_timeout: Optional[AdaptiveTimeout] = None


def get_global_adaptive_timeout() -> AdaptiveTimeout:
    """Get global adaptive timeout manager"""
    global _global_adaptive_timeout
    
    if _global_adaptive_timeout is None:
        llm_config = get_llm_config()
        timeout_config_dict = llm_config.get("resilience", {}).get("adaptive_timeout", {})
        
        config = TimeoutConfig(
            min_timeout=timeout_config_dict.get("min_timeout", 30.0),
            max_timeout=timeout_config_dict.get("max_timeout", 60.0),
            percentile=timeout_config_dict.get("percentile", 0.95),
            safety_margin=timeout_config_dict.get("safety_margin", 1.5),
        )
        
        _global_adaptive_timeout = AdaptiveTimeout(config)
        logger.info("Global adaptive timeout manager initialized")
    
    return _global_adaptive_timeout

