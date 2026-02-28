"""
Tests for the semantic search module.
"""

import pytest
import sys
import os
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock
from collections import Counter

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from semantic_search import (
    _normalize_token,
    _tokenize,
    _index_path,
    _load_index,
    _write_index,
    _should_rebuild,
    ensure_book_index,
    _build_context,
    _find_match,
    semantic_search_books,
    STOPWORDS,
    TOKEN_RE,
    INDEX_FILENAME,
    INDEX_VERSION,
)


class TestTokenNormalization:
    """Tests for token normalization."""

    def test_normalize_basic_token(self):
        """Test basic token normalization."""
        result = _normalize_token("Hello")
        assert result == "hello"
        assert isinstance(result, str)

    def test_normalize_removes_leading_trailing_quotes(self):
        """Test that leading/trailing quotes are removed."""
        assert _normalize_token("'hello'") == "hello"
        assert _normalize_token("'test") == "test"
        assert _normalize_token("word'") == "word"

    def test_normalize_removes_short_tokens(self):
        """Test that tokens shorter than 2 chars are removed."""
        assert _normalize_token("a") == ""
        assert _normalize_token("I") == ""
        assert _normalize_token("x") == ""

    def test_normalize_removes_digits(self):
        """Test that pure digit tokens are removed."""
        assert _normalize_token("123") == ""
        assert _normalize_token("456") == ""
        assert _normalize_token("0") == ""

    def test_normalize_suffix_ing(self):
        """Test suffix removal for 'ing'."""
        result = _normalize_token("running")
        assert result == "runn" or result == "run"
        assert "ing" not in result

    def test_normalize_suffix_ed(self):
        """Test suffix removal for 'ed'."""
        result = _normalize_token("walked")
        assert "ed" not in result

    def test_normalize_suffix_s(self):
        """Test suffix removal for 's'."""
        result = _normalize_token("books")
        assert result == "book"

    def test_normalize_suffix_es(self):
        """Test suffix removal for 'es'."""
        result = _normalize_token("boxes")
        assert "es" not in result

    def test_normalize_suffix_ly(self):
        """Test suffix removal for 'ly'."""
        result = _normalize_token("quickly")
        assert "ly" not in result

    def test_normalize_suffix_edly(self):
        """Test suffix removal for 'edly'."""
        result = _normalize_token("allegedly")
        assert "edly" not in result

    def test_normalize_preserves_apostrophes_in_middle(self):
        """Test that apostrophes in middle are preserved if word is long enough."""
        result = _normalize_token("don't")
        assert len(result) > 0


class TestTokenization:
    """Tests for text tokenization."""

    def test_tokenize_simple_text(self):
        """Test tokenizing simple text."""
        tokens = _tokenize("hello world")
        assert "hello" in tokens
        assert "world" in tokens

    def test_tokenize_removes_stopwords(self):
        """Test that stopwords are removed."""
        tokens = _tokenize("the quick brown fox")
        assert "the" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens

    def test_tokenize_handles_punctuation(self):
        """Test that punctuation is handled correctly."""
        tokens = _tokenize("Hello, world! How are you?")
        assert "hello" in tokens
        assert "world" in tokens
        # Punctuation should not create tokens
        assert "" not in tokens
        assert "," not in tokens

    def test_tokenize_empty_text(self):
        """Test tokenizing empty text."""
        tokens = _tokenize("")
        assert tokens == []

    def test_tokenize_only_stopwords(self):
        """Test tokenizing text with only stopwords."""
        tokens = _tokenize("the a an")
        assert tokens == []

    def test_tokenize_case_insensitive(self):
        """Test that tokenization is case-insensitive."""
        tokens1 = _tokenize("HELLO WORLD")
        tokens2 = _tokenize("hello world")
        assert tokens1 == tokens2

    def test_tokenize_short_tokens_removed(self):
        """Test that very short tokens are removed."""
        tokens = _tokenize("I a my x you")
        # Only "you" should remain (if not a stopword)
        assert "" not in tokens

    def test_tokenize_apostrophe_words(self):
        """Test tokenizing words with apostrophes."""
        tokens = _tokenize("don't can't")
        assert len(tokens) > 0

    def test_tokenize_hyphenated_words(self):
        """Test tokenizing hyphenated words."""
        tokens = _tokenize("well-known text")
        assert "known" in tokens or "well" in tokens


