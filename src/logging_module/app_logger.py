"""
Structured application logging.
Never logs sensitive information (passwords, tokens, proxy secrets).
"""

import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

from src.config.settings import settings


class AppLogger:
    """
    Structured logger for the application.
    
    Log format: TIMESTAMP | PROFILE_ID | EVENT | MESSAGE
    Example: 12:30:10 | spotify_de_001 | TASK_STARTED | Track review started
    """
    
    def __init__(self, name: str = "spotify_manager"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        
        # File handler
        log_file = settings.LOGS_DIR / f"{name}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Formatter - structured format
        formatter = logging.Formatter(
            '%(asctime)s | %(profile_id)s | %(event)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Custom filter to add profile_id and event
        class ContextFilter(logging.Filter):
            def filter(self, record):
                if not hasattr(record, 'profile_id'):
                    record.profile_id = "-"
                if not hasattr(record, 'event'):
                    record.event = record.levelname
                return True
        
        console_handler.addFilter(ContextFilter())
        file_handler.addFilter(ContextFilter())
        
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def _log(self, level: int, message: str, event: str, 
             profile_id: Optional[int] = None, extra: Optional[dict] = None):
        """Internal log method with context."""
        extra = extra or {}
        extra['profile_id'] = str(profile_id) if profile_id else "-"
        extra['event'] = event
        self.logger.log(level, message, extra=extra)
    
    def info(self, message: str, event: str = "INFO", profile_id: Optional[int] = None):
        """Log info level message."""
        self._log(logging.INFO, message, event, profile_id)
    
    def debug(self, message: str, event: str = "DEBUG", profile_id: Optional[int] = None):
        """Log debug level message."""
        self._log(logging.DEBUG, message, event, profile_id)
    
    def warning(self, message: str, event: str = "WARNING", profile_id: Optional[int] = None):
        """Log warning level message."""
        self._log(logging.WARNING, message, event, profile_id)
    
    def error(self, message: str, event: str = "ERROR", profile_id: Optional[int] = None):
        """Log error level message."""
        self._log(logging.ERROR, message, event, profile_id)
    
    def task_started(self, task_type: str, profile_id: Optional[int] = None):
        """Log task start event."""
        self.info(f"{task_type} task started", "TASK_STARTED", profile_id)
    
    def task_completed(self, task_type: str, profile_id: Optional[int] = None):
        """Log task completion event."""
        self.info(f"{task_type} task completed", "TASK_COMPLETED", profile_id)
    
    def task_failed(self, task_type: str, error: str, profile_id: Optional[int] = None):
        """Log task failure event."""
        self.error(f"{task_type} task failed: {error}", "TASK_FAILED", profile_id)
    
    def spotify_auth(self, message: str, profile_id: Optional[int] = None):
        """Log Spotify authentication event."""
        # Never log tokens or credentials
        self.info(message, "SPOTIFY_AUTH", profile_id)
    
    def browser_event(self, message: str, profile_id: Optional[int] = None):
        """Log browser-related event."""
        self.info(message, "BROWSER_EVENT", profile_id)


# Global logger instance
app_logger = AppLogger()


def get_logger() -> AppLogger:
    """Get the global logger instance."""
    return app_logger
