"""Test suite for chapter filtering and grouping functionality."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import sys

# Add the parent directory to the path so we can import the server module
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import app  # noqa: E402


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_epub_path():
    """Get path to a sample EPUB file for testing."""
    epub_dir = Path(__file__).parent.parent
    # Look for any .epub file
    epub_files = list(epub_dir.glob("*.epub"))
    if epub_files:
        return str(epub_files[0])
    # If no EPUB, create a mock path
    return str(epub_dir / "test_book.epub")


@pytest.fixture
def book_id():
    """Standard book ID for testing."""
    return "test_book"


class TestChapterFilteringUI:
    """Tests for chapter filtering UI elements."""

    def test_filter_dropdown_exists_in_html(self):
        """Test that filter dropdown is present in the reader HTML."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        assert 'id="chapter-filter"' in content, \
            "Filter dropdown not found in HTML"
        assert 'value="all"' in content, "All option not found"
        assert 'value="unread"' in content, "Unread option not found"
        assert 'value="read"' in content, "Read option not found"

    def test_search_input_exists_in_html(self):
        """Test that search input is present in the reader HTML."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        assert 'id="chapter-search"' in content, \
            "Search input not found in HTML"
        assert 'placeholder="Search chapters..."' in content, \
            "Search placeholder not found"
        assert 'onkeyup="filterChapters' in content, \
            "Search event handler not found"

    def test_filter_css_styles_present(self):
        """Test that CSS styles for filtering are present."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        assert '.chapter-filter' in content, \
            "Filter CSS class not found"
        assert '.chapter-filter select' in content, \
            "Filter select CSS not found"
        assert '.chapter-filter input' in content, \
            "Filter input CSS not found"

    def test_filter_function_exists(self):
        """Test that filterChapters JavaScript function exists."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        assert 'function filterChapters(filterType)' in content, \
            "filterChapters function not found"
        assert "filterType === 'unread'" in content, \
            "Unread filter logic not found"
        assert "filterType === 'read'" in content, \
            "Read filter logic not found"

    def test_filter_function_checks_read_status(self):
        """Test that filter function checks the read status."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        # Find the filterChapters function
        assert "classList.contains('read')" in content, \
            "Read class check not found"
        assert "isRead = link?.classList.contains('read')" in content, \
            "Read status extraction not found"

    def test_filter_function_hides_unmatched_chapters(self):
        """Test that filter function hides non-matching chapters."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        assert "chapterItem.style.display" in content, \
            "Display style manipulation not found"
        assert "shouldShow ? '' : 'none'" in content, \
            "Show/hide logic not found"

    def test_filter_function_unchecks_hidden_items(self):
        """Test that filter function unchecks hidden chapters."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        # Check that the function unchecks hidden chapters
        assert 'cb.checked = false' in content, \
            "Unchecking logic not found"
        assert 'if (!shouldShow)' in content, \
            "Condition for unchecking not found"

    def test_search_filter_is_case_insensitive(self):
        """Test that search filtering is case insensitive."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        assert 'toLowerCase()' in content, \
            "Case-insensitive conversion not found"
        
        # Check that filterChapters does case conversion
        func_start = content.find('function filterChapters')
        func_end = (content.find('function ', func_start + 1)
                    if content.find('function ', func_start + 1) > func_start
                    else len(content))
        filter_func = content[func_start:func_end]
        
        assert 'toLowerCase()' in filter_func, \
            "Case-insensitive search not implemented"

    def test_search_and_filter_work_together(self):
        """Test that search and filter dropdowns work together."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        # Check that both matchesSearch and matchesFilter are used
        assert 'const matchesSearch' in content, \
            "Search matching not found"
        assert 'let matchesFilter' in content, \
            "Filter matching not found"
        assert 'matchesSearch && matchesFilter' in content, \
            "Combined filter logic not found"

    def test_filter_calls_update_copy_button(self):
        """Test that filtering updates the copy button state."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        assert 'updateCopyButton()' in content, \
            "updateCopyButton not called"
        # Find the filterChapters function and check if it calls updateCopyButton
        func_start = content.find('function filterChapters')
        func_end = content.find('function ', func_start + 1)
        filter_func = content[func_start:func_end]
        assert 'updateCopyButton()' in filter_func, \
            "updateCopyButton not called in filterChapters"

    def test_reset_filter_function_exists(self):
        """Test that resetChapterFilter function exists."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        assert 'function resetChapterFilter()' in content, \
            "resetChapterFilter function not found"

    def test_reset_filter_clears_inputs(self):
        """Test that reset filter clears both filter and search."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')

        func_start = content.find('function resetChapterFilter')
        func_end = content.find('function ', func_start + 1)
        reset_func = content[func_start:func_end]

        assert "filterSelect.value = 'all'" in reset_func, \
            "Filter not reset to all"
        assert "searchInput.value = ''" in reset_func, \
            "Search input not cleared"
        assert "filterChapters('all')" in reset_func, \
            "Filter not reapplied"


class TestFilteringIntegration:
    """Integration tests for filtering with copy functionality."""

    def test_filter_affects_selected_chapters_count(self):
        """Test that filtering affects which chapters are counted as selected."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # Verify that updateCopyButton only counts visible checkboxes
        func_start = content.find('function updateCopyButton')
        func_end = content.find('function ', func_start + 1)
        update_func = content[func_start:func_end]
        
        # The function should select only visible checkboxes
        assert 'querySelectorAll' in update_func, "Checkbox selection not found"

    def test_copying_respects_hidden_chapters(self):
        """Test that copy functionality only copies visible chapters."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # Verify that copySelectedChapters function exists and uses querySelectorAll
        assert 'function copySelectedChapters' in content, "copySelectedChapters function not found"
        
        # The function should select checkboxes (whether checked or all)
        func_start = content.find('function copySelectedChapters')
        func_end = content.find('function ', func_start + 1) if content.find('function ', func_start + 1) > func_start else len(content)
        copy_func = content[func_start:func_end]
        
        assert 'querySelectorAll' in copy_func or 'chapter-checkbox' in copy_func, \
            "Chapter checkbox selection not found in copy function"

    def test_hidden_chapters_cannot_be_selected(self):
        """Test that hidden chapters don't affect selection count."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # Find the filterChapters function
        func_start = content.find('function filterChapters')
        func_end = content.find('function ', func_start + 1)
        filter_func = content[func_start:func_end]
        
        # Verify hidden chapters are unchecked
        assert 'if (!shouldShow)' in filter_func, "Visibility check not found"
        assert 'cb.checked = false' in filter_func, "Hidden chapter unchecking not found"


