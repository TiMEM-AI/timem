"""
Fallback strategy manager

Provides multi-level fallback capability:
1. Provider fallback chain: primary service → backup service → Mock
2. Model fallback: advanced model → fast model
3. Feature fallback: full generation → simplified generation → cached response
"""

import asyncio
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class FallbackStrategy(str, Enum):
    """Fallback strategy type"""
    PROVIDER = "provider"  # Provider fallback
    MODEL = "model"  # Model fallback
    FEATURE = "feature"  # Feature fallback


@dataclass
class FallbackOption:
    """Fallback option"""
    provider: str  # Provider name
    model: Optional[str] = None  # Model name
    priority: int = 0  # Priority (lower number = higher priority)
    enabled: bool = True  # Whether enabled
    metadata: Dict[str, Any] = None  # Additional metadata
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class FallbackChain:
    """Fallback chain"""
    name: str  # Chain name
    strategy: FallbackStrategy  # Strategy type
    options: List[FallbackOption]  # Fallback options list (sorted by priority)
    max_attempts: int = 3  # Maximum attempts
    
    def __post_init__(self):
        # Sort by priority
        self.options.sort(key=lambda x: x.priority)
        
        # Filter disabled options
        self.options = [opt for opt in self.options if opt.enabled]


@dataclass
class FallbackResult:
    """Fallback result"""
    success: bool  # Whether successful
    option: Optional[FallbackOption]  # Fallback option used
    attempt: int  # Number of attempts
    result: Any  # Result data
    error: Optional[Exception] = None  # Error information
    fallback_used: bool = False  # Whether fallback was used


