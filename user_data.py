"""
User data management for Reader3.
Handles reading progress, bookmarks, highlights, and search history.
"""

import json
import os
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
class UserData:
    """All user data for Reader3."""
    highlights: Dict[str, List[Highlight]] = field(default_factory=dict)  # book_id -> highlights
    bookmarks: Dict[str, List[Bookmark]] = field(default_factory=dict)  # book_id -> bookmarks
    progress: Dict[str, ReadingProgress] = field(default_factory=dict)  # book_id -> progress
    search_history: List[SearchQuery] = field(default_factory=list)
    version: str = "1.0"


def generate_id() -> str:
    """Generate a unique ID."""
    return hashlib.md5(
        f"{datetime.now().isoformat()}-{os.urandom(8).hex()}".encode()
    ).hexdigest()[:12]


class UserDataManager:
    """Manages user data persistence."""
    
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.data_file = os.path.join(data_dir, "user_data.json")
        self._data: Optional[UserData] = None
    
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
                search_history=[
                    SearchQuery(**q) for q in raw.get('search_history', [])
                ],
                version=raw.get('version', '1.0')
            )
        except Exception as e:
            print(f"Error loading user data: {e}")
            self._data = UserData()
        
        return self._data
    
    def save(self):
        """Save user data to disk."""
        if self._data is None:
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
            'search_history': [asdict(q) for q in self._data.search_history],
            'version': self._data.version
        }
        
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
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
        """Save reading progress for a book."""
        data = self.load()
        data.progress[progress.book_id] = progress
        self.save()
    
    def get_progress(self, book_id: str) -> Optional[ReadingProgress]:
        """Get reading progress for a book."""
        data = self.load()
        return data.progress.get(book_id)
    
    def update_reading_time(self, book_id: str, seconds: int):
        """Add to the reading time for a book."""
        data = self.load()
        if book_id in data.progress:
            data.progress[book_id].reading_time_seconds += seconds
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
        
        if changed:
            self.save()
