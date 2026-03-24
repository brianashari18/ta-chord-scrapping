"""
scrapers/base.py - Abstract base class for all chord scrapers
"""

import re
import time
import random
from abc import ABC, abstractmethod
from typing import List, Optional

import requests

try:
    import cloudscraper

    _CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    _CLOUDSCRAPER_AVAILABLE = False
from bs4 import BeautifulSoup

from models import ChordSong, SearchResult

# Common user agents to rotate (Chrome/Firefox terbaru)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # detik

# Regex pattern to detect chord tokens (e.g. Am, G, C#m7, Bm/F#, Bbm, E/G#)
# Catatan: \b tidak bekerja benar setelah # karena # bukan word char,
# jadi kita gunakan lookbehind/lookahead sebagai word boundary.
CHORD_PATTERN = re.compile(
    r"(?<![A-Za-z#b])"
    r"([A-G][#b]?"
    r"(?:maj|min|m|M|aug|dim|sus[24]?|add|dom)?[0-9]?"
    r"(?:/[A-G][#b]?)?)"
    r"(?![A-Za-z#b])"
)


class BaseChordScraper(ABC):
    """Base class that all site-specific scrapers must extend."""

    SOURCE_NAME: str = "base"
    BASE_URL: str = ""

    def __init__(self, delay: float = 1.5):
        self.delay = delay  # seconds to wait between requests
        # Gunakan cloudscraper jika tersedia (bypass Cloudflare)
        if _CLOUDSCRAPER_AVAILABLE:
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
        else:
            self.session = requests.Session()
        # Set adapter-level defaults agar session terlihat seperti browser
        self.session.headers.update(self._base_headers())

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _base_headers(self) -> dict:
        """Header dasar yang selalu dipakai oleh session.

        CATATAN: Jangan override Accept-Encoding karena cloudscraper
        mengelola encoding sendiri.  Menambahkan 'br' (brotli) bisa
        menyebabkan respons tidak ter-decompress dengan benar.
        """
        ua = random.choice(USER_AGENTS)
        return {
            "User-Agent": ua,
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

    def _headers(self) -> dict:
        """Header per-request (bisa di-override subclass).

        Default: kosong. Jangan override User-Agent per-request karena
        cloudscraper perlu konsistensi UA untuk mempertahankan session
        Cloudflare.
        """
        return {}

    def _warm_up(self, base_url: str) -> None:
        """Kunjungi halaman utama dulu agar session dapat cookie yang valid."""
        try:
            self.session.get(base_url, timeout=10)
            time.sleep(random.uniform(0.8, 1.5))
        except requests.RequestException:
            pass

    def _get(
        self, url: str, retries: int = MAX_RETRIES, **kwargs
    ) -> Optional[BeautifulSoup]:
        """GET dengan retry + exponential backoff. Kembalikan BeautifulSoup atau None."""
        for attempt in range(1, retries + 1):
            try:
                response = self.session.get(
                    url,
                    headers=self._headers(),
                    timeout=15,
                    allow_redirects=True,
                    **kwargs,
                )
                if response.status_code == 403:
                    print(
                        f"[{self.SOURCE_NAME}] 403 Forbidden (attempt {attempt}/{retries}) — {url}"
                    )
                    if attempt < retries:
                        # Ganti User-Agent dan tunggu sebelum retry
                        self.session.headers.update(self._base_headers())
                        time.sleep(RETRY_BACKOFF * attempt + random.uniform(1, 3))
                        continue
                    return None
                response.raise_for_status()
                time.sleep(self.delay + random.uniform(0, 0.5))
                return BeautifulSoup(response.text, "lxml")
            except requests.RequestException as exc:
                print(
                    f"[{self.SOURCE_NAME}] Request failed (attempt {attempt}/{retries}) for {url}: {exc}"
                )
                if attempt < retries:
                    time.sleep(RETRY_BACKOFF * attempt)
        return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """Search for songs and return a list of SearchResult objects."""

    @abstractmethod
    def get_song(self, url: str) -> Optional[ChordSong]:
        """Scrape a single song page and return a ChordSong object."""

    def search_and_fetch(self, query: str, max_results: int = 5) -> List[ChordSong]:
        """Convenience method: search then fetch each result's detail page."""
        results = self.search(query, max_results)
        songs: List[ChordSong] = []
        for item in results:
            song = self.get_song(item.url)
            if song:
                songs.append(song)
        return songs

    # ------------------------------------------------------------------
    # Chord extraction helper
    # ------------------------------------------------------------------

    @staticmethod
    def extract_chords(text: str) -> List[str]:
        """Return unique chord tokens found in *text* (order-preserving).

        Preprocessing sebelum regex:
        1. Ganti strip/dash `-` → spasi (pisahkan chord dempet: Am-G → Am G)
        2. Hapus kurung `()` (chord opsional: (Em) → Em)
        """
        # Preprocessing: pisahkan chord dempet & buang kurung
        cleaned = text.replace("-", " ")
        cleaned = cleaned.replace("(", " ").replace(")", " ")

        seen = set()
        chords = []
        for match in CHORD_PATTERN.finditer(cleaned):
            chord = match.group(1)
            if chord not in seen:
                seen.add(chord)
                chords.append(chord)
        return chords
