"""
TiMem Standard Logging System - Based on Python Standard Library
Completely replaces loguru, provides more stable and reliable logging

Features:
- Based on Python standard library logging, no third-party dependencies
- Built-in log length limit, prevents long text blocking
- Safe exception handling, ensures logging errors don't affect main program
- Supports file rotation, compression and other enterprise-level features
- Thread-safe, supports concurrent scenarios
- Compatible with original API, supports smooth migration
"""

import logging
import logging.handlers
import sys
import os
import threading
import traceback
import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List, Union, TextIO
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, asdict


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


@dataclass
class LogContext:
    """Log context"""
    operation: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    component: Optional[str] = None
    duration: Optional[float] = None
    error_code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SafeFormatter(logging.Formatter):
    """Safe log formatter - Prevent long text blocking"""
    
    def __init__(self, fmt=None, datefmt=None, max_length=10000):
        super().__init__(fmt, datefmt)
        self.max_length = max_length
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record, limit message length"""
        try:
            # Limit message length
            if hasattr(record, 'msg') and isinstance(record.msg, str):
                if len(record.msg) > self.max_length:
                    record.msg = record.msg[:self.max_length-100] + f"...[truncated, original length:{len(record.msg)}]"
            
            # Limit string length in args
            if hasattr(record, 'args') and record.args:
                safe_args = []
                for arg in record.args:
                    if isinstance(arg, str) and len(arg) > self.max_length:
                        safe_args.append(arg[:self.max_length-50] + "...[truncated]")
                    else:
                        safe_args.append(arg)
                record.args = tuple(safe_args)
            
            return super().format(record)
        except Exception as e:
            # If formatting fails, return simple error message
            return f"[LOGGING_ERROR] {e} - Original: {getattr(record, 'msg', 'Unknown')}"


class SafeHandler(logging.Handler):
    """Safe log handler - Prevent logging errors affecting main program"""
    
    def __init__(self, target_handler, max_errors=10):
        super().__init__()
        self.target_handler = target_handler
        self.max_errors = max_errors
        self.error_count = 0
        self.fallback_mode = False
        self._lock = threading.Lock()
    
    def emit(self, record: logging.LogRecord) -> None:
        """Safely emit log record"""
        try:
            if self.fallback_mode:
                # Fallback to simple print
                try:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    message = self.format(record) if hasattr(self, 'format') else str(record.getMessage())
                    print(f"[{timestamp}] {record.levelname}: {message}")
                except Exception:
                    pass  # If even print fails, give up
                return
            
            # Try using normal handler
            self.target_handler.emit(record)
            
        except Exception as e:
            with self._lock:
                self.error_count += 1
                if self.error_count >= self.max_errors:
                    self.fallback_mode = True
                    try:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] WARNING: Too many logging handler errors, switching to fallback mode")
                    except Exception:
                        pass
                
                # Try printing error message
                try:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] LOGGING_ERROR: {e}")
                except Exception:
                    pass  # If even print fails, give up


class StandardLogger:
    """Standard logger"""
    
    def __init__(self, name: str = "TiMem", level: str = "INFO", max_length: int = 10000):
        self.name = name
        self.max_length = max_length
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, level.upper()))
        self._lock = threading.Lock()
        self._context_stack = []
        self._initialized = False
        
        # Clear existing handlers
        self._logger.handlers.clear()
        
        # Initialize handlers
        self._setup_handlers()
        self._initialized = True
    
    def _setup_handlers(self):
        """Setup handlers"""
        try:
            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_formatter = SafeFormatter(
                fmt='%(asctime)s | %(levelname)-8s | %(name)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
                max_length=self.max_length
            )
            console_handler.setFormatter(console_formatter)
            
            # Use safe handler wrapper
            safe_console = SafeHandler(console_handler)
            safe_console.setFormatter(console_formatter)
            self._logger.addHandler(safe_console)
            
            # File handler (optional)
            log_file_enabled = os.getenv("LOG_FILE_ENABLED", "false").lower() == "true"
            if log_file_enabled:
                self._add_file_handler()
                
        except Exception as e:
            # If setup fails, at least ensure basic output
            try:
                print(f"Logging system initialization failed: {e}")
            except Exception:
                pass
    
    def _add_file_handler(self):
        """Add file handler"""
        try:
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            
            # Use RotatingFileHandler to avoid large files
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_dir / "timem.log",
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            
            file_formatter = SafeFormatter(
                fmt='%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S.%f',
                max_length=self.max_length
            )
            file_handler.setFormatter(file_formatter)
            
            # Use safe handler wrapper
            safe_file = SafeHandler(file_handler)
            safe_file.setFormatter(file_formatter)
            self._logger.addHandler(safe_file)
            
        except Exception as e:
            try:
                print(f"File logging handler setup failed: {e}")
            except Exception:
                pass
    
    def _safe_log(self, level: str, message: str, *args, **kwargs):
        """Safe logging method"""
        if not self._initialized:
            return
            
        try:
            # Limit message length
            if isinstance(message, str) and len(message) > self.max_length:
                message = message[:self.max_length-100] + f"...[truncated, original length:{len(message)}]"
            
            # Get logging method
            log_method = getattr(self._logger, level.lower(), self._logger.info)
            
            # Add context information
            extra = {}
            if self._context_stack:
                extra['context'] = self._context_stack[-1]
            
            log_method(message, *args, extra=extra, **kwargs)
            
        except Exception as e:
            # Final fallback
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] LOGGING_FALLBACK [{level}]: {message}")
            except Exception:
                pass  # Give up
    
    def trace(self, message: str, *args, **kwargs):
        """Log TRACE level message"""
        self._safe_log("debug", f"TRACE: {message}", *args, **kwargs)  # TRACE maps to DEBUG
    
    def debug(self, message: str, *args, **kwargs):
        """Log DEBUG level message"""
        self._safe_log("debug", message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Log INFO level message"""
        self._safe_log("info", message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log WARNING level message"""
        self._safe_log("warning", message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log ERROR level message"""
        self._safe_log("error", message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Log CRITICAL level message"""
        self._safe_log("critical", message, *args, **kwargs)
    
    @contextmanager
    def context(self, **context_data):
        """Logging context manager"""
        context = LogContext(**context_data)
        self._context_stack.append(context)
        try:
            yield context
        finally:
            if self._context_stack:
                self._context_stack.pop()
    
    def bind(self, **kwargs):
        """Bind context information (compatible with loguru API)"""
        return BoundLogger(self, **kwargs)


class BoundLogger:
    """Bound logger with context"""
    
    def __init__(self, logger: StandardLogger, **context):
        self.logger = logger
        self.context = context
    
    def _log_with_context(self, level: str, message: str, *args, **kwargs):
        """Log with context"""
        # Merge context information into message
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            message = f"[{context_str}] {message}"
        
        getattr(self.logger, level)(message, *args, **kwargs)
    
    def trace(self, message: str, *args, **kwargs):
        self._log_with_context("trace", message, *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs):
        self._log_with_context("debug", message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        self._log_with_context("info", message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        self._log_with_context("warning", message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        self._log_with_context("error", message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        self._log_with_context("critical", message, *args, **kwargs)


# Global logger instances
_loggers = {}
_logger_lock = threading.Lock()


def get_standard_logger(name: str = "TiMem", level: str = "INFO") -> StandardLogger:
    """Get standard logger instance"""
    with _logger_lock:
        if name not in _loggers:
            _loggers[name] = StandardLogger(name=name, level=level)
        return _loggers[name]


def get_logger(name: str, category: LogCategory = LogCategory.SYSTEM) -> StandardLogger:
    """Get logger (compatible with original API)"""
    logger_name = f"{category.value}.{name}" if category != LogCategory.SYSTEM else name
    return get_standard_logger(logger_name)


# For compatibility, provide functions with the same name as the original API
def get_safe_logger() -> StandardLogger:
    """Get safe logger"""
    return get_standard_logger("SafeLogger")


def init_logging():
    """Initialize logging system"""
    return get_standard_logger()


def setup_logging():
    """Setup logging system (backward compatible)"""
    return init_logging()


def setup_error_handler():
    """Setup error handler (backward compatible)"""
    class ErrorHandler:
        def __init__(self):
            self.logger = get_standard_logger("ErrorHandler")
        
        def handle_exception(self, exc_type, exc_value, exc_traceback):
            """Handle uncaught exceptions"""
            if exc_type is KeyboardInterrupt:
                return
            
            error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            self.logger.error(f"Uncaught exception: {error_msg}")
        
        def handle_error(self, error: Exception, context: Dict[str, Any] = None):
            """Handle known errors"""
            context_str = f" Context: {context}" if context else ""
            self.logger.error(f"Error handling: {str(error)}{context_str}")
    
    return ErrorHandler()


# Performance monitoring decorator
def log_performance(logger_name: str = "Performance"):
    """Performance monitoring decorator"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_standard_logger(logger_name)
            start_time = datetime.now()
            
            try:
                result = await func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"{func.__name__} executed successfully, took: {duration:.3f}s")
                return result
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                logger.error(f"{func.__name__} execution failed, took: {duration:.3f}s, error: {e}")
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = get_standard_logger(logger_name)
            start_time = datetime.now()
            
            try:
                result = func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"{func.__name__} executed successfully, took: {duration:.3f}s")
                return result
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                logger.error(f"{func.__name__} execution failed, took: {duration:.3f}s, error: {e}")
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


# Backward compatible class
class LoggingMixin:
    """Logging mixin class (backward compatible)"""
    
    @property
    def logger(self):
        """Get logger"""
        return get_standard_logger(self.__class__.__name__)
    
    def log_method_call(self, method_name: str, *args, **kwargs):
        """Log method call"""
        self.logger.debug(f"Method call: {method_name}, args: {args}, kwargs: {kwargs}")
    
    def log_error(self, error: Exception, context: Dict[str, Any] = None):
        """Log error"""
        context_str = f" Context: {context}" if context else ""
        self.logger.error(f"Error: {str(error)}{context_str}")


# Ensure logger is available on import
import asyncio

# Create default logger instance
logger = get_standard_logger()
