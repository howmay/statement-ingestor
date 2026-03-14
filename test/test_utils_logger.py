"""
Unit tests for logger utility.
"""
import os
import sys
import pytest
import logging
from unittest.mock import patch, MagicMock
from pathlib import Path

# We need to set up the environment properly for import
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.support.logger import setup_logging, get_logger


class TestLogger:
    """Test suite for logger utility."""
    
    def test_get_logger(self):
        """Test getting a logger instance."""
        logger = get_logger('test')
        assert logger is not None
        # get_logger returns StructuredLogger
        assert hasattr(logger, 'logger')  # StructuredLogger has .logger attribute
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'debug')
    
    def test_setup_logging_console_only(self):
        """Test setting up logging with console only."""
        # Should not raise any errors
        setup_logging(
            log_level='INFO',
            log_to_file=False,
            log_to_console=True
        )
        # Check that root logger has handlers
        root_logger = logging.getLogger()
        # Should have at least one handler (console)
        assert any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers)
        # Cleanup: reset logging
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
    
    def test_setup_logging_file_only(self, tmp_path):
        """Test setting up logging with file only."""
        log_dir = tmp_path / "logs"
        setup_logging(
            log_level='DEBUG',
            log_to_file=True,
            log_to_console=False,
            log_dir=str(log_dir)
        )
        # Check that log directory was created
        assert log_dir.exists()
        # Check that a log file was created
        log_files = list(log_dir.glob("*.log"))
        # There should be at least one log file
        assert len(log_files) > 0
        # Cleanup
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
    
    def test_setup_logging_both(self, tmp_path):
        """Test setting up logging with both file and console."""
        log_dir = tmp_path / "logs"
        setup_logging(
            log_level='WARNING',
            log_to_file=True,
            log_to_console=True,
            log_dir=str(log_dir)
        )
        root_logger = logging.getLogger()
        # Should have both types of handlers
        has_console = any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                          for h in root_logger.handlers)
        has_file = any(isinstance(h, logging.FileHandler) for h in root_logger.handlers)
        assert has_console
        assert has_file
        # Cleanup
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
    
    def test_logger_levels(self, tmp_path):
        """Test different log levels."""
        log_dir = tmp_path / "logs"
        setup_logging(
            log_level='DEBUG',
            log_to_file=True,
            log_to_console=False,
            log_dir=str(log_dir)
        )
        logger = get_logger('test_levels')
        
        # Log messages at different levels
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        
        # Check that log file contains messages
        log_files = list(log_dir.glob("*.log"))
        if log_files:
            with open(log_files[0], 'r') as f:
                content = f.read()
                assert "Debug message" in content
                assert "Info message" in content
                assert "Warning message" in content
                assert "Error message" in content
        
        # Cleanup
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