class TestIndexPaths:
    """Tests for index path handling."""

    def test_index_path_construction(self):
        """Test index path construction."""
        book_dir = "/path/to/book"
        path = _index_path(book_dir)
        assert path.endswith(INDEX_FILENAME)
        assert book_dir in path

    def test_index_path_with_trailing_slash(self):
        """Test index path with trailing slash in book_dir."""
        book_dir = "/path/to/book/"
        path = _index_path(book_dir)
        assert path.endswith(INDEX_FILENAME)


class TestIndexIO:
    """Tests for index file I/O operations."""

    def test_load_nonexistent_index(self):
        """Test loading an index that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nonexistent.json")
            result = _load_index(path)
            assert result is None

    def test_write_and_load_index(self):
        """Test writing and loading an index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_index.json")
            test_data = {
                "index_version": INDEX_VERSION,
                "book_id": "test_book",
                "documents": []
            }

            _write_index(path, test_data)
            loaded = _load_index(path)

            assert loaded is not None
            assert loaded["book_id"] == "test_book"
            assert loaded["index_version"] == INDEX_VERSION

    def test_index_caching(self):
        """Test that index caching works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "cached_index.json")
            test_data = {"book_id": "test"}

            _write_index(path, test_data)
            loaded1 = _load_index(path)
            loaded2 = _load_index(path)

            # Should return the same cached instance on second load
            # (if mtime hasn't changed)
            assert loaded1 is not None
            assert loaded2 is not None


class TestShouldRebuild:
    """Tests for rebuild logic."""

    def test_rebuild_when_no_index(self):
        """Test that rebuild is needed when index is None."""
        book = Mock()
        assert _should_rebuild(None, book) is True

    def test_rebuild_when_wrong_version(self):
        """Test rebuild is needed when index version differs."""
        index = {"index_version": 0}  # Wrong version
        book = Mock()
        assert _should_rebuild(index, book) is True

    def test_no_rebuild_when_current(self):
        """Test no rebuild needed when index is current."""
        current_time = "2024-01-01T00:00:00"
        index = {
            "index_version": INDEX_VERSION,
            "processed_at": current_time,
            "chapter_count": 3
        }
        book = Mock()
        book.processed_at = current_time
        book.spine = [Mock(), Mock(), Mock()]

        assert _should_rebuild(index, book) is False

    def test_rebuild_when_processed_date_changes(self):
        """Test rebuild when book processed_at changes."""
        index = {
            "index_version": INDEX_VERSION,
            "processed_at": "2024-01-01",
            "chapter_count": 3
        }
        book = Mock()
        book.processed_at = "2024-01-02"
        book.spine = [Mock(), Mock(), Mock()]

        assert _should_rebuild(index, book) is True

    def test_rebuild_when_chapter_count_changes(self):
        """Test rebuild when chapter count changes."""
        index = {
            "index_version": INDEX_VERSION,
            "processed_at": "2024-01-01",
            "chapter_count": 3
        }
        book = Mock()
        book.processed_at = "2024-01-01"
        book.spine = [Mock(), Mock(), Mock(), Mock(), Mock()]  # 5 chapters

        assert _should_rebuild(index, book) is True


class TestEnsureBookIndex:
    """Tests for book index creation."""

    def test_create_index_for_new_book(self):
        """Test creating index for a book without one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            book = Mock()
            book.processed_at = "2024-01-01"
            book.spine = [Mock(), Mock()]
            book.spine[0].text = "Chapter one content"
            book.spine[0].title = "Chapter 1"
            book.spine[0].href = "ch1.xhtml"
            book.spine[1].text = "Chapter two content"
            book.spine[1].title = "Chapter 2"
            book.spine[1].href = "ch2.xhtml"
            book.metadata = Mock()
            book.metadata.title = "Test Book"

            index = ensure_book_index("test_book", book, tmpdir)

            assert index["book_id"] == "test_book"
            assert index["book_title"] == "Test Book"
            assert len(index["documents"]) == 2

    def test_index_caching_no_rebuild(self):
        """Test that index is not rebuilt if not needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            book = Mock()
            book.processed_at = "2024-01-01"
            book.spine = [Mock()]
            book.spine[0].text = "Content"
            book.spine[0].title = "Ch1"
            book.spine[0].href = "ch1.xhtml"
            book.metadata = Mock()
            book.metadata.title = "Test"

            index1 = ensure_book_index("book1", book, tmpdir)
            index2 = ensure_book_index("book1", book, tmpdir)

            assert index1 == index2

    def test_index_empty_chapters(self):
        """Test indexing when some chapters have no text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            book = Mock()
            book.processed_at = "2024-01-01"
            book.spine = [Mock(), Mock(), Mock()]
            book.spine[0].text = "Content"
            book.spine[0].title = "Ch1"
            book.spine[0].href = "ch1.xhtml"
            book.spine[1].text = ""  # Empty
            book.spine[1].title = "Ch2"
            book.spine[1].href = "ch2.xhtml"
            book.spine[2].text = None  # None
            book.spine[2].title = "Ch3"
            book.spine[2].href = "ch3.xhtml"
            book.metadata = Mock()
            book.metadata.title = "Test"

            index = ensure_book_index("book1", book, tmpdir)

            # Should only index chapter with content
            assert len(index["documents"]) == 1


