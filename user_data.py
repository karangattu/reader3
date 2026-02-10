"""
User data management for Reader3.
Handles reading progress, bookmarks, highlights, and search history.
Writes are debounced: changes are batched and flushed to disk after a
configurable delay (default 2 s) or when the process shuts down.
"""

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional
import hashlib


@dataclass
class Highlight:
    """A text highlight with optional note."""
    id: str
    book_id: str
    chapter_index: int
    text: str
    color: str  # yellow, green, blue, pink, purple
    note: Optional[str] = None
    start_offset: int = 0
    end_offset: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Bookmark:
    """A bookmark with optional note."""
    id: str
    book_id: str
    chapter_index: int
    scroll_position: float  # 0.0 to 1.0 (percentage)
    title: str  # Auto-generated or user-provided
    note: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ReadingProgress:
    """Reading progress for a book."""
    book_id: str
    chapter_index: int
    scroll_position: float  # 0.0 to 1.0 (percentage)
    last_read: str = field(default_factory=lambda: datetime.now().isoformat())
    total_chapters: int = 0
    reading_time_seconds: int = 0  # Total time spent reading


@dataclass
class SearchQuery:
    """A search query entry for history."""
    query: str
    book_id: Optional[str]  # None if global search
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    results_count: int = 0


@dataclass
class ReadingSession:
    """A reading session for tracking reading history."""
    id: str
    book_id: str
    book_title: str
    chapter_index: int
    chapter_title: str
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    duration_seconds: int = 0
    pages_read: int = 0
    scroll_position: float = 0.0


@dataclass
class VocabularyWord:
    """A saved word from dictionary lookups."""
    id: str
    book_id: str
    word: str
    definition: str
    phonetic: Optional[str] = None
    part_of_speech: Optional[str] = None
    example: Optional[str] = None
    chapter_index: int = 0
    context: str = ""  # Sentence where word was found
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reviewed_count: int = 0


@dataclass
class Annotation:
    """A text annotation/note attached to a highlight or bookmark."""
    id: str
    book_id: str
    chapter_index: int
    note_text: str
    highlight_id: Optional[str] = None  # Link to a highlight
    bookmark_id: Optional[str] = None  # Link to a bookmark
    position_offset: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = field(default_factory=list)


@dataclass
class Collection:
    """A collection/shelf to organize books."""
    id: str
    name: str
    description: str = ""
    icon: str = "folder"  # Font Awesome icon name (folder, book, star, heart, etc.)
    color: str = "#3498db"  # Hex color for the collection
    book_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_smart: bool = False  # For future: smart collections based on rules
    sort_order: int = 0  # For custom ordering of collections


@dataclass
class UserData:
    """All user data for Reader3."""
    highlights: Dict[str, List[Highlight]] = field(default_factory=dict)
    bookmarks: Dict[str, List[Bookmark]] = field(default_factory=dict)
    progress: Dict[str, ReadingProgress] = field(default_factory=dict)
    chapter_progress: Dict[str, Dict[int, float]] = field(default_factory=dict)
    search_history: List[SearchQuery] = field(default_factory=list)
    reading_sessions: List[ReadingSession] = field(default_factory=list)
    vocabulary: Dict[str, List[VocabularyWord]] = field(default_factory=dict)
    annotations: Dict[str, List[Annotation]] = field(default_factory=dict)
    collections: List[Collection] = field(default_factory=list)
    version: str = "1.2"


def generate_id() -> str:
    """Generate a unique ID."""
    return hashlib.md5(
        f"{datetime.now().isoformat()}-{os.urandom(8).hex()}".encode()
    ).hexdigest()[:12]


