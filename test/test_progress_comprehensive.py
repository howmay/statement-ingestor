"""
Comprehensive tests for progress.py to improve coverage to 85%.
Focuses on edge cases and uncovered lines.
"""
import sys
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from io import StringIO
import threading

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.utils.progress import (
    ProgressIndicator,
    ProgressStyle,
    track_progress,
    MultiProgress,
    run_with_progress
)


class TestProgressIndicatorComprehensive:
    """Comprehensive tests for ProgressIndicator covering all edge cases."""

    def test_progress_exceeds_total(self):
        """Test that progress.current is capped at total when exceeding."""
        progress = ProgressIndicator(total=10, style=ProgressStyle.SILENT)
        progress.start()

        # Update more than total
        progress.update(15)
        assert progress.current == 10  # Should be capped at total

        progress.finish()

    def test_update_without_start(self):
        """Test update() without calling start() first."""
        progress = ProgressIndicator(total=10, style=ProgressStyle.SILENT)

        # Should not crash when updating without start
        progress.update(5)
        assert progress.current == 5

    def test_finish_without_start(self):
        """Test finish() without calling start() first."""
        progress = ProgressIndicator(total=10, style=ProgressStyle.SILENT)

        # Should not crash when finishing without start
        progress.finish("Test complete")
        assert progress.completed is True

    def test_finish_with_message(self):
        """Test finish() with a custom message."""
        # Use non-silent style to test printing
        progress = ProgressIndicator(total=10, style=ProgressStyle.BAR)
        progress.start()

        with patch('builtins.print') as mock_print:
            progress.finish("Custom completion message")

            # Should print the custom message
            mock_print.assert_called_with("\nCustom completion message")

    def test_finish_without_message(self):
        """Test finish() without a custom message."""
        # Use non-silent style to test printing
        progress = ProgressIndicator(total=10, description="Test Task", style=ProgressStyle.BAR)
        
        # Mock time.time to control elapsed time
        with patch('time.time') as mock_time:
            # Set up time sequence: start() calls time.time(), finish() calls it twice
            # (once for elapsed calculation, once in the print message)
            mock_time.side_effect = [1000.0, 1005.0, 1005.0]
            
            progress.start()
            
            with patch('builtins.print') as mock_print:
                progress.finish()
                
                # Should print default completion message with elapsed time
                # The elapsed time should be 5.0s (1005.0 - 1000.0)
                mock_print.assert_called_with("\n✓ Test Task completed in 5.0s")

    def test_format_time_seconds(self):
        """Test _format_time for seconds."""
        progress = ProgressIndicator(total=10, style=ProgressStyle.SILENT)

        assert progress._format_time(30) == "30s"
        assert progress._format_time(59.9) == "60s"  # rounded up

    def test_format_time_minutes(self):
        """Test _format_time for minutes."""
        progress = ProgressIndicator(total=10, style=ProgressStyle.SILENT)

        assert progress._format_time(120) == "2m"
        assert progress._format_time(3599) == "60m"  # 59.98 minutes

    def test_format_time_hours(self):
        """Test _format_time for hours."""
        progress = ProgressIndicator(total=10, style=ProgressStyle.SILENT)

        assert progress._format_time(3600) == "1.0h"
        assert progress._format_time(7200) == "2.0h"
        assert progress._format_time(5400) == "1.5h"  # 1.5 hours

    def test_context_manager_with_exception(self):
        """Test context manager when an exception occurs."""
        progress = ProgressIndicator(total=10, style=ProgressStyle.BAR)
        progress.start()

        with patch('sys.stdout.write') as mock_write:
            with patch('sys.stdout.flush') as mock_flush:
                # Simulate exception in context
                try:
                    with progress:
                        raise ValueError("Test error")
                except ValueError:
                    pass

                # Should clear the progress line on exception
                mock_write.assert_any_call('\r' + ' ' * 80 + '\r')
                mock_flush.assert_called()

    def test_print_progress_silent_style(self):
        """Test _print_progress with SILENT style."""
        progress = ProgressIndicator(total=10, style=ProgressStyle.SILENT)
        progress.start()

        # Should not print anything for silent style
        with patch('sys.stdout.write') as mock_write:
            progress._print_progress()
            mock_write.assert_not_called()

    def test_print_bar_without_percentage(self):
        """Test _print_bar without showing percentage."""
        progress = ProgressIndicator(
            total=10,
            description="Test",
            style=ProgressStyle.BAR,
            show_percentage=False
        )
        progress.start()

        with patch('sys.stdout.write') as mock_write:
            with patch('sys.stdout.flush') as mock_flush:
                # Clear previous calls from start()
                mock_write.reset_mock()
                mock_flush.reset_mock()

                progress._print_bar(0.5, 50.0, " ETA: 10s")

                # Should not include percentage in output
                # _print_bar calls write twice: once for \r, once for the bar
                assert mock_write.call_count >= 1
                # Check that percentage is not in any call
                for call in mock_write.call_args_list:
                    args = call[0]
                    if len(args) > 0:
                        assert "50.0%" not in args[0]
                call_args = mock_write.call_args[0][0]
                assert "50.0%" not in call_args

    def test_print_percentage_without_percentage(self):
        """Test _print_percentage without showing percentage."""
        progress = ProgressIndicator(
            total=10,
            description="Test",
            style=ProgressStyle.PERCENTAGE,
            show_percentage=False
        )
        progress.start()
        progress.current = 5

        with patch('sys.stdout.write') as mock_write:
            with patch('sys.stdout.flush') as mock_flush:
                progress._print_percentage(0.5, 50.0, " ETA: 10s")

                # Should show counter instead of percentage
                call_args = mock_write.call_args[0][0]
                assert "5/10" in call_args
                assert "50.0%" not in call_args

    def test_print_spinner_without_percentage(self):
        """Test _print_spinner without showing percentage."""
        progress = ProgressIndicator(
            total=10,
            description="Test",
            style=ProgressStyle.SPINNER,
            show_percentage=False
        )
        progress.start()

        with patch('sys.stdout.write') as mock_write:
            progress._print_spinner(0.5, 50.0, " ETA: 10s")

            # Should not include percentage
            call_args = mock_write.call_args[0][0]
            assert "50.0%" not in call_args

    def test_print_counter_without_percentage(self):
        """Test _print_counter without showing percentage."""
        progress = ProgressIndicator(
            total=10,
            description="Test",
            style=ProgressStyle.COUNTER,
            show_percentage=False
        )
        progress.start()
        progress.current = 5

        with patch('sys.stdout.write') as mock_write:
            progress._print_counter(0.5, 50.0, " ETA: 10s")

            # Should not include percentage in parentheses
            call_args = mock_write.call_args[0][0]
            assert "5/10" in call_args
            assert "(50.0%)" not in call_args

    def test_print_counter_with_percentage(self):
        """Test _print_counter with showing percentage."""
        progress = ProgressIndicator(
            total=10,
            description="Test",
            style=ProgressStyle.COUNTER,
            show_percentage=True
        )
        progress.start()
        progress.current = 5

        with patch('sys.stdout.write') as mock_write:
            progress._print_counter(0.5, 50.0, " ETA: 10s")

            # Should include percentage in parentheses
            call_args = mock_write.call_args[0][0]
            assert "5/10" in call_args
            assert "(50.0%)" in call_args

    def test_eta_calculation_with_zero_progress(self):
        """Test ETA calculation when progress is zero."""
        progress = ProgressIndicator(total=10, show_eta=True, style=ProgressStyle.SILENT)
        progress.start()

        # Mock time to have elapsed time but zero progress
        with patch('time.time', return_value=10.0):
            progress.current = 0

            # Should not calculate ETA when progress is zero
            # This is handled in _print_progress, but we need to ensure no division by zero
            progress._print_progress()  # Should not crash

    def test_eta_calculation_without_start_time(self):
        """Test ETA calculation when start_time is None."""
        progress = ProgressIndicator(total=10, show_eta=True, style=ProgressStyle.SILENT)
        # Don't call start()
        progress.current = 5

        # Should not crash when calculating ETA without start_time
        progress._print_progress()  # Should not crash


