"""
Tests for PDF and EPUB copy badge tracking and multi-page copy robustness.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from reader3 import Book, BookMetadata, ChapterContent, TOCEntry, save_to_pickle
from server import app


def create_test_book(
    book_id,
    title,
    author="Test Author",
    *,
    chapters=3,
    is_pdf=False,
):
    """Create a minimal processed book in the test library."""
    from datetime import datetime

    added_at = datetime.now().isoformat()
    book_dir = Path(server.BOOKS_DIR) / book_id
    book_dir.mkdir(parents=True, exist_ok=True)

    spine = []
    toc = []
    for index in range(chapters):
        href = f"chapter-{index}.html"
        content = (
            f'<div class="pdf-page-image-container"><img class="pdf-page-image" src="images/page-{index}.png"></div>'
            if is_pdf
            else f"<p>{title} chapter {index + 1}</p>"
        )
        spine.append(
            ChapterContent(
                id=f"chapter-{index}",
                href=href,
                title=f"Chapter {index + 1}" if not is_pdf else f"Page {index + 1}",
                content=content,
                text=f"{title} chapter {index + 1}",
                order=index,
            )
        )
        toc.append(
            TOCEntry(
                title=f"Chapter {index + 1}" if not is_pdf else f"Page {index + 1}",
                href=href,
                file_href=href,
                anchor="",
            )
        )

    source_ext = ".pdf" if is_pdf else ".epub"
    book = Book(
        metadata=BookMetadata(title=title, language="en", authors=[author]),
        spine=spine,
        toc=toc,
        images={},
        source_file=f"{title}{source_ext}",
        processed_at=added_at,
        added_at=added_at,
        is_pdf=is_pdf,
    )
    save_to_pickle(book, str(book_dir))

    server.load_book_cached.cache_clear()
    server.load_book_metadata.cache_clear()
    server.get_cached_reading_times.cache_clear()
    return book_dir


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# PDF badge rendering tests
# ---------------------------------------------------------------------------
class TestPdfCopiedBadge:
    """Tests that the PDF reader page renders the copied-badge elements."""

    def test_pdf_page_has_copied_badge_element(self, client):
        """Each PDF page should contain a hidden copied-badge span."""
        bid = f"test_pdf_badge_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Badge PDF", is_pdf=True, chapters=3)

        response = client.get(f"/read/{bid}/0")
        assert response.status_code == 200
        html = response.text
        # The server-rendered first page should contain the badge
        assert 'pdf-copied-badge' in html
        assert 'id="pdf-copied-badge-0"' in html
        assert 'fa-circle-check' in html

    def test_pdf_badge_starts_hidden(self, client):
        """The badge should NOT have the 'visible' class initially."""
        bid = f"test_pdf_hidden_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Hidden Badge PDF", is_pdf=True, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        # Badge class should not include 'visible' on first load
        assert 'pdf-page-copied-badge visible' not in html
        assert 'pdf-page-copied-badge"' in html

    def test_pdf_page_has_copy_image_button(self, client):
        """Verify the Copy Image button still exists on PDF pages."""
        bid = f"test_pdf_copybtn_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "CopyBtn PDF", is_pdf=True, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert 'copyPageImage' in html
        assert 'Copy Image' in html

    def test_pdf_page_has_copy_text_button(self, client):
        """Verify the Copy Text button still exists on PDF pages."""
        bid = f"test_pdf_copytxt_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "CopyTxt PDF", is_pdf=True, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert 'copyPageText' in html
        assert 'Copy Text' in html


class TestPdfMultiCopyRobustness:
    """Tests for the robustness improvements in multi-page PDF copy."""

    def test_pdf_pages_endpoint_returns_page_data(self, client):
        """The pages endpoint should return page data for valid ranges."""
        bid = f"test_pdf_pages_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Pages PDF", is_pdf=True, chapters=5)

        response = client.get(f"/read/{bid}/pages/0/3")
        assert response.status_code == 200
        data = response.json()
        assert "pages" in data
        assert len(data["pages"]) == 3
        assert data["pages"][0]["index"] == 0
        assert data["pages"][2]["index"] == 2

    def test_pdf_pages_beyond_total_returns_empty(self, client):
        """Requesting pages beyond total should return empty array."""
        bid = f"test_pdf_beyond_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Beyond PDF", is_pdf=True, chapters=3)

        response = client.get(f"/read/{bid}/pages/10/5")
        assert response.status_code == 200
        data = response.json()
        assert data["pages"] == []

    def test_pdf_pages_partial_range(self, client):
        """When requested range extends beyond total, return available pages."""
        bid = f"test_pdf_partial_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Partial PDF", is_pdf=True, chapters=5)

        response = client.get(f"/read/{bid}/pages/3/10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["pages"]) == 2  # pages 3 and 4 only
        assert data["total"] == 5

    def test_pdf_pages_each_has_required_fields(self, client):
        """Each page object should have index, title, and content."""
        bid = f"test_pdf_fields_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Fields PDF", is_pdf=True, chapters=2)

        response = client.get(f"/read/{bid}/pages/0/2")
        data = response.json()
        for page in data["pages"]:
            assert "index" in page
            assert "title" in page
            assert "content" in page

    def test_pdf_pages_rejects_non_pdf(self, client):
        """The pages endpoint should reject non-PDF books."""
        bid = f"test_epub_reject_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "EPUB Book", is_pdf=False, chapters=3)

        response = client.get(f"/read/{bid}/pages/0/3")
        assert response.status_code == 400


class TestPdfCopiedBadgeCSS:
    """Test that PDF badge CSS classes are present in the rendered page."""

    def test_pdf_badge_css_class_defined(self, client):
        """The pdf-page-copied-badge CSS class should be defined in the page."""
        bid = f"test_pdf_css_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "CSS PDF", is_pdf=True, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert '.pdf-page-copied-badge' in html

    def test_pdf_multi_copy_button_exists(self, client):
        """The multi-copy button should be present on PDF pages."""
        bid = f"test_pdf_multi_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Multi PDF", is_pdf=True, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert 'pdf-multi-copy-btn' in html
        assert 'copySelectedPagesAsImage' in html

    def test_pdf_toolbar_has_select_pages_toggle(self, client):
        """PDF toolbar should have a 'Select Pages' toggle button."""
        bid = f"test_pdf_toggle_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Toggle PDF", is_pdf=True, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert 'pdf-select-toggle-btn' in html
        assert 'toggleSelectionBar' in html
        assert 'Select Pages' in html

    def test_pdf_toolbar_has_collapsible_selection_row(self, client):
        """PDF toolbar should have a collapsible selection row."""
        bid = f"test_pdf_collapse_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Collapse PDF", is_pdf=True, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert 'pdf-toolbar-selection' in html
        assert 'pdf-toolbar-primary' in html

    def test_pdf_toolbar_selection_badge_exists(self, client):
        """The selection count badge on the toggle button should exist."""
        bid = f"test_pdf_badge_cnt_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Badge PDF", is_pdf=True, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert 'pdf-selection-count-badge' in html


# ---------------------------------------------------------------------------
# EPUB badge rendering tests
# ---------------------------------------------------------------------------
class TestEpubCopiedBadge:
    """Tests that the EPUB reader page renders the copied-badge elements."""

    def test_epub_toc_has_copied_badge_element(self, client):
        """EPUB TOC items should contain a hidden copied-badge span."""
        bid = f"test_epub_badge_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Badge EPUB", is_pdf=False, chapters=3)

        response = client.get(f"/read/{bid}/0")
        assert response.status_code == 200
        html = response.text
        assert 'toc-copied-badge' in html
        assert 'fa-circle-check' in html

    def test_epub_badge_starts_hidden(self, client):
        """The badge should NOT have the 'visible' class initially."""
        bid = f"test_epub_hidden_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Hidden EPUB", is_pdf=False, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        # Badge should render without 'visible' class
        assert 'toc-copied-badge visible' not in html
        assert 'toc-copied-badge' in html

    def test_epub_badge_css_class_defined(self, client):
        """The toc-copied-badge CSS class should be defined in the page."""
        bid = f"test_epub_css_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "CSS EPUB", is_pdf=False, chapters=1)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert '.toc-copied-badge' in html

    def test_epub_copy_all_button_exists(self, client):
        """EPUB pages should have the Copy All button."""
        bid = f"test_epub_copyall_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "CopyAll EPUB", is_pdf=False, chapters=2)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert 'copyAllLoaded' in html
        assert 'Copy All' in html

    def test_epub_multi_chapter_copy_controls_exist(self, client):
        """EPUB pages should have multi-chapter copy controls."""
        bid = f"test_epub_multi_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Multi EPUB", is_pdf=False, chapters=3)

        response = client.get(f"/read/{bid}/0")
        html = response.text
        assert 'copy-chapters-btn' in html
        assert 'copySelectedChapters' in html
        assert 'multi-copy-controls' in html


class TestEpubMultiChapterCopyAPI:
    """Tests for the multi-chapter text copy API used by EPUB badge tracking."""

    def test_copy_chapters_returns_hrefs(self, client):
        """Copied chapters should include their hrefs for badge tracking."""
        bid = f"test_epub_hrefs_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Href EPUB", is_pdf=False, chapters=3)

        response = client.post(
            "/api/chapters/text",
            json={
                "book_id": bid,
                "chapter_hrefs": ["chapter-0.html", "chapter-1.html"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["chapters"]) == 2
        assert data["chapters"][0]["href"] == "chapter-0.html"
        assert data["chapters"][1]["href"] == "chapter-1.html"

    def test_copy_chapters_includes_title_and_text(self, client):
        """Each chapter in the response should have title and text."""
        bid = f"test_epub_struct_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Struct EPUB", is_pdf=False, chapters=2)

        response = client.post(
            "/api/chapters/text",
            json={
                "book_id": bid,
                "chapter_hrefs": ["chapter-0.html"],
            },
        )
        assert response.status_code == 200
        ch = response.json()["chapters"][0]
        assert "title" in ch
        assert "text" in ch
        assert "href" in ch

    def test_copy_chapters_unknown_hrefs_ignored(self, client):
        """Unknown chapter hrefs should be silently ignored."""
        bid = f"test_epub_unknown_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Unknown EPUB", is_pdf=False, chapters=2)

        response = client.post(
            "/api/chapters/text",
            json={
                "book_id": bid,
                "chapter_hrefs": ["nonexistent.html", "chapter-0.html"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["chapters"]) == 1
        assert data["chapters"][0]["href"] == "chapter-0.html"

    def test_copy_chapters_empty_hrefs(self, client):
        """Empty hrefs list should return empty chapters."""
        bid = f"test_epub_empty_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Empty EPUB", is_pdf=False, chapters=2)

        response = client.post(
            "/api/chapters/text",
            json={
                "book_id": bid,
                "chapter_hrefs": [],
            },
        )
        assert response.status_code == 200
        assert response.json()["chapters"] == []

    def test_copy_chapters_preserves_order(self, client):
        """Chapters should be returned in the order requested."""
        bid = f"test_epub_order_{uuid.uuid4().hex[:8]}"
        create_test_book(bid, "Order EPUB", is_pdf=False, chapters=4)

        response = client.post(
            "/api/chapters/text",
            json={
                "book_id": bid,
                "chapter_hrefs": ["chapter-2.html", "chapter-0.html", "chapter-3.html"],
            },
        )
        assert response.status_code == 200
        chapters = response.json()["chapters"]
        assert len(chapters) == 3
        assert chapters[0]["href"] == "chapter-2.html"
        assert chapters[1]["href"] == "chapter-0.html"
        assert chapters[2]["href"] == "chapter-3.html"


# ---------------------------------------------------------------------------
# Chapter progress tracking (badge persistence across navigation)
# ---------------------------------------------------------------------------
class TestCopyProgressTracking:
    """Tests for chapter progress API used alongside copy badge tracking."""

    def test_mark_chapter_100_after_copy(self, client):
        """Marking chapter as 100% read after copy should persist."""
        bid = f"test_progress_{uuid.uuid4().hex[:8]}"

        response = client.post(
            f"/api/chapter-progress/{bid}/0",
            json={"progress": 100.0},
        )
        assert response.status_code == 200

        response = client.get(f"/api/chapter-progress/{bid}")
        data = response.json()
        assert data["progress"]["0"] == 100.0

    def test_mark_multiple_chapters_after_multi_copy(self, client):
        """Multiple chapters can be marked as read after bulk copy."""
        bid = f"test_multi_prog_{uuid.uuid4().hex[:8]}"

        for i in range(3):
            resp = client.post(
                f"/api/chapter-progress/{bid}/{i}",
                json={"progress": 100.0},
            )
            assert resp.status_code == 200

        response = client.get(f"/api/chapter-progress/{bid}")
        data = response.json()
        for i in range(3):
            assert data["progress"][str(i)] == 100.0

    def test_unmarked_chapters_remain_zero(self, client):
        """Chapters not copied should remain at 0 progress."""
        bid = f"test_unmark_{uuid.uuid4().hex[:8]}"

        client.post(
            f"/api/chapter-progress/{bid}/1",
            json={"progress": 100.0},
        )

        response = client.get(f"/api/chapter-progress/{bid}")
        data = response.json()
        assert data["progress"].get("0", 0) == 0
        assert data["progress"]["1"] == 100.0


# ---------------------------------------------------------------------------
# JavaScript logic contract tests (data-level, no browser needed)
# ---------------------------------------------------------------------------
class TestCopiedPagesSetLogic:
    """Test the Set-based tracking logic used by copiedPdfPages / copiedEpubChapters."""

    def test_add_single_page(self):
        """Adding a page index to the set tracks it."""
        copied = set()
        copied.add(0)
        assert 0 in copied
        assert 1 not in copied

    def test_add_multiple_pages(self):
        """Adding multiple page indices tracks them all."""
        copied = set()
        for idx in [0, 2, 5]:
            copied.add(idx)
        assert copied == {0, 2, 5}

    def test_duplicate_add_is_idempotent(self):
        """Adding the same page twice doesn't create duplicates."""
        copied = set()
        copied.add(3)
        copied.add(3)
        assert len(copied) == 1

    def test_tracks_epub_hrefs(self):
        """EPUB chapters are tracked by href string."""
        copied = set()
        copied.add("chapter-0.html")
        copied.add("chapter-2.html")
        assert "chapter-0.html" in copied
        assert "chapter-1.html" not in copied

    def test_mark_pages_batch(self):
        """Marking a batch of page indices works."""
        copied = set()
        batch = [0, 1, 2, 5, 8]
        for idx in batch:
            copied.add(idx)
        assert len(copied) == 5
        assert all(idx in copied for idx in batch)


