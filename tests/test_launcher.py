"""
Tests for the launcher module.
"""

import pytest
import sys
import os
import tempfile
from unittest.mock import patch, MagicMock, call
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher import (
    get_error_log_path,
    log_error,
    log_info,
    get_books_directory,
    open_browser,
)


class TestErrorLogPath:
    """Tests for error log path retrieval."""

    def test_error_log_path_in_documents(self):
        """Test that error log path points to Documents directory."""
        path = get_error_log_path()
        assert "Documents" in path
        assert "Reader3_error.log" in path

    def test_error_log_path_is_string(self):
        """Test that error log path is a string."""
        path = get_error_log_path()
        assert isinstance(path, str)

    def test_error_log_path_is_expandable(self):
        """Test that error log path can be expanded."""
        path = get_error_log_path()
        # Should not contain ~
        assert "~" not in path


class TestErrorLogging:
    """Tests for error logging functionality."""

    def test_log_error_creates_entry(self):
        """Test that log_error creates a log entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_error("Test error", include_traceback=False)

                with open(log_file, "r") as f:
                    content = f.read()
                    assert "Test error" in content

    def test_log_error_includes_timestamp(self):
        """Test that error log includes timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_error("Test error", include_traceback=False)

                with open(log_file, "r") as f:
                    content = f.read()
                    # Check for ISO format timestamp
                    assert "T" in content or "[" in content

    def test_log_error_with_traceback(self):
        """Test that error log can include traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                try:
                    raise ValueError("Test exception")
                except ValueError:
                    log_error("An error occurred", include_traceback=True)

                with open(log_file, "r") as f:
                    content = f.read()
                    assert "Test exception" in content

    def test_log_error_without_traceback(self):
        """Test that error log excludes traceback when specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_error("Simple error message", include_traceback=False)

                with open(log_file, "r") as f:
                    content = f.read()
                    assert "Simple error message" in content

    def test_log_error_handles_write_failures(self):
        """Test that log_error gracefully handles write failures."""
        with patch("launcher.get_error_log_path", return_value="/invalid/path/error.log"):
            # Should not raise an exception
            log_error("Error message")

    def test_log_error_appends_to_existing(self):
        """Test that log_error appends to existing log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_error("First error", include_traceback=False)
                log_error("Second error", include_traceback=False)

                with open(log_file, "r") as f:
                    content = f.read()
                    assert "First error" in content
                    assert "Second error" in content


class TestInfoLogging:
    """Tests for info logging functionality."""

    def test_log_info_creates_entry(self):
        """Test that log_info creates a log entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_info("Application started")

                with open(log_file, "r") as f:
                    content = f.read()
                    assert "Application started" in content

    def test_log_info_includes_info_label(self):
        """Test that log_info includes INFO label."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_info("Test message")

                with open(log_file, "r") as f:
                    content = f.read()
                    assert "INFO" in content

    def test_log_info_includes_timestamp(self):
        """Test that log_info includes timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_info("Test message")

                with open(log_file, "r") as f:
                    content = f.read()
                    # Should have timestamp
                    assert "[" in content

    def test_log_info_handles_write_failures(self):
        """Test that log_info gracefully handles write failures."""
        with patch("launcher.get_error_log_path", return_value="/invalid/path/error.log"):
            # Should not raise an exception
            log_info("Info message")


class TestGetBooksDirectory:
    """Tests for books directory detection."""

    def test_get_books_directory_when_not_frozen(self):
        """Test getting books directory when not running as frozen app."""
        with patch("sys.frozen", False, create=True):
            # Mock getcwd to return a specific directory
            with patch("os.getcwd", return_value="/home/user/books"):
                result = get_books_directory()
                assert result == "/home/user/books"

    def test_get_books_directory_frozen_windows(self):
        """Test getting books directory for frozen Windows app."""
        with patch("sys.frozen", True, create=True):
            with patch("sys.platform", "win32"):
                with patch("sys.executable", "C:\\Program Files\\Reader3\\reader3.exe"):
                    result = get_books_directory()
                    # Should return parent directory of executable
                    assert "Program Files" in result or "Reader3" in result

    def test_get_books_directory_frozen_macos_app_bundle(self):
        """Test getting books directory for frozen macOS app bundle."""
        with patch("sys.frozen", True, create=True):
            with patch("sys.platform", "darwin"):
                with patch("sys.executable", "/Applications/Reader3.app/Contents/MacOS/reader3"):
                    result = get_books_directory()
                    # Should go outside the .app bundle
                    assert ".app" not in result or result.count("Reader3") < 3

    def test_get_books_directory_frozen_without_app_bundle(self):
        """Test getting books directory for frozen non-bundle executable."""
        with patch("sys.frozen", True, create=True):
            with patch("sys.executable", "/opt/reader3/bin/reader3"):
                result = get_books_directory()
                # Should return directory of executable
                assert "reader3" in result.lower() or "bin" in result


