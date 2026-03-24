"""
exporter.py - Save scraped ChordSong objects to CSV / JSON
"""

import csv
import json
from pathlib import Path
from typing import List

from models import ChordSong


class Exporter:
    """Handles exporting a list of ChordSong objects."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def to_csv(self, songs: List[ChordSong], filename: str = "chords.csv") -> Path:
        """Export to CSV. Returns the path of the written file."""
        path = self.output_dir / filename
        if not songs:
            print("No songs to export.")
            return path

        fieldnames = list(songs[0].to_dict().keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for song in songs:
                writer.writerow(song.to_dict())

        print(f"[Exporter] Saved {len(songs)} song(s) to {path}")
        return path

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self, songs: List[ChordSong], filename: str = "chords.json") -> Path:
        """Export to JSON. Returns the path of the written file."""
        path = self.output_dir / filename
        data = [song.to_dict() for song in songs]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[Exporter] Saved {len(songs)} song(s) to {path}")
        return path

    # ------------------------------------------------------------------
    # Text (human-readable chord sheet)
    # ------------------------------------------------------------------

    def to_text(self, song: ChordSong, filename: str | None = None) -> Path:
        """Export a single song as a plain-text chord sheet."""
        safe_title = "".join(
            c if c.isalnum() or c in " _-" else "_" for c in song.title
        )
        filename = filename or f"{safe_title}.txt"
        path = self.output_dir / filename

        lines = [
            f"Title   : {song.title}",
            f"Artist  : {song.artist}",
            f"Source  : {song.source}",
            f"URL     : {song.url}",
        ]
        if song.key:
            lines.append(f"Key     : {song.key}")
        if song.capo:
            lines.append(f"Capo    : {song.capo}")
        if song.tempo:
            lines.append(f"Tempo   : {song.tempo}")
        if song.difficulty:
            lines.append(f"Difficulty: {song.difficulty}")
        if song.chords_used:
            lines.append(f"Chords  : {', '.join(song.chords_used)}")
        if song.detected_key:
            conf = f" ({song.key_confidence:.0%})" if song.key_confidence else ""
            lines.append(f"Detected Key: {song.detected_key}{conf}")
        if song.harmonic_map:
            parts = [f"{c}={v['roman']}" for c, v in song.harmonic_map.items()]
            lines.append(f"Harmonic: {', '.join(parts)}")
        lines.append("")
        lines.append("-" * 60)
        lines.append(song.chord_content or "(no content)")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[Exporter] Saved chord sheet to {path}")
        return path