class FallbackManager:
    """
    Fallback strategy manager
    
    Manages multi-level fallback strategies to ensure service availability.
    """
    
    def __init__(self, enable_fallback: bool = True):
        """
        Initialize fallback manager
        
        Args:
            enable_fallback: Whether to enable fallback
        """
        self.enable_fallback = enable_fallback
        
        # Fallback chains
        self._chains: Dict[str, FallbackChain] = {}
        
        # Fallback statistics
        self._stats = {
            "total_calls": 0,
            "fallback_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "option_usage": {},  # Usage count for each option
        }
        
        # Lock
        self._lock = asyncio.Lock()
        
        logger.info(f"Fallback manager initialized: enable_fallback={enable_fallback}")
    
    def register_chain(self, chain: FallbackChain):
        """
        Register fallback chain
        
        Args:
            chain: Fallback chain configuration
        """
        self._chains[chain.name] = chain
        logger.info(
            f"Registered fallback chain [{chain.name}]: "
            f"strategy={chain.strategy.value}, "
            f"options={len(chain.options)}"
        )
    
    def get_chain(self, name: str) -> Optional[FallbackChain]:
        """
        Get fallback chain
        
        Args:
            name: Chain name
            
        Returns:
            Fallback chain configuration
        """
        return self._chains.get(name)
    
    async def execute_with_fallback(
        self,
        chain_name: str,
        func: Callable,
        *args,
        **kwargs
    ) -> FallbackResult:
        """
        Execute function call with fallback
        
        Args:
            chain_name: Fallback chain name
            func: Async function to execute (accepts option parameter)
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Fallback result
        """
        chain = self.get_chain(chain_name)
        if not chain:
            raise ValueError(f"Fallback chain [{chain_name}] does not exist")
        
        self._stats["total_calls"] += 1
        
        if not self.enable_fallback:
            # Fallback not enabled, call primary option directly
            primary_option = chain.options[0] if chain.options else None
            if not primary_option:
                raise ValueError(f"Fallback chain [{chain_name}] has no available options")
            
            try:
                result = await func(primary_option, *args, **kwargs)
                self._stats["success_calls"] += 1
                return FallbackResult(
                    success=True,
                    option=primary_option,
                    attempt=1,
                    result=result,
                    fallback_used=False
                )
            except Exception as e:
                self._stats["failed_calls"] += 1
                return FallbackResult(
                    success=False,
                    option=primary_option,
                    attempt=1,
                    result=None,
                    error=e,
                    fallback_used=False
                )
        
        # Execute fallback chain
        last_error = None
        for attempt, option in enumerate(chain.options, 1):
            if attempt > chain.max_attempts:
                logger.warning(
                    f"Fallback chain [{chain_name}] reached max attempts {chain.max_attempts}"
                )
                break
            
            try:
                logger.info(
                    f"Fallback chain [{chain_name}] attempt {attempt}/{len(chain.options)}: "
                    f"provider={option.provider}, model={option.model}"
                )
                
                # Execute function
                result = await func(option, *args, **kwargs)
                
                # Success
                async with self._lock:
                    self._stats["success_calls"] += 1
                    if attempt > 1:
                        self._stats["fallback_calls"] += 1
                    
                    # Update option usage statistics
                    option_key = f"{option.provider}:{option.model}"
                    self._stats["option_usage"][option_key] = (
                        self._stats["option_usage"].get(option_key, 0) + 1
                    )
                
                logger.info(
                    f"Fallback chain [{chain_name}] succeeded (attempt {attempt}): "
                    f"provider={option.provider}, model={option.model}"
                )
                
                return FallbackResult(
                    success=True,
                    option=option,
                    attempt=attempt,
                    result=result,
                    fallback_used=(attempt > 1)
                )
            
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Fallback chain [{chain_name}] failed (attempt {attempt}): "
                    f"provider={option.provider}, model={option.model}, "
                    f"error={e}"
                )
                
                # Try next option
                continue
        
        # All options failed
        self._stats["failed_calls"] += 1
        logger.error(f"Fallback chain [{chain_name}] all options failed")
        
        return FallbackResult(
            success=False,
            option=None,
            attempt=len(chain.options),
            result=None,
            error=last_error,
            fallback_used=True
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get fallback statistics"""
        return {
            "enable_fallback": self.enable_fallback,
            "total_calls": self._stats["total_calls"],
            "success_calls": self._stats["success_calls"],
            "failed_calls": self._stats["failed_calls"],
            "fallback_calls": self._stats["fallback_calls"],
            "success_rate": (
                self._stats["success_calls"] / self._stats["total_calls"]
                if self._stats["total_calls"] > 0 else 0.0
            ),
            "fallback_rate": (
                self._stats["fallback_calls"] / self._stats["total_calls"]
                if self._stats["total_calls"] > 0 else 0.0
            ),
            "option_usage": self._stats["option_usage"],
            "registered_chains": list(self._chains.keys()),
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self._stats = {
            "total_calls": 0,
            "fallback_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "option_usage": {},
        }
        logger.info("Fallback statistics reset")


def create_default_fallback_chain() -> FallbackChain:
    """
    Create default fallback chain
    
    Returns:
        Default fallback chain configuration
    """
    return FallbackChain(
        name="default",
        strategy=FallbackStrategy.PROVIDER,
        options=[
            FallbackOption(provider="zhipuai", model="glm-4-flash", priority=0),
            FallbackOption(provider="openai", model="gpt-4o-mini", priority=1),
            FallbackOption(provider="mock", model="mock-llm", priority=2),
        ],
        max_attempts=3
    )


# Global fallback manager (singleton)
_global_fallback_manager: Optional[FallbackManager] = None
_global_fallback_lock = asyncio.Lock()


async def get_global_fallback_manager() -> FallbackManager:
    """
    Get global fallback manager (singleton)
    
    Returns:
        FallbackManager instance
    """
    global _global_fallback_manager
    
    if _global_fallback_manager is None:
        async with _global_fallback_lock:
            if _global_fallback_manager is None:
                # Load from configuration
                from timem.utils.config_manager import get_llm_config
                llm_config = get_llm_config()
                
                fallback_config = llm_config.get("fallback", {})
                enable = fallback_config.get("enable", True)
                
                _global_fallback_manager = FallbackManager(enable_fallback=enable)
                
                # Register default fallback chains
                chains = fallback_config.get("chains", [])
                if chains:
                    # Build fallback chains from configuration
                    options = []
                    for i, chain_config in enumerate(chains):
                        option = FallbackOption(
                            provider=chain_config.get("provider"),
                            model=chain_config.get("model"),
                            priority=i,
                            enabled=chain_config.get("enabled", True)
                        )
                        options.append(option)
                    
                    chain = FallbackChain(
                        name="default",
                        strategy=FallbackStrategy.PROVIDER,
                        options=options,
                        max_attempts=len(options)
                    )
                    _global_fallback_manager.register_chain(chain)
                else:
                    # Use default fallback chain
                    _global_fallback_manager.register_chain(create_default_fallback_chain())
                
                logger.info("Global fallback manager initialized")
    
    return _global_fallback_manager

