"""
Structured logging configuration for gmail-expense-parser.
Provides consistent logging format, levels, and file output.
"""
import os
import sys
import logging
import logging.handlers
from datetime import datetime
from typing import Optional, Dict, Any

# Log levels mapping
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# Default configuration
DEFAULT_LOG_LEVEL = 'INFO'
DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
DEFAULT_LOG_DIR = 'logs'
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5


class StructuredLogger:
    """Enhanced logger with structured logging capabilities."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.context: Dict[str, Any] = {}
    
    def set_context(self, **kwargs):
        """Set context variables for structured logging."""
        self.context.update(kwargs)
    
    def clear_context(self):
        """Clear all context variables."""
        self.context.clear()
    
    def _format_message(self, message: str) -> str:
        """Format message with context if available."""
        if self.context:
            context_str = ' '.join(f'{k}={v}' for k, v in self.context.items())
            return f"{message} [{context_str}]"
        return message
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.set_context(**kwargs)
        self.logger.debug(self._format_message(message))
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self.set_context(**kwargs)
        self.logger.info(self._format_message(message))
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.set_context(**kwargs)
        self.logger.warning(self._format_message(message))
    
    def error(self, message: str, exc_info: bool = False, **kwargs):
        """Log error message."""
        self.set_context(**kwargs)
        self.logger.error(self._format_message(message), exc_info=exc_info)
    
    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self.set_context(**kwargs)
        self.logger.critical(self._format_message(message))
    
    def exception(self, message: str, **kwargs):
        """Log exception with traceback."""
        self.set_context(**kwargs)
        self.logger.exception(self._format_message(message))


def setup_logging(
    log_level: str = DEFAULT_LOG_LEVEL,
    log_format: str = DEFAULT_LOG_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
    log_dir: str = DEFAULT_LOG_DIR,
    log_to_file: bool = True,
    log_to_console: bool = True,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT
) -> None:
    """
    Setup comprehensive logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log message format
        date_format: Date format in logs
        log_dir: Directory for log files
        log_to_file: Whether to log to file
        log_to_console: Whether to log to console
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup log files to keep
    """
    # Convert string log level to logging constant
    level = LOG_LEVELS.get(log_level.upper(), logging.INFO)
    
    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(log_format, date_format)
    
    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_to_file:
        # Create log directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Create log filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f'gmail_expense_parser_{timestamp}.log')
        
        # Rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Set root logger level
    root_logger.setLevel(level)
    
    # Log startup message
    startup_logger = logging.getLogger(__name__)
    startup_logger.info(f"Logging initialized with level: {log_level}")
    startup_logger.info(f"Log directory: {os.path.abspath(log_dir)}")
    startup_logger.info(f"Log to file: {log_to_file}, Log to console: {log_to_console}")


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)


# Convenience function for quick logging setup
def quick_setup(level: str = 'INFO'):
    """Quick setup with default configuration."""
    setup_logging(log_level=level)


if __name__ == '__main__':
    # Test the logging setup
    quick_setup('DEBUG')
    logger = get_logger(__name__)
    
    logger.info("Testing structured logger")
    logger.debug("Debug message", user="test", action="login")
    logger.warning("Warning message", count=5, threshold=10)
    logger.error("Error message", exc_info=False, error_code=404)
    
    try:
        raise ValueError("Test exception")
    except ValueError:
        logger.exception("Exception occurred", context="test")