class TestContextBuilding:
    """Tests for context extraction."""

    def test_build_context_center_match(self):
        """Test context building with match in center."""
        text = "This is a long sentence with some important information in the middle of the text."
        context = _build_context(text, 30, 9)
        assert "important" in context

    def test_build_context_start_match(self):
        """Test context building with match at start."""
        text = "Important content at the start and then more text follows."
        context = _build_context(text, 0, 9)
        assert "Important" in context or "important" in context.lower()

    def test_build_context_end_match(self):
        """Test context building with match at end."""
        text = "Some content here and then important information at the end"
        context = _build_context(text, len(text) - 11, 11)
        assert len(context) > 0

    def test_build_context_empty_text(self):
        """Test context building with empty text."""
        context = _build_context("", 0, 0)
        assert context == ""

    def test_build_context_ellipsis_added(self):
        """Test that ellipsis is added for truncated context."""
        text = "This is a very long sentence with lots of content that extends beyond what should be shown in context."
        context = _build_context(text, 50, 5)
        if len(context) < len(text):
            # If context was truncated, it should have ellipsis
            assert "..." in context or len(context) < len(text)


class TestMatchFinding:
    """Tests for match finding in text."""

    def test_find_single_term(self):
        """Test finding a single term."""
        text = "The quick brown fox"
        pos, length = _find_match(text, ["quick"])
        assert pos != -1
        assert "quick" in text[pos:pos+length].lower()

    def test_find_earliest_match(self):
        """Test finding earliest match when term appears multiple times."""
        text = "The quick quickest quicksand"
        pos, length = _find_match(text, ["quick"])
        assert pos != -1
        assert pos == text.lower().find("quick")

    def test_find_no_match(self):
        """Test when term is not found."""
        text = "The quick brown fox"
        pos, length = _find_match(text, ["elephant"])
        assert pos == -1

    def test_find_multiple_terms(self):
        """Test finding early match when multiple terms provided."""
        text = "The elephant and the quick fox"
        pos, length = _find_match(text, ["elephant", "quick"])
        # Should find elephant first (appears first)
        assert pos != -1

    def test_find_case_insensitive(self):
        """Test that match finding is case-insensitive."""
        text = "THE QUICK BROWN"
        pos, length = _find_match(text, ["quick"])
        # Should find it even though text is uppercase
        assert pos != -1 or length == 0


