"""
Additional edge case tests for utils/progress.py to improve coverage.
"""
import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.support.progress import (
    ProgressIndicator,
    ProgressStyle,
    track_progress,
)


class TestProgressIndicatorEdgeCases:
    """Edge case tests for ProgressIndicator."""
    
    def test_progress_indicator_with_zero_total(self):
        """Test ProgressIndicator with zero total."""
        progress = ProgressIndicator(total=0, style=ProgressStyle.SILENT)
        progress.start()
        progress.finish()
        assert progress.completed is True
    
    def test_progress_indicator_with_none_description(self):
        """Test with None description."""
        progress = ProgressIndicator(total=100, description=None, style=ProgressStyle.SILENT)
        progress.start()
        progress.update(50)
        progress.finish()
        assert progress.completed is True
    
    def test_progress_indicator_with_empty_description(self):
        """Test with empty description."""
        progress = ProgressIndicator(total=100, description="", style=ProgressStyle.SILENT)
        progress.start()
        progress.update(50)
        progress.finish()
        assert progress.completed is True
    
    def test_progress_indicator_with_very_large_total(self):
        """Test with very large total."""
        progress = ProgressIndicator(total=10**6, style=ProgressStyle.SILENT)
        progress.start()
        progress.update(500000)
        progress.finish()
        assert progress.completed is True
    
    def test_progress_indicator_spinner_style(self):
        """Test spinner style."""
        progress = ProgressIndicator(total=100, style=ProgressStyle.SPINNER)
        progress.start()
        progress.update(50)
        progress.finish()
        assert progress.completed is True
    
    def test_progress_indicator_counter_style(self):
        """Test counter style."""
        progress = ProgressIndicator(total=100, style=ProgressStyle.COUNTER)
        progress.start()
        progress.update(50)
        progress.finish()
        assert progress.completed is True
    
    def test_progress_indicator_bar_style(self):
        """Test bar style."""
        progress = ProgressIndicator(total=100, style=ProgressStyle.BAR, bar_width=20)
        progress.start()
        progress.update(75)
        progress.finish()
        assert progress.completed is True
    
    def test_progress_indicator_percentage_style(self):
        """Test percentage style."""
        progress = ProgressIndicator(total=100, style=ProgressStyle.PERCENTAGE)
        progress.start()
        progress.update(25)
        progress.finish()
        assert progress.completed is True
    
    # Context manager test depends on __enter__/__exit__ implementation details
    def test_track_progress_with_generator(self):
        """Test track_progress with a generator."""
        data = range(10)
        result = []
        for item in track_progress(data, description="Testing"):
            result.append(item)
        assert len(result) == 10
    
    def test_track_progress_with_list(self):
        """Test track_progress with a list."""
        data = [1, 2, 3, 4, 5]
        result = list(track_progress(data, description="Testing"))
        assert result == data
    
    def test_track_progress_with_empty_iterable(self):
        """Test track_progress with empty iterable."""
        data = []
        result = list(track_progress(data, description="Testing"))
        assert result == []
    
    def test_track_progress_with_description_none(self):
        """Test track_progress with None description."""
        data = [1, 2, 3]
        result = list(track_progress(data, description=None))
        assert len(result) == 3