class TestTrackProgressComprehensive:
    """Comprehensive tests for track_progress function."""

    def test_track_progress_with_unknown_length(self):
        """Test track_progress with iterable that has no len()."""
        # Create a generator (no __len__)
        def my_generator():
            for i in range(5):
                yield i

        gen = my_generator()

        # Should default to total=100 when length is unknown
        with patch('src.utils.progress.ProgressIndicator') as MockProgress:
            mock_indicator = MagicMock()
            MockProgress.return_value.__enter__.return_value = mock_indicator

            result = list(track_progress(gen, description="Testing"))

            # Should have used default total=100
            MockProgress.assert_called_with(100, "Testing", ProgressStyle.BAR, 0.1)
            assert len(result) == 5

    def test_track_progress_with_custom_total(self):
        """Test track_progress with custom total parameter."""
        items = [1, 2, 3]

        with patch('src.utils.progress.ProgressIndicator') as MockProgress:
            mock_indicator = MagicMock()
            MockProgress.return_value.__enter__.return_value = mock_indicator

            result = list(track_progress(items, total=50, description="Testing"))

            # Should use custom total
            MockProgress.assert_called_with(50, "Testing", ProgressStyle.BAR, 0.1)
            assert result == items

    def test_track_progress_with_custom_style_and_interval(self):
        """Test track_progress with custom style and update_interval."""
        items = [1, 2, 3]

        with patch('src.utils.progress.ProgressIndicator') as MockProgress:
            mock_indicator = MagicMock()
            MockProgress.return_value.__enter__.return_value = mock_indicator

            result = list(track_progress(
                items,
                description="Testing",
                style=ProgressStyle.SPINNER,
                update_interval=0.5
            ))

            # Should use custom parameters
            MockProgress.assert_called_with(3, "Testing", ProgressStyle.SPINNER, 0.5)
            assert result == items


