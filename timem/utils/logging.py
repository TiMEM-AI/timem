"""
TiMem Simplified Logging System - Using only print
Completely avoids any complex logging processing that could cause blocking
"""

import sys
import threading
import traceback
from datetime import datetime
from typing import Any, Dict, Optional, List, Union
from contextlib import contextmanager
from functools import wraps
from enum import Enum


class LogLevel(Enum):
    """Log level enumeration"""
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogCategory(Enum):
    """Log category enumeration"""
    SYSTEM = "SYSTEM"
    WORKFLOW = "WORKFLOW"
    STORAGE = "STORAGE"
    LLM = "LLM"
    API = "API"
    PERFORMANCE = "PERFORMANCE"


class SimpleLogger:
    """Simplest logger implementation - Using only print"""
    
    def __init__(self, name: str = "TiMem"):
        self.name = name
        self._lock = threading.Lock()
    
    def _safe_print(self, level: str, message: str):
        """Safe print method"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            # Limit message length to avoid overly long content
            if len(message) > 1000:
                message = message[:1000] + "...[truncated]"
            print(f"[{timestamp}] {level}: {message}")
        except Exception:
            # If even print fails, give up completely
            pass
    
    def trace(self, message: str, *args, **kwargs):
        """Log TRACE level message"""
        if args:
            try:
                message = message % args
            except Exception:
                pass
        self._safe_print("TRACE", message)
    
    def debug(self, message: str, *args, **kwargs):
        """Log DEBUG level message"""
        if args:
            try:
                message = message % args
            except Exception:
                pass
        self._safe_print("DEBUG", message)
    
    def info(self, message: str, *args, **kwargs):
        """Log INFO level message"""
        if args:
            try:
                message = message % args
            except Exception:
                pass
        self._safe_print("INFO", message)
    
    def warning(self, message: str, *args, **kwargs):
        """Log WARNING level message"""
        if args:
            try:
                message = message % args
            except Exception:
                pass
        self._safe_print("WARNING", message)
    
    def error(self, message: str, *args, **kwargs):
        """Log ERROR level message"""
        if args:
            try:
                message = message % args
            except Exception:
                pass
        self._safe_print("ERROR", message)
    
    def critical(self, message: str, *args, **kwargs):
        """Log CRITICAL level message"""
        if args:
            try:
                message = message % args
            except Exception:
                pass
        self._safe_print("CRITICAL", message)
    
    @contextmanager
    def context(self, **context_data):
        """Log context manager (no-op)"""
        yield self
    
    def bind(self, **kwargs):
        """Bind context information (return self)"""
        return self


class BoundLogger:
    """Bound logger with context (simplified version)"""
    
    def __init__(self, logger: SimpleLogger, **context):
        self.logger = logger
        self.context = context
    
    def _add_context(self, message: str) -> str:
        """Add context to message"""
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"[{context_str}] {message}"
        return message
    
    def trace(self, message: str, *args, **kwargs):
        self.logger.trace(self._add_context(message), *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs):
        self.logger.debug(self._add_context(message), *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        self.logger.info(self._add_context(message), *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        self.logger.warning(self._add_context(message), *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        self.logger.error(self._add_context(message), *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        self.logger.critical(self._add_context(message), *args, **kwargs)


# Global logger instance management
_loggers = {}
_logger_lock = threading.Lock()


def get_logger(name: str, category: LogCategory = LogCategory.SYSTEM) -> SimpleLogger:
    """Get simple logger"""
    logger_name = f"{category.value}.{name}" if category != LogCategory.SYSTEM else name
    
    with _logger_lock:
        if logger_name not in _loggers:
            _loggers[logger_name] = SimpleLogger(name=logger_name)
        return _loggers[logger_name]


def get_safe_logger() -> SimpleLogger:
    """Get safe logger"""
    return get_logger("SafeLogger")


def init_logging():
    """Initialize logging system"""
    return get_logger("TiMem")


def setup_logging():
    """Setup logging system (backward compatible)"""
    return init_logging()


def setup_error_handler():
    """Setup error handler (backward compatible)"""
    import traceback

    class ErrorHandler:
        def __init__(self):
            self.logger = get_logger("ErrorHandler")

        def handle_exception(self, exc_type, exc_value, exc_traceback):
            """Handle uncaught exception"""
            if exc_type is KeyboardInterrupt:
                return
            try:
                error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
                if len(error_msg) > 1000:
                    error_msg = error_msg[:1000] + "...[truncated]"
                self.logger.error(f"Uncaught exception: {error_msg}")
            except Exception:
                print(f"[ERROR] Uncaught exception: {exc_value}")

        def handle_error(self, error: Exception, context: Dict[str, Any] = None):
            """Handle known error"""
            try:
                context_str = f" Context: {context}" if context else ""
                self.logger.error(f"Error handling: {str(error)}{context_str}")
            except Exception:
                print(f"[ERROR] Error handling: {error}")

    return ErrorHandler()


# Performance monitoring decorator
def log_performance(logger_name: str = "Performance"):
    """Performance monitoring decorator"""
    from functools import wraps
    from datetime import datetime
    import asyncio

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_logger(logger_name)
            start_time = datetime.now()
            try:
                result = await func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"{func.__name__} executed successfully, took: {duration:.3f} seconds")
                return result
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                logger.error(f"{func.__name__} execution failed, took: {duration:.3f} seconds, error: {e}")
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = get_logger(logger_name)
            start_time = datetime.now()
            try:
                result = func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"{func.__name__} executed successfully, took: {duration:.3f} seconds")
                return result
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                logger.error(f"{func.__name__} execution failed, took: {duration:.3f} seconds, error: {e}")
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Backward compatible classes
class LoggingMixin:
    """Logging mixin class (backward compatible)"""
    
    @property
    def logger(self):
        """Get logger"""
        return get_logger(self.__class__.__name__)
    
    def log_method_call(self, method_name: str, *args, **kwargs):
        """Log method call"""
        self.logger.debug(f"Method call: {method_name}")
    
    def log_error(self, error: Exception, context: Dict[str, Any] = None):
        """Log error"""
        self.logger.error(f"Error: {str(error)}")


# Backward compatible type definitions
StandardLogger = SimpleLogger
UnifiedLogger = SimpleLogger

# Backward compatible functions
def get_standard_logger(name: str = "TiMem", level: str = "INFO") -> SimpleLogger:
    """Get standard logger instance"""
    return get_logger(name)

# Create default logger instance
logger = get_logger("TiMem")