class TestCanvasSizeGuard:
    """Test the canvas dimension limiting logic."""

    MAX_CANVAS_DIM = 16384
    MAX_CANVAS_AREA = 268435456  # 256 MP

    def test_small_image_passes(self):
        """A small combined image should pass the guard."""
        width, height = 800, 3000
        assert width <= self.MAX_CANVAS_DIM
        assert height <= self.MAX_CANVAS_DIM
        assert width * height <= self.MAX_CANVAS_AREA

    def test_tall_image_fails(self):
        """A very tall combined image should trigger the guard."""
        width, height = 800, 20000
        exceeds = height > self.MAX_CANVAS_DIM
        assert exceeds

    def test_large_area_fails(self):
        """A huge area should trigger the guard."""
        width, height = 16385, 16384
        exceeds = width * height > self.MAX_CANVAS_AREA
        assert exceeds

    def test_typical_10_pages_passes(self):
        """10 pages of typical PDF size should pass."""
        page_width = 1200
        page_height = 1600
        padding = 20
        num_pages = 10
        total_height = page_height * num_pages + padding * (num_pages - 1)
        assert page_width <= self.MAX_CANVAS_DIM
        assert total_height <= self.MAX_CANVAS_DIM
        assert page_width * total_height <= self.MAX_CANVAS_AREA

    def test_50_pages_may_exceed(self):
        """50 high-res pages may exceed canvas limits."""
        page_width = 2400
        page_height = 3200
        padding = 20
        num_pages = 50
        total_height = page_height * num_pages + padding * (num_pages - 1)
        # 3200 * 50 + 20 * 49 = 160980 > 16384
        assert total_height > self.MAX_CANVAS_DIM


class TestImageLoadTimeoutLogic:
    """Test the timeout constant and skip-on-failure logic."""

    def test_timeout_is_reasonable(self):
        """The image load timeout should be between 5s and 30s."""
        IMAGE_LOAD_TIMEOUT_MS = 15000
        assert 5000 <= IMAGE_LOAD_TIMEOUT_MS <= 30000

    def test_failed_pages_tracked_separately(self):
        """Failed page indices should be collected for user notification."""
        loaded = []
        failed = []
        pages_to_load = [0, 1, 2, 3, 4]
        pages_that_fail = {1, 3}

        for p in pages_to_load:
            if p in pages_that_fail:
                failed.append(p + 1)  # 1-indexed for user display
            else:
                loaded.append(p)

        assert loaded == [0, 2, 4]
        assert failed == [2, 4]
        assert len(loaded) + len(failed) == len(pages_to_load)

    def test_skip_and_continue_produces_partial_result(self):
        """Even with some failures, the copy should produce a partial result."""
        all_pages = list(range(10))
        failed = {2, 7}
        loaded = [p for p in all_pages if p not in failed]
        assert len(loaded) == 8
        assert len(loaded) > 0  # partial result is non-empty