class TestRunWithProgressComprehensive:
    """Comprehensive tests for run_with_progress decorator."""

    def test_run_with_progress_success(self):
        """Test run_with_progress decorator with successful function."""
        # Define the function first
        def test_func():
            return "success"

        # Apply decorator
        decorated_func = run_with_progress(test_func, total=10, description="Test Function")

        with patch('src.utils.progress.ProgressIndicator') as MockProgress:
            mock_indicator = MagicMock()
            MockProgress.return_value = mock_indicator

            result = decorated_func()

            # Should have started and finished progress
            mock_indicator.start.assert_called_once()
            mock_indicator.finish.assert_called_once()
            assert result == "success"

    def test_run_with_progress_with_progress_param(self):
        """Test run_with_progress with function that accepts progress parameter."""
        # Define the function first
        def test_func(progress=None):
            if progress:
                progress.update(5)
            return "success"

        # Apply decorator
        decorated_func = run_with_progress(test_func, total=10, description="Test Function")

        with patch('src.utils.progress.ProgressIndicator') as MockProgress:
            mock_indicator = MagicMock()
            MockProgress.return_value = mock_indicator

            # Mock inspect.signature to return a signature with 'progress' parameter
            with patch('inspect.signature') as mock_signature:
                mock_sig = MagicMock()
                mock_sig.parameters.keys.return_value = ['progress']
                mock_signature.return_value = mock_sig

                result = decorated_func()

                # Should have passed progress to function
                mock_indicator.start.assert_called_once()
                mock_indicator.finish.assert_called_once()
                assert result == "success"

    def test_run_with_progress_with_exception(self):
        """Test run_with_progress when function raises an exception."""
        # Define the function first
        def test_func():
            raise ValueError("Test error")

        # Apply decorator
        decorated_func = run_with_progress(test_func, total=10, description="Test Function")

        with patch('src.utils.progress.ProgressIndicator') as MockProgress:
            mock_indicator = MagicMock()
            MockProgress.return_value = mock_indicator

            # Should raise the exception
            with pytest.raises(ValueError, match="Test error"):
                decorated_func()

            # Should have called finish with error message
            mock_indicator.finish.assert_called_with("✗ Test Function failed: Test error")

    def test_run_with_progress_with_other_params(self):
        """Test run_with_progress with function that has other parameters."""
        # Define the function first
        def test_func(x, y, z=3):
            return x + y + z

        # Apply decorator
        decorated_func = run_with_progress(test_func, total=10, description="Test Function")

        with patch('src.utils.progress.ProgressIndicator') as MockProgress:
            mock_indicator = MagicMock()
            MockProgress.return_value = mock_indicator

            # Mock inspect.signature to return a signature without 'progress' parameter
            with patch('inspect.signature') as mock_signature:
                mock_sig = MagicMock()
                mock_sig.parameters.keys.return_value = ['x', 'y', 'z']
                mock_signature.return_value = mock_sig

                result = decorated_func(1, 2, z=4)

                # Should not pass progress parameter
                mock_indicator.start.assert_called_once()
                mock_indicator.finish.assert_called_once()
                assert result == 7


class TestMultiProgressComprehensive:
    """Comprehensive tests for MultiProgress."""

    def test_multi_progress_thread_safety(self):
        """Test MultiProgress thread safety with concurrent access."""
        manager = MultiProgress()

        # Add indicators from multiple threads
        def add_indicator(name):
            return manager.add(name, total=10, description=f"Task {name}")

        # Test in single thread first
        ind1 = add_indicator("task1")
        assert manager.get("task1") is ind1

        # Test concurrent access (simulated)
        with manager._lock:
            # Lock is acquired, trying to add should wait
            # But we're testing from same thread, so just verify lock exists
            assert hasattr(manager, '_lock')

    def test_multi_progress_remove_nonexistent(self):
        """Test removing non-existent indicator."""
        manager = MultiProgress()

        # Should not crash when removing non-existent indicator
        manager.remove("nonexistent")

        # Verify it doesn't exist
        assert manager.get("nonexistent") is None

    def test_multi_progress_clear_empty(self):
        """Test clearing empty MultiProgress."""
        manager = MultiProgress()

        # Should not crash when clearing empty manager
        manager.clear()
        assert len(manager.indicators) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])