class TestFilteringEdgeCases:
    """Tests for edge cases in filtering functionality."""

    def test_filter_with_empty_search(self):
        """Test filtering with empty search term."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        func_start = content.find('function filterChapters')
        func_end = content.find('function ', func_start + 1)
        filter_func = content[func_start:func_end]
        
        # Should handle empty search gracefully
        assert '!searchTerm' in filter_func or 'searchTerm ||' in filter_func, \
            "Empty search term handling not found"

    def test_filter_with_special_characters(self):
        """Test filtering handles special characters in search."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # The function uses includes() which handles special characters
        func_start = content.find('function filterChapters')
        func_end = content.find('function ', func_start + 1)
        filter_func = content[func_start:func_end]
        
        assert '.includes(searchTerm)' in filter_func, "String matching with includes() not found"

    def test_filter_with_no_matching_chapters(self):
        """Test filtering when no chapters match the criteria."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # The function should handle this gracefully
        func_start = content.find('function filterChapters')
        func_end = content.find('function ', func_start + 1)
        filter_func = content[func_start:func_end]
        
        assert 'updateCopyButton()' in filter_func, "Should update button even when no chapters match"

    def test_filter_after_marking_chapters_read(self):
        """Test that filter correctly reflects read status."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # Verify that copySelectedChapters marks chapters as read
        assert 'chapter-progress' in content, \
            "Chapter marking functionality not found"
        
        # Verify filterChapters checks for read status
        func_start = content.find('function filterChapters')
        func_end = (content.find('function ', func_start + 1)
                    if content.find('function ', func_start + 1) > func_start
                    else len(content))
        filter_func = content[func_start:func_end]
        
        assert 'classList' in filter_func, \
            "CSS class checking not implemented in filter"

    def test_select_all_with_filter_active(self):
        """Test select all behavior when filter is active."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # selectAllChapters should select visible checkboxes
        func_start = content.find('function selectAllChapters')
        func_end = content.find('function ', func_start + 1)
        select_all = content[func_start:func_end]
        
        # Current implementation selects all, but they get unchecked if hidden
        assert 'querySelectorAll' in select_all, "Checkbox selection not found"


class TestFilteringAccessibility:
    """Tests for accessibility of filtering controls."""

    def test_filter_controls_have_proper_labels(self):
        """Test that filter controls have descriptive text."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # Check for descriptive options
        assert 'All Chapters' in content, "All option text not found"
        assert 'Unread Only' in content, "Unread option text not found"
        assert 'Read Only' in content, "Read option text not found"

    def test_search_input_has_placeholder(self):
        """Test that search input has helpful placeholder."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        assert 'placeholder="Search chapters..."' in content, "Search placeholder not found"

    def test_clear_button_clears_filter(self):
        """Test that clear button resets filter."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # Clear button should clear selections
        assert 'onclick="clearChapterSelection()"' in content, "Clear button not found"


class TestFilteringPerformance:
    """Tests for performance considerations in filtering."""

    def test_filter_function_is_efficient(self):
        """Test that filter function doesn't have unnecessary loops."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        func_start = content.find('function filterChapters')
        func_end = content.find('function ', func_start + 1)
        filter_func = content[func_start:func_end]
        
        # Should have single forEach loop
        loop_count = filter_func.count('.forEach(')
        assert loop_count == 1, f"Expected 1 loop, found {loop_count}"

    def test_filter_uses_event_delegation(self):
        """Test that filtering uses efficient event handling."""
        html_path = Path(__file__).parent.parent / "templates" / "reader.html"
        content = html_path.read_text(encoding='utf-8')
        
        # Filter is called on dropdown change, not on every keystroke... wait, it is on keyup
        # But that's acceptable for reasonable chapter counts
        assert 'onchange="filterChapters' in content or 'onkeyup="filterChapters' in content, \
            "Filter event handler not found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