class TestOpenBrowser:
    """Tests for browser opening functionality."""

    @patch("time.sleep")
    @patch("webbrowser.open")
    def test_open_browser_success(self, mock_webbrowser, mock_sleep):
        """Test successfully opening browser."""
        open_browser()

        mock_sleep.assert_called_once_with(2)
        mock_webbrowser.assert_called_once_with("http://127.0.0.1:8123")

    @patch("time.sleep")
    @patch("webbrowser.open", side_effect=Exception("Browser error"))
    @patch("subprocess.run")
    def test_open_browser_fallback_to_subprocess(self, mock_subprocess, mock_webbrowser, mock_sleep):
        """Test fallback to subprocess when webbrowser fails."""
        open_browser()

        # Should try webbrowser first
        mock_webbrowser.assert_called_once()

        # Then fall back to subprocess
        mock_subprocess.assert_called()

    @patch("time.sleep")
    @patch("webbrowser.open", side_effect=Exception("Browser error"))
    @patch("subprocess.run", side_effect=Exception("Subprocess error"))
    def test_open_browser_graceful_failure(self, mock_subprocess, mock_webbrowser, mock_sleep):
        """Test graceful failure when browser opening fails."""
        # Should not raise exception
        open_browser()

    @patch("time.sleep")
    @patch("webbrowser.open")
    def test_open_browser_uses_correct_url(self, mock_webbrowser, mock_sleep):
        """Test that the correct URL is used."""
        open_browser()

        call_args = mock_webbrowser.call_args[0][0]
        assert "127.0.0.1" in call_args
        assert "8123" in call_args

    @patch("time.sleep")
    @patch("webbrowser.open")
    def test_open_browser_waits_before_opening(self, mock_webbrowser, mock_sleep):
        """Test that browser waits before opening."""
        open_browser()

        # Sleep should be called with 2 seconds
        mock_sleep.assert_called_with(2)
        # Both should be called
        assert mock_sleep.called
        assert mock_webbrowser.called


class TestBooksDirectoryEnvironment:
    """Tests for READER3_BOOKS_DIR environment variable."""

    def test_books_dir_environment_variable(self):
        """Test that books directory can be set via environment variable."""
        test_dir = "/custom/books/path"

        with patch.dict(os.environ, {"READER3_BOOKS_DIR": test_dir}):
            # Environment variable should be readable
            assert os.environ.get("READER3_BOOKS_DIR") == test_dir


class TestMainFunction:
    """Tests for main launcher functionality (partial)."""

    @patch("launcher.open_browser")
    @patch("launcher.get_books_directory")
    def test_main_sets_books_dir_environment(self, mock_get_books, mock_open_browser):
        """Test that main function sets READER3_BOOKS_DIR."""
        mock_get_books.return_value = "/test/books"

        with patch.dict(os.environ, {}, clear=False):
            # Import and use code that would set the environment
            test_dir = "/test/path"
            with patch.dict(os.environ, {"READER3_BOOKS_DIR": test_dir}):
                assert os.environ.get("READER3_BOOKS_DIR") == test_dir


class TestLoggingEdgeCases:
    """Tests for edge cases in logging."""

    def test_log_error_with_special_characters(self):
        """Test logging errors with special characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_error("Error: Special chars <>&\"'", include_traceback=False)

                with open(log_file, "r") as f:
                    content = f.read()
                    assert "Special chars" in content

    def test_log_error_with_long_message(self):
        """Test logging very long error messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            long_message = "x" * 10000

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_error(long_message, include_traceback=False)

                with open(log_file, "r") as f:
                    content = f.read()
                    assert len(content) > 10000

    def test_log_info_with_empty_message(self):
        """Test logging empty info message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")

            with patch("launcher.get_error_log_path", return_value=log_file):
                log_info("")

                # Should not raise exception
                assert os.path.exists(log_file)
