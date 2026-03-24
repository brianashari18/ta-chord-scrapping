"""
scrapers/ultimateguitar.py - Scraper for https://www.ultimate-guitar.com
Uses the embedded JSON data payload that UG injects into every page.
"""

import json
import re
from typing import List, Optional
from urllib.parse import urljoin, quote_plus

from scrapers.base import BaseChordScraper
from models import ChordSong, SearchResult
from harmony import analyse_chords


class UltimateGuitarScraper(BaseChordScraper):
    """Scraper for Ultimate Guitar (ultimate-guitar.com)."""

    SOURCE_NAME = "ultimateguitar"
    BASE_URL = "https://www.ultimate-guitar.com"
    SEARCH_URL = "https://www.ultimate-guitar.com/search.php"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    _DATA_RE = re.compile(r'data-content="([^"]+)"', re.DOTALL)

    def _extract_json(self, soup) -> Optional[dict]:
        """Extract the JSON payload that UG embeds as a data-content attribute."""
        tag = soup.find("div", class_="js-store")
        if tag and tag.get("data-content"):
            raw = tag["data-content"]
            # UG HTML-encodes some characters
            raw = raw.replace("&quot;", '"').replace("&amp;", "&").replace("&#34;", '"')
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        params = {
            "search_type": "title",
            "value": query,
        }
        soup = self._get(self.SEARCH_URL, params=params)
        if soup is None:
            return []

        data = self._extract_json(soup)
        results: List[SearchResult] = []

        if data:
            try:
                tabs = data["store"]["page"]["data"]["results"]
            except (KeyError, TypeError):
                tabs = []

            for tab in tabs[:max_results]:
                tab_url = tab.get("tab_url") or tab.get("href", "")
                title = tab.get("song_name") or tab.get("name", "Unknown")
                artist = tab.get("artist_name", "Unknown")
                rating = str(tab.get("rating", ""))
                difficulty = tab.get("difficulty", None)

                if not tab_url:
                    continue

                results.append(
                    SearchResult(
                        title=title,
                        artist=artist,
                        url=tab_url,
                        source=self.SOURCE_NAME,
                        rating=rating,
                        difficulty=difficulty,
                    )
                )
        else:
            # Fallback HTML parsing
            for link in soup.select("a.LQUZJ")[:max_results]:
                url = urljoin(self.BASE_URL, link["href"])
                title = link.get_text(strip=True)
                results.append(
                    SearchResult(
                        title=title, artist="Unknown", url=url, source=self.SOURCE_NAME
                    )
                )

        return results

    # ------------------------------------------------------------------
    # Song detail
    # ------------------------------------------------------------------

    def get_song(self, url: str) -> Optional[ChordSong]:
        soup = self._get(url)
        if soup is None:
            return None

        data = self._extract_json(soup)

        if data:
            try:
                tab = data["store"]["page"]["data"]["tab"]
                tab_view = data["store"]["page"]["data"]["tab_view"]
            except (KeyError, TypeError):
                tab = {}
                tab_view = {}

            title = tab.get("song_name", "Unknown Title")
            artist = tab.get("artist_name", "Unknown Artist")
            key = tab_view.get("meta", {}).get("tonality")
            capo = tab_view.get("meta", {}).get("capo")
            tempo = tab_view.get("meta", {}).get("tempo")
            difficulty = tab.get("difficulty")
            rating = str(tab.get("rating", ""))

            # Chord content is stored under wiki_tab > content or content
            chord_content = tab_view.get("wiki_tab", {}).get("content") or tab_view.get(
                "content", ""
            )
            # Strip UG markup tags like [ch] [/ch] [tab] [/tab]
            chord_content = re.sub(
                r"\[/?(?:ch|tab|verse|chorus|bridge|intro|outro)[^\]]*\]",
                "",
                chord_content,
            )

        else:
            # Minimal HTML fallback
            title_tag = soup.select_one("h1.dxHVR, h1")
            title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
            artist_tag = soup.select_one("h2.ruTMB, .artist a, h2 a")
            artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
            key = capo = tempo = difficulty = rating = None

            pre = soup.select_one("pre, .js-tab-content")
            chord_content = pre.get_text() if pre else ""

        chords_used = self.extract_chords(chord_content)

        # -- Harmonic analysis (auto key detection) -----------------------
        harmony = analyse_chords(chords_used)
        detected_key = harmony["detected_key"]
        key_confidence = harmony["key_confidence"]
        harmonic_map = (
            {
                lbl.chord: {
                    "roman": lbl.roman,
                    "function": lbl.function,
                    "diatonic": lbl.is_diatonic,
                }
                for lbl in harmony["labels"]
            }
            if harmony["labels"]
            else None
        )

        return ChordSong(
            title=title,
            artist=artist,
            url=url,
            source=self.SOURCE_NAME,
            key=str(key) if key else None,
            capo=str(capo) if capo else None,
            tempo=str(tempo) if tempo else None,
            difficulty=difficulty,
            rating=rating,
            chord_content=chord_content,
            chords_used=chords_used,
            detected_key=detected_key,
            key_confidence=key_confidence,
            harmonic_map=harmonic_map,
        )
