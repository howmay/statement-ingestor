"""
Unit tests for progress indicator utility.
"""
import sys
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.utils.progress import (
    ProgressIndicator,
    ProgressStyle,
    track_progress,
    MultiProgress
)


class TestProgressIndicator:
    """Test suite for progress indicators."""
    
    def test_progress_indicator_start_stop(self):
        """Test ProgressIndicator start and stop."""
        progress = ProgressIndicator(total=100, description="Testing", style=ProgressStyle.SILENT)
        
        assert not hasattr(progress, 'started') or not progress._started
        progress.start()
        assert progress.start_time is not None
        assert progress.total == 100
        assert progress.current == 0
        
        progress.update(10)
        assert progress.current == 10
        
        progress.finish()
        assert progress.completed is True
    
    def test_progress_indicator_update(self):
        """Test updating ProgressIndicator."""
        progress = ProgressIndicator(total=10, style=ProgressStyle.SILENT)
        progress.start()
        
        # Update without description
        progress.update(5)
        assert progress.current == 5
        
        # Update with description
        progress.update(3, "Processing item")
        assert progress.current == 8
        
        progress.finish()
    
    def test_progress_spinner_style(self):
        """Test spinner style progress indicator."""
        progress = ProgressIndicator(
            total=0,  # indeterminate spinner
            description="Spinning",
            style=ProgressStyle.SPINNER
        )
        
        assert progress.style == ProgressStyle.SPINNER
        progress.start()
        # Spinner should have a spinner index
        assert hasattr(progress, 'spinner_chars')
        time.sleep(0.1)
        progress.finish()
        assert progress.completed is True
    
    def test_progress_context_manager(self):
        """Test using progress indicator as context manager."""
        with ProgressIndicator(total=5, description="Context test", style=ProgressStyle.SILENT) as progress:
            for i in range(5):
                progress.update(1)
                assert progress.current == i + 1
        
        assert progress.completed
    
    def test_track_progress_generator(self):
        """Test track_progress generator function."""
        items = list(range(10))
        
        # Track progress
        tracked = track_progress(items, total=10, description="Items")
        
        # Consume the tracked items
        count = 0
        for item in tracked:
            count += 1
            assert item in items
        
        assert count == 10
    
    def test_multi_progress(self):
        """Test MultiProgress manager."""
        manager = MultiProgress()
        ind1 = manager.add("op1", total=10, description="First")
        ind2 = manager.add("op2", total=20, description="Second")
        
        assert manager.get("op1") is ind1
        assert manager.get("op2") is ind2
        
        # Should raise on duplicate
        with pytest.raises(ValueError):
            manager.add("op1", total=5)
        
        manager.remove("op1")
        assert manager.get("op1") is None
        
        manager.clear()
        assert len(manager.indicators) == 0
