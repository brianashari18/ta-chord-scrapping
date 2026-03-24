"""
models.py - Data models for chord scraping results
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ChordSong:
    """Represents a song with its chord information."""

    title: str
    artist: str
    url: str
    source: str  # e.g., 'chordtela', 'ultimateguitar'
    key: Optional[str] = None
    capo: Optional[str] = None
    tempo: Optional[str] = None
    difficulty: Optional[str] = None
    rating: Optional[str] = None
    genre: Optional[str] = None
    chord_content: Optional[str] = None  # raw text of the chord / lyrics
    chords_used: List[str] = field(default_factory=list)  # unique chords found
    # Harmonic analysis (auto-filled by harmony.analyse_chords)
    detected_key: Optional[str] = None  # e.g. "C major", "A minor"
    key_confidence: Optional[float] = None  # 0.0 – 1.0
    harmonic_map: Optional[dict] = None  # {chord: {roman, function, diatonic}}

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "url": self.url,
            "source": self.source,
            "key": self.key,
            "detected_key": self.detected_key,
            "key_confidence": self.key_confidence,
            "capo": self.capo,
            "tempo": self.tempo,
            "difficulty": self.difficulty,
            "rating": self.rating,
            "genre": self.genre,
            "chord_content": self.chord_content,
            "chords_used": ", ".join(self.chords_used),
            "harmonic_map": self.harmonic_map,
        }


@dataclass
class SearchResult:
    """Represents a single item from a search result page."""

    title: str
    artist: str
    url: str
    source: str
    rating: Optional[str] = None
    difficulty: Optional[str] = None
