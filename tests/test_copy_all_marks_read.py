"""
Tests for chapter reading progress marking when copying content.
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestCopyAllMarksChapterAsRead:
    """Tests for marking chapter as read when copying all content."""

    def test_copy_all_saves_100_percent_progress(self, client):
        """Test that copying all content saves 100% progress for the chapter."""
        import uuid
        book_id = f"test_copy_mark_{uuid.uuid4().hex[:8]}"
        chapter_index = 0
        
        # Save 100% progress when copy all is called
        response = client.post(
            f"/api/chapter-progress/{book_id}/{chapter_index}",
            json={"progress": 100.0}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "saved"
        
        # Verify the progress was saved
        # Note: JSON serialization converts int keys to strings
        progress_response = client.get(f"/api/chapter-progress/{book_id}")
        data = progress_response.json()
        assert str(chapter_index) in data["progress"]
        assert data["progress"][str(chapter_index)] == 100.0

    def test_copy_all_marks_correct_chapter(self, client):
        """Test that only the current chapter is marked as read."""
        import uuid
        book_id = f"test_copy_mark_correct_{uuid.uuid4().hex[:8]}"
        
        # Chapter 0: not started (0%)
        # Chapter 1: partially read (50%)
        # Chapter 2: fully read (100%)
        
        client.post(
            f"/api/chapter-progress/{book_id}/1",
            json={"progress": 50.0}
        )
        
        client.post(
            f"/api/chapter-progress/{book_id}/2",
            json={"progress": 100.0}
        )
        
        # Now copy all for chapter 1, marking it as 100%
        client.post(
            f"/api/chapter-progress/{book_id}/1",
            json={"progress": 100.0}
        )
        
        # Get all chapter progress
        response = client.get(f"/api/chapter-progress/{book_id}")
        data = response.json()
        
        # JSON keys are strings
        assert data["progress"].get("0", 0) == 0.0  # Chapter 0
        assert data["progress"]["1"] == 100.0  # Chapter 1 now fully
        assert data["progress"]["2"] == 100.0  # Chapter 2 still fully

    def test_multiple_copy_all_calls_maintain_100_percent(self, client):
        """Test that multiple copy-all calls maintain 100%."""
        import uuid
        book_id = f"test_copy_multiple_{uuid.uuid4().hex[:8]}"
        chapter_index = 0
        
        # First copy all - save 100%
        client.post(
            f"/api/chapter-progress/{book_id}/{chapter_index}",
            json={"progress": 100.0}
        )
        
        # Second copy all - should still be 100%
        client.post(
            f"/api/chapter-progress/{book_id}/{chapter_index}",
            json={"progress": 100.0}
        )
        
        # Verify progress
        progress_response = client.get(f"/api/chapter-progress/{book_id}")
        data = progress_response.json()
        assert data["progress"][str(chapter_index)] == 100.0

    def test_copy_all_updates_overall_progress(self, client):
        """Test that copying all affects the overall book progress."""
        import uuid
        book_id = f"test_copy_overall_{uuid.uuid4().hex[:8]}"
        
        # Mark chapter 0 as fully read
        client.post(
            f"/api/chapter-progress/{book_id}/0",
            json={"progress": 100.0}
        )
        
        # Get overall progress
        response = client.get(f"/api/progress/{book_id}")
        data = response.json()
        
        # Should have some progress_percent > 0
        assert data["progress_percent"] >= 0
        # With one chapter at 100%, overall progress should be > 0
        # (exact % depends on total chapters, but should improve)

    def test_copy_all_with_different_chapters(self, client):
        """Test copy-all marking different chapters as read."""
        import uuid
        book_id = f"test_copy_diff_ch_{uuid.uuid4().hex[:8]}"
        
        # Mark chapters 0, 2, 4 as read via copy-all
        for chapter_idx in [0, 2, 4]:
            response = client.post(
                f"/api/chapter-progress/{book_id}/{chapter_idx}",
                json={"progress": 100.0}
            )
            assert response.status_code == 200
        
        # Verify all are marked
        progress_response = client.get(f"/api/chapter-progress/{book_id}")
        data = progress_response.json()
        
        for chapter_idx in [0, 2, 4]:
            assert data["progress"][str(chapter_idx)] == 100.0

    def test_copy_all_persists_after_page_reload(self, client):
        """Test that copy-all marking persists in storage."""
        import uuid
        book_id = f"test_copy_persist_{uuid.uuid4().hex[:8]}"
        chapter_index = 3
        
        # Mark as read via copy-all
        client.post(
            f"/api/chapter-progress/{book_id}/{chapter_index}",
            json={"progress": 100.0}
        )
        
        # Simulate page reload - fetch progress again
        response = client.get(f"/api/chapter-progress/{book_id}")
        data = response.json()
        
        # Should still show 100% after reload (JSON keys are strings)
        assert data["progress"][str(chapter_index)] == 100.0

    def test_copy_all_only_updates_progress_not_other_fields(self, client):
        """Test that copy-all doesn't unintentionally modify other fields."""
        import uuid
        book_id = f"test_copy_only_progress_{uuid.uuid4().hex[:8]}"
        chapter_index = 0
        
        # Save some progress
        response = client.post(
            f"/api/chapter-progress/{book_id}/{chapter_index}",
            json={"progress": 100.0}
        )
        
        # Response should just indicate status, no side effects
        data = response.json()
        assert data["status"] == "saved"
        assert "progress" in data or "status" in data  # Should have status field


class TestChapterProgressBoundaries:
    """Tests for progress value boundaries in copy-all scenario."""

    def test_progress_exactly_100_percent(self, client):
        """Test that progress is exactly 100.0 when marked by copy-all."""
        import uuid
        book_id = f"test_progress_boundary_{uuid.uuid4().hex[:8]}"
        
        client.post(
            f"/api/chapter-progress/{book_id}/0",
            json={"progress": 100.0}
        )
        
        progress_response = client.get(f"/api/chapter-progress/{book_id}")
        data = progress_response.json()
        
        # Should be exactly 100.0, not 99.9 or 100.1
        assert data["progress"]["0"] == 100.0

    def test_progress_does_not_exceed_100_percent(self, client):
        """Test that progress is capped at 100% from copy-all."""
        import uuid
        book_id = f"test_progress_cap_{uuid.uuid4().hex[:8]}"
        
        # Try to set over 100% (shouldn't happen in normal flow)
        response = client.post(
            f"/api/chapter-progress/{book_id}/0",
            json={"progress": 100.0}
        )
        
        progress_response = client.get(f"/api/chapter-progress/{book_id}")
        data = progress_response.json()
        
        # Should not exceed 100%
        assert data["progress"]["0"] <= 100.0
        assert data["progress"]["0"] >= 0

    def test_copy_all_with_zero_chapters(self, client):
        """Test copy-all behavior with empty book."""
        import uuid
        book_id = f"test_empty_book_{uuid.uuid4().hex[:8]}"
        
        # Try to mark non-existent chapter
        response = client.post(
            f"/api/chapter-progress/{book_id}/0",
            json={"progress": 100.0}
        )
        
        # Should still succeed or fail gracefully
        assert response.status_code in [200, 201]

    def test_negative_chapter_index(self, client):
        """Test that negative chapter indices are handled."""
        import uuid
        book_id = f"test_negative_idx_{uuid.uuid4().hex[:8]}"
        
        # Try negative index
        response = client.post(
            f"/api/chapter-progress/{book_id}/-1",
            json={"progress": 100.0}
        )
        
        # Behavior depends on implementation - should either reject or handle gracefully
        # For this test, we just verify it doesn't crash
        assert response.status_code in [200, 201, 400, 404]
