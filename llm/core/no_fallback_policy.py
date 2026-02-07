"""
Disable Fallback policy

Ensure absolute no fallback content usage, all responses from real LLM services.
"""

from typing import Callable, Any, Optional
import asyncio

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class NoFallbackPolicy:
    """Disable Fallback policy"""
    
    def __init__(self, enabled: bool = True):
        """
        Initialize disable Fallback policy
        
        Args:
            enabled: Whether to enable strict mode (disable fallback)
        """
        self.enabled = enabled
        self.strict_mode = enabled  # Strict mode: never use fallback
        
        logger.info(
            f"Fallback policy initialized: enabled={enabled}, strict_mode={self.strict_mode}"
        )
        
        if self.strict_mode:
            logger.warning(
                "⚠️ Strict mode enabled: will absolutely not use fallback content, "
                "all responses must come from real LLM services"
            )
    
    def should_use_fallback(self, error: Exception) -> bool:
        """
        Determine if should use fallback
        
        Args:
            error: Exception occurred
            
        Returns:
            Whether to use fallback (always False in strict mode)
        """
        if self.strict_mode:
            logger.debug(
                f"Strict mode: rejecting fallback, error: {type(error).__name__}"
            )
            return False
        
        # Non-strict mode (currently not used)
        return not self.enabled
    
    async def execute_without_fallback(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function without fallback
        
        If failed, will raise exception instead of returning fallback content
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function execution result
            
        Raises:
            Last exception
        """
        if not self.strict_mode:
            # Non-strict mode, execute directly
            return await func(*args, **kwargs)
        
        try:
            result = await func(*args, **kwargs)
            
            # Validate result is not fallback content
            if self._is_fallback_content(result):
                raise ValueError("Detected fallback content, not allowed in strict mode")
            
            return result
            
        except Exception as e:
            logger.error(
                f"Strict mode: function execution failed, not using fallback: "
                f"{type(e).__name__}: {e}"
            )
            raise
    
    def _is_fallback_content(self, content: Any) -> bool:
        """
        Detect if content is fallback
        
        Uses smarter detection strategy to distinguish real system fallback responses from normal technical descriptions.
        
        Args:
            content: Content to detect
            
        Returns:
            Whether is fallback content
        """
        if not content:
            return False
        
        content_str = str(content).lower()
        
        # 1. First check if is technical discussion/normal content
        # If contains these features, it's normal technical description, exclude first
        technical_discussion_indicators = [
            # Code related
            "css", "html", "javascript", "browser", "video tag", "compatibility",
            "function", "method", "class", "property", "attribute",
            # Technical concepts (containing fallback phrases)
            "fallback mechanism", "fallback option", "fallback position", 
            "fallback strategy", "fallback plan", "fallback solution",
            "fallback font", "fallback content", "fallback behavior",
            "as a fallback", "provide a fallback", "provide fallback",
            "use fallback", "uses fallback", "used fallback",
            "implement fallback", "implemented a fallback",
            # Negotiation/strategy terms
            "negotiation", "bargaining", "union", "contract", "batna",
            # Technical documentation features
            "example", "tutorial", "guide", "documentation",
            # Memory generation features
            "user", "assistant", "conversation", "session",
            "discussed", "mentioned", "talked about", "explained",
            # Timeline features
            "timeline", "event", "activity", "pattern",
            # Web development
            "older browser", "older browsers", "backward compatibility",
        ]
        
        # If content contains technical discussion features, not fallback
        for indicator in technical_discussion_indicators:
            if indicator in content_str:
                logger.debug(
                    f"Detected technical discussion feature '{indicator}', "
                    f"content not considered fallback response"
                )
                return False
        
        # 2. Check strong features: clear system fallback response indicators
        # These usually appear in system degradation, mock responses, etc.
        # Note: only check complete phrases to avoid false positives
        strong_fallback_indicators = [
            "mock response",
            "fallback response",  # System-level fallback response
            "using fallback due to",  # System log format
            "switched to fallback",  # System switched to fallback
        ]
        
        for indicator in strong_fallback_indicators:
            if indicator in content_str:
                logger.warning(f"Detected strong fallback feature: {indicator}")
                return True
        
        # 3. Check very short response + containing "fallback" vocabulary
        # Real system fallback responses are usually short (<100 chars) and only contain error info
        # Note: technical discussion features already excluded (in step 1)
        if "fallback" in content_str and len(content_str) < 100:
            logger.warning(
                f"Detected suspicious short fallback response (length: {len(content_str)}): "
                f"{content_str[:50]}..."
            )
            return True
        
        # 4. Check "service unavailable" etc. service error messages
        # But need to exclude references in technical discussions
        error_indicators = [
            "service unavailable",
            "api error",
            "connection failed",
        ]
        
        for indicator in error_indicators:
            if indicator in content_str:
                # Check if referenced in technical discussion
                if any(word in content_str for word in ["if", "when", "example"]):
                    # Might be discussing error handling
                    continue
                logger.warning(f"Detected service error indicator: {indicator}")
                return True
        
        # 5. If content is long enough (>200 chars) and contains normal conversation structure
        # Almost certainly not fallback response
        if len(content_str) > 200:
            return False
        
        return False
    
    def validate_response(self, response: Any) -> bool:
        """
        Validate response is valid (non-fallback)
        
        Args:
            response: Response object
            
        Returns:
            Whether valid
            
        Raises:
            ValueError: If fallback content detected
        """
        if self._is_fallback_content(response):
            if self.strict_mode:
                raise ValueError(
                    "Strict mode: detected fallback content, rejecting"
                )
            return False
        
        return True


# Global disable fallback policy (singleton)
_global_no_fallback_policy: Optional[NoFallbackPolicy] = None


def get_global_no_fallback_policy() -> NoFallbackPolicy:
    """Get global disable fallback policy"""
    global _global_no_fallback_policy
    
    if _global_no_fallback_policy is None:
        from timem.utils.config_manager import get_llm_config
        
        llm_config = get_llm_config()
        fallback_config = llm_config.get("resilience", {}).get("fallback", {})
        
        # enabled=False means disable fallback (i.e., enable strict mode)
        enabled = not fallback_config.get("enabled", True)
        strict_mode = fallback_config.get("strict_mode", True)
        
        _global_no_fallback_policy = NoFallbackPolicy(
            enabled=enabled or strict_mode
        )
        
        logger.info("Global disable fallback policy initialized")
    
    return _global_no_fallback_policy