class UserDataManager:
    """Manages user data persistence with debounced writes."""
    
    DEBOUNCE_SECONDS = 2.0  # Flush after 2 seconds of inactivity

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.data_file = os.path.join(data_dir, "user_data.json")
        self._data: Optional[UserData] = None
        self._dirty = False
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
    
    def _ensure_dir(self):
        """Ensure data directory exists."""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
    
    def load(self) -> UserData:
        """Load user data from disk."""
        if self._data is not None:
            return self._data
        
        self._ensure_dir()
        
        if not os.path.exists(self.data_file):
            self._data = UserData()
            return self._data
        
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            
            # Reconstruct the UserData object
            self._data = UserData(
                highlights={
                    book_id: [Highlight(**h) for h in highlights]
                    for book_id, highlights in raw.get('highlights', {}).items()
                },
                bookmarks={
                    book_id: [Bookmark(**b) for b in bookmarks]
                    for book_id, bookmarks in raw.get('bookmarks', {}).items()
                },
                progress={
                    book_id: ReadingProgress(**p)
                    for book_id, p in raw.get('progress', {}).items()
                },
                chapter_progress={
                    book_id: {int(k): v for k, v in chapters.items()}
                    for book_id, chapters in raw.get('chapter_progress', {}).items()
                },
                search_history=[
                    SearchQuery(**q) for q in raw.get('search_history', [])
                ],
                reading_sessions=[
                    ReadingSession(**s) for s in raw.get('reading_sessions', [])
                ],
                vocabulary={
                    book_id: [VocabularyWord(**w) for w in words]
                    for book_id, words in raw.get('vocabulary', {}).items()
                },
                annotations={
                    book_id: [Annotation(**a) for a in annots]
                    for book_id, annots in raw.get('annotations', {}).items()
                },
                collections=[
                    Collection(**c) for c in raw.get('collections', [])
                ],
                version=raw.get('version', '1.2')
            )
        except Exception as e:
            print(f"Error loading user data: {e}")
            self._data = UserData()
        
        return self._data
    
    def save(self):
        """Persist data to disk immediately (atomic write)."""
        self._dirty = True
        self._do_flush()

    def save_deferred(self):
        """Mark data as dirty and schedule a debounced write.

        Use this for high-frequency updates (e.g. scroll-position saves)
        where batching is preferred over per-call I/O.
        """
        self._dirty = True
        self._schedule_flush()

    def _schedule_flush(self):
        """Reset the debounce timer. The actual write happens after DEBOUNCE_SECONDS of inactivity."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.DEBOUNCE_SECONDS, self._do_flush)
            self._timer.daemon = True
            self._timer.start()

    def flush(self):
        """Immediately write pending changes to disk (called on shutdown)."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._do_flush()

    def _do_flush(self):
        """Actually persist data to disk."""
        if not self._dirty or self._data is None:
            return
        
        self._ensure_dir()
        
        # Convert to serializable format
        data = {
            'highlights': {
                book_id: [asdict(h) for h in highlights]
                for book_id, highlights in self._data.highlights.items()
            },
            'bookmarks': {
                book_id: [asdict(b) for b in bookmarks]
                for book_id, bookmarks in self._data.bookmarks.items()
            },
            'progress': {
                book_id: asdict(p)
                for book_id, p in self._data.progress.items()
            },
            'chapter_progress': self._data.chapter_progress,
            'search_history': [asdict(q) for q in self._data.search_history],
            'reading_sessions': [asdict(s) for s in self._data.reading_sessions],
            'vocabulary': {
                book_id: [asdict(w) for w in words]
                for book_id, words in self._data.vocabulary.items()
            },
            'annotations': {
                book_id: [asdict(a) for a in annots]
                for book_id, annots in self._data.annotations.items()
            },
            'collections': [asdict(c) for c in self._data.collections],
            'version': self._data.version
        }
        
        try:
            # Atomic write via temp-file + rename
            tmp_path = self.data_file + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.data_file)
            self._dirty = False
        except Exception as e:
            print(f"Error saving user data: {e}")
    
    # Highlights
    def add_highlight(self, highlight: Highlight) -> Highlight:
        """Add a highlight."""
        data = self.load()
        if highlight.book_id not in data.highlights:
            data.highlights[highlight.book_id] = []
        data.highlights[highlight.book_id].append(highlight)
        self.save()
        return highlight
    
    def get_highlights(self, book_id: str, chapter_index: Optional[int] = None) -> List[Highlight]:
        """Get highlights for a book, optionally filtered by chapter."""
        data = self.load()
        highlights = data.highlights.get(book_id, [])
        if chapter_index is not None:
            highlights = [h for h in highlights if h.chapter_index == chapter_index]
        return highlights
    
    def delete_highlight(self, book_id: str, highlight_id: str) -> bool:
        """Delete a highlight."""
        data = self.load()
        if book_id not in data.highlights:
            return False
        
        original_len = len(data.highlights[book_id])
        data.highlights[book_id] = [
            h for h in data.highlights[book_id] if h.id != highlight_id
        ]
        
        if len(data.highlights[book_id]) < original_len:
            self.save()
            return True
        return False
    
    def update_highlight_note(self, book_id: str, highlight_id: str, note: str) -> bool:
        """Update a highlight's note."""
        data = self.load()
        if book_id not in data.highlights:
            return False
        
        for h in data.highlights[book_id]:
            if h.id == highlight_id:
                h.note = note
                self.save()
                return True
        return False
    
    def update_highlight_color(self, book_id: str, highlight_id: str, color: str) -> bool:
        """Update a highlight's color."""
        valid_colors = ['yellow', 'green', 'blue', 'pink', 'purple']
        if color not in valid_colors:
            return False
        
        data = self.load()
        if book_id not in data.highlights:
            return False
        
        for h in data.highlights[book_id]:
            if h.id == highlight_id:
                h.color = color
                self.save()
                return True
        return False
    
    # Bookmarks
    def add_bookmark(self, bookmark: Bookmark) -> Bookmark:
        """Add a bookmark."""
        data = self.load()
        if bookmark.book_id not in data.bookmarks:
            data.bookmarks[bookmark.book_id] = []
        data.bookmarks[bookmark.book_id].append(bookmark)
        self.save()
        return bookmark
    
    def get_bookmarks(self, book_id: str) -> List[Bookmark]:
        """Get bookmarks for a book."""
        data = self.load()
        return data.bookmarks.get(book_id, [])
    
    def delete_bookmark(self, book_id: str, bookmark_id: str) -> bool:
        """Delete a bookmark."""
        data = self.load()
        if book_id not in data.bookmarks:
            return False
        
        original_len = len(data.bookmarks[book_id])
        data.bookmarks[book_id] = [
            b for b in data.bookmarks[book_id] if b.id != bookmark_id
        ]
        
        if len(data.bookmarks[book_id]) < original_len:
            self.save()
            return True
        return False
    
    def update_bookmark_note(self, book_id: str, bookmark_id: str, note: str) -> bool:
        """Update a bookmark's note."""
        data = self.load()
        if book_id not in data.bookmarks:
            return False
        
        for b in data.bookmarks[book_id]:
            if b.id == bookmark_id:
                b.note = note
                self.save()
                return True
        return False
    
    # Reading Progress
    def save_progress(self, progress: ReadingProgress):
        """Save reading progress for a book (deferred write)."""
        data = self.load()
        data.progress[progress.book_id] = progress
        self.save_deferred()
    
    def get_progress(self, book_id: str) -> Optional[ReadingProgress]:
        """Get reading progress for a book."""
        data = self.load()
        return data.progress.get(book_id)
    
    def update_reading_time(self, book_id: str, seconds: int):
        """Add to the reading time for a book (deferred write)."""
        data = self.load()
        if book_id in data.progress:
            data.progress[book_id].reading_time_seconds += seconds
            self.save_deferred()
    
    # Chapter Progress (per-chapter tracking)
    def get_chapter_progress(self, book_id: str) -> Dict[int, float]:
        """Get reading progress for each chapter in a book."""
        data = self.load()
        return data.chapter_progress.get(book_id, {})
    
    def save_chapter_progress(self, book_id: str, chapter_index: int,
                              progress_percent: float):
        """Save reading progress for a specific chapter."""
        data = self.load()
        if book_id not in data.chapter_progress:
            data.chapter_progress[book_id] = {}
        # Only update if new progress is higher (don't lose progress)
        current = data.chapter_progress[book_id].get(chapter_index, 0)
        if progress_percent > current:
            data.chapter_progress[book_id][chapter_index] = min(100, progress_percent)
            self.save()
    
    # Search History
    def add_search(self, query: SearchQuery):
        """Add a search query to history."""
        data = self.load()
        # Keep only last 50 searches
        data.search_history.insert(0, query)
        data.search_history = data.search_history[:50]
        self.save()
    
    def get_search_history(self, limit: int = 20) -> List[SearchQuery]:
        """Get recent search history."""
        data = self.load()
        return data.search_history[:limit]
    
    def clear_search_history(self):
        """Clear search history."""
        data = self.load()
        data.search_history = []
        self.save()
    
    # Export
    def export_book_data(self, book_id: str, format: str = 'json') -> str:
        """Export highlights and bookmarks for a book."""
        data = self.load()
        
        export_data = {
            'book_id': book_id,
            'exported_at': datetime.now().isoformat(),
            'highlights': [asdict(h) for h in data.highlights.get(book_id, [])],
            'bookmarks': [asdict(b) for b in data.bookmarks.get(book_id, [])],
        }
        
        if format == 'markdown':
            return self._to_markdown(export_data)
        else:
            return json.dumps(export_data, indent=2, ensure_ascii=False)
    
    def _to_markdown(self, data: dict) -> str:
        """Convert export data to Markdown format."""
        lines = [
            f"# Notes and Highlights",
            f"",
            f"**Book ID:** {data['book_id']}",
            f"**Exported:** {data['exported_at']}",
            f"",
        ]
        
        if data['bookmarks']:
            lines.append("## Bookmarks")
            lines.append("")
            for b in data['bookmarks']:
                lines.append(f"### {b['title']}")
                lines.append(f"*Chapter {b['chapter_index'] + 1}, {b['created_at']}*")
                if b.get('note'):
                    lines.append(f"")
                    lines.append(f"> {b['note']}")
                lines.append("")
        
        if data['highlights']:
            lines.append("## Highlights")
            lines.append("")
            for h in data['highlights']:
                color_emoji = {
                    'yellow': '🟡',
                    'green': '🟢',
                    'blue': '🔵',
                    'pink': '🔴',
                    'purple': '🟣'
                }.get(h['color'], '⚪')
                
                lines.append(f"{color_emoji} **Chapter {h['chapter_index'] + 1}**")
                lines.append(f"")
                lines.append(f"> {h['text']}")
                if h.get('note'):
                    lines.append(f"")
                    lines.append(f"*Note: {h['note']}*")
                lines.append("")
        
        return "\n".join(lines)
    
    def export_all_data(self, format: str = 'json') -> str:
        """Export all user data."""
        data = self.load()
        
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'highlights': {
                book_id: [asdict(h) for h in highlights]
                for book_id, highlights in data.highlights.items()
            },
            'bookmarks': {
                book_id: [asdict(b) for b in bookmarks]
                for book_id, bookmarks in data.bookmarks.items()
            },
            'progress': {
                book_id: asdict(p)
                for book_id, p in data.progress.items()
            },
            'vocabulary': {
                book_id: [asdict(w) for w in words]
                for book_id, words in data.vocabulary.items()
            },
            'annotations': {
                book_id: [asdict(a) for a in annots]
                for book_id, annots in data.annotations.items()
            },
        }
        
        return json.dumps(export_data, indent=2, ensure_ascii=False)
    
    # Cleanup
    def cleanup_book_data(self, book_id: str):
        """Remove all data for a deleted book."""
        data = self.load()
        
        changed = False
        if book_id in data.highlights:
            del data.highlights[book_id]
            changed = True
        if book_id in data.bookmarks:
            del data.bookmarks[book_id]
            changed = True
        if book_id in data.progress:
            del data.progress[book_id]
            changed = True
        if book_id in data.chapter_progress:
            del data.chapter_progress[book_id]
            changed = True
        if book_id in data.vocabulary:
            del data.vocabulary[book_id]
            changed = True
        if book_id in data.annotations:
            del data.annotations[book_id]
            changed = True
        
        # Remove reading sessions for this book
        original_sessions = len(data.reading_sessions)
        data.reading_sessions = [
            s for s in data.reading_sessions if s.book_id != book_id
        ]
        if len(data.reading_sessions) < original_sessions:
            changed = True
        
        if changed:
            self.save()

    # ========== Reading Sessions ==========
    
    def start_reading_session(self, session: ReadingSession) -> ReadingSession:
        """Start a new reading session."""
        data = self.load()
        data.reading_sessions.insert(0, session)
        # Keep only last 100 sessions
        data.reading_sessions = data.reading_sessions[:100]
        self.save()
        return session
    
    def end_reading_session(self, session_id: str, 
                            duration_seconds: int,
                            pages_read: int,
                            scroll_position: float) -> bool:
        """End a reading session with final statistics."""
        data = self.load()
        for session in data.reading_sessions:
            if session.id == session_id:
                session.end_time = datetime.now().isoformat()
                session.duration_seconds = duration_seconds
                session.pages_read = pages_read
                session.scroll_position = scroll_position
                self.save()
                return True
        return False
    
    def get_reading_sessions(self, book_id: str = None, 
                             limit: int = 20) -> List[ReadingSession]:
        """Get reading sessions, optionally filtered by book."""
        data = self.load()
        sessions = data.reading_sessions
        if book_id:
            sessions = [s for s in sessions if s.book_id == book_id]
        return sessions[:limit]
    
    def get_reading_stats(self, book_id: str = None) -> dict:
        """Get reading statistics."""
        data = self.load()
        sessions = data.reading_sessions
        if book_id:
            sessions = [s for s in sessions if s.book_id == book_id]
        
        total_time = sum(s.duration_seconds for s in sessions)
        total_pages = sum(s.pages_read for s in sessions)
        session_count = len(sessions)
        
        # Calculate streak (consecutive days)
        streak = 0
        if sessions:
            from datetime import timedelta
            today = datetime.now().date()
            dates_read = set()
            for s in sessions:
                try:
                    date = datetime.fromisoformat(s.start_time).date()
                    dates_read.add(date)
                except Exception:
                    pass
            
            current_date = today
            while current_date in dates_read:
                streak += 1
                current_date -= timedelta(days=1)
        
        return {
            'total_time_seconds': total_time,
            'total_pages': total_pages,
            'session_count': session_count,
            'streak_days': streak,
            'avg_session_minutes': round(total_time / 60 / session_count, 1) 
                                   if session_count > 0 else 0
        }

    # ========== Vocabulary ==========
    
    def add_vocabulary_word(self, word: VocabularyWord) -> VocabularyWord:
        """Add a word to vocabulary."""
        data = self.load()
        if word.book_id not in data.vocabulary:
            data.vocabulary[word.book_id] = []
        
        # Check if word already exists for this book
        existing = [w for w in data.vocabulary[word.book_id] 
                    if w.word.lower() == word.word.lower()]
        if existing:
            # Update existing word
            existing[0].reviewed_count += 1
            self.save()
            return existing[0]
        
        data.vocabulary[word.book_id].append(word)
        self.save()
        return word
    
    def get_vocabulary(self, book_id: str = None) -> List[VocabularyWord]:
        """Get vocabulary words, optionally filtered by book."""
        data = self.load()
        if book_id:
            return data.vocabulary.get(book_id, [])
        # Return all words across all books
        all_words = []
        for words in data.vocabulary.values():
            all_words.extend(words)
        return sorted(all_words, key=lambda w: w.created_at, reverse=True)
    
    def delete_vocabulary_word(self, book_id: str, word_id: str) -> bool:
        """Delete a vocabulary word."""
        data = self.load()
        if book_id not in data.vocabulary:
            return False
        
        original_len = len(data.vocabulary[book_id])
        data.vocabulary[book_id] = [
            w for w in data.vocabulary[book_id] if w.id != word_id
        ]
        
        if len(data.vocabulary[book_id]) < original_len:
            self.save()
            return True
        return False
    
    def search_vocabulary(self, query: str) -> List[VocabularyWord]:
        """Search vocabulary by word or definition."""
        data = self.load()
        query_lower = query.lower()
        results = []
        for words in data.vocabulary.values():
            for w in words:
                if (query_lower in w.word.lower() or 
                    query_lower in w.definition.lower()):
                    results.append(w)
        return results

    # ========== Annotations ==========
    
    def add_annotation(self, annotation: Annotation) -> Annotation:
        """Add an annotation."""
        data = self.load()
        if annotation.book_id not in data.annotations:
            data.annotations[annotation.book_id] = []
        data.annotations[annotation.book_id].append(annotation)
        self.save()
        return annotation
    
    def get_annotations(self, book_id: str, 
                        chapter_index: int = None) -> List[Annotation]:
        """Get annotations for a book, optionally filtered by chapter."""
        data = self.load()
        annotations = data.annotations.get(book_id, [])
        if chapter_index is not None:
            annotations = [a for a in annotations 
                           if a.chapter_index == chapter_index]
        return annotations
    
    def update_annotation(self, book_id: str, annotation_id: str,
                          note_text: str, tags: List[str] = None) -> bool:
        """Update an annotation."""
        data = self.load()
        if book_id not in data.annotations:
            return False
        
        for a in data.annotations[book_id]:
            if a.id == annotation_id:
                a.note_text = note_text
                a.updated_at = datetime.now().isoformat()
                if tags is not None:
                    a.tags = tags
                self.save()
                return True
        return False
    
    def delete_annotation(self, book_id: str, annotation_id: str) -> bool:
        """Delete an annotation."""
        data = self.load()
        if book_id not in data.annotations:
            return False
        
        original_len = len(data.annotations[book_id])
        data.annotations[book_id] = [
            a for a in data.annotations[book_id] if a.id != annotation_id
        ]
        
        if len(data.annotations[book_id]) < original_len:
            self.save()
            return True
        return False
    
    def search_annotations(self, book_id: str, query: str) -> List[Annotation]:
        """Search annotations by text or tags."""
        data = self.load()
        annotations = data.annotations.get(book_id, [])
        query_lower = query.lower()
        
        return [
            a for a in annotations 
            if query_lower in a.note_text.lower() or 
               any(query_lower in tag.lower() for tag in a.tags)
        ]
    
    def export_annotations_markdown(self, book_id: str) -> str:
        """Export annotations to Markdown format."""
        data = self.load()
        annotations = data.annotations.get(book_id, [])
        highlights = data.highlights.get(book_id, [])
        
        lines = [
            f"# Annotations and Notes",
            f"",
            f"**Book ID:** {book_id}",
            f"**Exported:** {datetime.now().isoformat()}",
            f"",
        ]
        
        # Group by chapter
        by_chapter = {}
        for a in annotations:
            if a.chapter_index not in by_chapter:
                by_chapter[a.chapter_index] = {'annotations': [], 'highlights': []}
            by_chapter[a.chapter_index]['annotations'].append(a)
        
        for h in highlights:
            if h.chapter_index not in by_chapter:
                by_chapter[h.chapter_index] = {'annotations': [], 'highlights': []}
            by_chapter[h.chapter_index]['highlights'].append(h)
        
        for chapter_idx in sorted(by_chapter.keys()):
            chapter_data = by_chapter[chapter_idx]
            lines.append(f"## Chapter {chapter_idx + 1}")
            lines.append("")
            
            # Highlights with notes
            for h in chapter_data['highlights']:
                color_emoji = {
                    'yellow': '🟡', 'green': '🟢', 'blue': '🔵',
                    'pink': '🔴', 'purple': '🟣'
                }.get(h.color, '⚪')
                lines.append(f"{color_emoji} **Highlight:**")
                lines.append(f"> {h.text}")
                if h.note:
                    lines.append(f"")
                    lines.append(f"*Note: {h.note}*")
                lines.append("")
            
            # Standalone annotations
            for a in chapter_data['annotations']:
                tags_str = ' '.join(f'`#{t}`' for t in a.tags) if a.tags else ''
                lines.append(f"📝 **Note** {tags_str}")
                lines.append(f"")
                lines.append(f"{a.note_text}")
                lines.append(f"")
                lines.append(f"*Created: {a.created_at}*")
                lines.append("")
        
        return "\n".join(lines)

    # ========== Collections ==========
    
    def create_collection(self, name: str, description: str = "",
                          icon: str = "folder", color: str = "#3498db") -> Collection:
        """Create a new collection."""
        data = self.load()
        
        # Generate unique ID
        collection_id = generate_id()
        
        # Determine sort order (add to end)
        max_order = max((c.sort_order for c in data.collections), default=-1)
        
        collection = Collection(
            id=collection_id,
            name=name,
            description=description,
            icon=icon,
            color=color,
            book_ids=[],
            sort_order=max_order + 1
        )
        
        data.collections.append(collection)
        self.save()
        return collection
    
    def get_collections(self) -> List[Collection]:
        """Get all collections, sorted by sort_order."""
        data = self.load()
        return sorted(data.collections, key=lambda c: c.sort_order)
    
    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get a single collection by ID."""
        data = self.load()
        for c in data.collections:
            if c.id == collection_id:
                return c
        return None
    
    def update_collection(self, collection_id: str, name: str = None,
                          description: str = None, icon: str = None,
                          color: str = None) -> bool:
        """Update a collection's properties."""
        data = self.load()
        for c in data.collections:
            if c.id == collection_id:
                if name is not None:
                    c.name = name
                if description is not None:
                    c.description = description
                if icon is not None:
                    c.icon = icon
                if color is not None:
                    c.color = color
                c.updated_at = datetime.now().isoformat()
                self.save()
                return True
        return False
    
    def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection (books are not deleted, just removed from collection)."""
        data = self.load()
        original_len = len(data.collections)
        data.collections = [c for c in data.collections if c.id != collection_id]
        
        if len(data.collections) < original_len:
            self.save()
            return True
        return False
    
    def add_book_to_collection(self, collection_id: str, book_id: str) -> bool:
        """Add a book to a collection."""
        data = self.load()
        for c in data.collections:
            if c.id == collection_id:
                if book_id not in c.book_ids:
                    c.book_ids.append(book_id)
                    c.updated_at = datetime.now().isoformat()
                    self.save()
                return True
        return False
    
    def remove_book_from_collection(self, collection_id: str, book_id: str) -> bool:
        """Remove a book from a collection."""
        data = self.load()
        for c in data.collections:
            if c.id == collection_id:
                if book_id in c.book_ids:
                    c.book_ids.remove(book_id)
                    c.updated_at = datetime.now().isoformat()
                    self.save()
                return True
        return False
    
    def get_book_collections(self, book_id: str) -> List[Collection]:
        """Get all collections that contain a specific book."""
        data = self.load()
        return [c for c in data.collections if book_id in c.book_ids]
    
    def set_book_collections(self, book_id: str, collection_ids: List[str]) -> bool:
        """Set which collections a book belongs to (replaces existing)."""
        data = self.load()
        changed = False
        
        for c in data.collections:
            should_have_book = c.id in collection_ids
            has_book = book_id in c.book_ids
            
            if should_have_book and not has_book:
                c.book_ids.append(book_id)
                c.updated_at = datetime.now().isoformat()
                changed = True
            elif not should_have_book and has_book:
                c.book_ids.remove(book_id)
                c.updated_at = datetime.now().isoformat()
                changed = True
        
        if changed:
            self.save()
        return True
    
    def reorder_collections(self, collection_ids: List[str]) -> bool:
        """Reorder collections based on the provided list of IDs."""
        data = self.load()
        
        # Create a mapping of id to new order
        order_map = {cid: idx for idx, cid in enumerate(collection_ids)}
        
        for c in data.collections:
            if c.id in order_map:
                c.sort_order = order_map[c.id]
        
        self.save()
        return True
    
    def get_books_in_collection(self, collection_id: str) -> List[str]:
        """Get all book IDs in a collection."""
        data = self.load()
        for c in data.collections:
            if c.id == collection_id:
                return c.book_ids.copy()
        return []
    
    def cleanup_collection_books(self, book_id: str):
        """Remove a deleted book from all collections."""
        data = self.load()
        changed = False
        
        for c in data.collections:
            if book_id in c.book_ids:
                c.book_ids.remove(book_id)
                c.updated_at = datetime.now().isoformat()
                changed = True
        
        if changed:
            self.save()