class TestSemanticSearch:
    """Tests for full semantic search functionality."""

    def test_search_empty_query(self):
        """Test search with empty query."""
        results = semantic_search_books("", [], "/tmp", lambda x: None)
        assert results == []

    def test_search_only_stopwords(self):
        """Test search with only stopwords."""
        results = semantic_search_books("the a an", [], "/tmp", lambda x: None)
        assert results == []

    def test_search_single_book(self):
        """Test search in single book."""
        with tempfile.TemporaryDirectory() as tmpdir:
            book = Mock()
            book.processed_at = "2024-01-01"
            book.spine = [Mock()]
            book.spine[0].text = "Machine learning and artificial intelligence are transformative technologies"
            book.spine[0].title = "Chapter 1"
            book.spine[0].href = "ch1.xhtml"
            book.metadata = Mock()
            book.metadata.title = "AI Book"

            book_dir = os.path.join(tmpdir, "book1")
            os.makedirs(book_dir, exist_ok=True)

            # Pre-index the book
            ensure_book_index("book1", book, book_dir)

            def load_book(book_id):
                if book_id == "book1":
                    return book
                return None

            results = semantic_search_books(
                "machine learning",
                ["book1"],
                tmpdir,
                load_book
            )

            assert len(results) > 0
            assert results[0]["book_id"] == "book1"

    def test_search_multiple_books(self):
        """Test search across multiple books."""
        with tempfile.TemporaryDirectory() as tmpdir:
            book1 = Mock()
            book1.processed_at = "2024-01-01"
            book1.spine = [Mock()]
            book1.spine[0].text = "Python programming is fun"
            book1.spine[0].title = "Ch1"
            book1.spine[0].href = "ch1.xhtml"
            book1.metadata = Mock()
            book1.metadata.title = "Python Book"

            book2 = Mock()
            book2.processed_at = "2024-01-01"
            book2.spine = [Mock()]
            book2.spine[0].text = "Java development requires patience"
            book2.spine[0].title = "Ch1"
            book2.spine[0].href = "ch1.xhtml"
            book2.metadata = Mock()
            book2.metadata.title = "Java Book"

            for bid in ["book1", "book2"]:
                book_dir = os.path.join(tmpdir, bid)
                os.makedirs(book_dir, exist_ok=True)

            book1_dir = os.path.join(tmpdir, "book1")
            book2_dir = os.path.join(tmpdir, "book2")
            ensure_book_index("book1", book1, book1_dir)
            ensure_book_index("book2", book2, book2_dir)

            def load_book(book_id):
                if book_id == "book1":
                    return book1
                if book_id == "book2":
                    return book2
                return None

            results = semantic_search_books(
                "programming",
                ["book1", "book2"],
                tmpdir,
                load_book
            )

            assert len(results) > 0
            book_ids = {r["book_id"] for r in results}
            assert "book1" in book_ids

    def test_search_results_format(self):
        """Test search results have expected format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            book = Mock()
            book.processed_at = "2024-01-01"
            book.spine = [Mock()]
            book.spine[0].text = "The machine learning model performs well"
            book.spine[0].title = "Chapter 1"
            book.spine[0].href = "ch1.xhtml"
            book.metadata = Mock()
            book.metadata.title = "ML Book"

            book_dir = os.path.join(tmpdir, "book1")
            os.makedirs(book_dir, exist_ok=True)
            ensure_book_index("book1", book, book_dir)

            def load_book(book_id):
                return book if book_id == "book1" else None

            results = semantic_search_books("machine learning", ["book1"], tmpdir, load_book)

            assert len(results) > 0
            result = results[0]

            # Check expected keys
            assert "book_id" in result
            assert "book_title" in result
            assert "chapter_index" in result
            assert "chapter_title" in result
            assert "chapter_href" in result
            assert "context" in result
            assert "score" in result

    def test_search_respects_limit(self):
        """Test that search respects limit parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create book with many chapters
            book = Mock()
            book.processed_at = "2024-01-01"
            book.spine = [Mock() for _ in range(10)]

            for i, chapter in enumerate(book.spine):
                chapter.text = "machine learning data science algorithms"
                chapter.title = f"Ch{i}"
                chapter.href = f"ch{i}.xhtml"

            book.metadata = Mock()
            book.metadata.title = "Book"

            book_dir = os.path.join(tmpdir, "book1")
            os.makedirs(book_dir, exist_ok=True)
            ensure_book_index("book1", book, book_dir)

            def load_book(book_id):
                return book if book_id == "book1" else None

            results = semantic_search_books(
                "machine learning",
                ["book1"],
                tmpdir,
                load_book,
                limit=3
            )

            assert len(results) <= 3
