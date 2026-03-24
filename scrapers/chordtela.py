"""
scrapers/chordtela.py - Scraper for https://www.chordtela.com

Arsitektur:
  - Chordtela berbasis WordPress.
  - Halaman search (chord-kunci-gitar-dasar-hasil-pencarian) merender hasil
    via JavaScript — tidak ada post URL di HTML statis.
  - Strategi search:
      1. Parse query → pisahkan kemungkinan nama artis / judul.
      2. Cari artis di halaman indeks artis (/chord-gitar-a-b, dst.).
      3. Buka halaman artis (/chord/ARTIST-SLUG) → ambil semua post URL.
      4. Filter post berdasarkan kecocokan judul (fuzzy substring).
  - get_song() langsung scrape halaman chord dengan selector yang benar.
"""

import json
import re
import unicodedata
from typing import List, Optional, Tuple
from scrapers.base import BaseChordScraper, CHORD_PATTERN
from models import ChordSong, SearchResult
from harmony import analyse_chords

# Pola URL artikel Chordtela: domain/YYYY/MM/slug.html
_POST_URL_RE = re.compile(
    r"https?://(?:www\.)?chordtela\.com/\d{4}/\d{2}/[\w\-]+\.html"
)

# Peta huruf pertama → slug halaman indeks artis
_INDEX_PAGE: dict = {
    "a": "chord-gitar-a-b",
    "b": "chord-gitar-a-b",
    "c": "chord-gitar-c-d",
    "d": "chord-gitar-c-d",
    "e": "chord-gitar-e-f",
    "f": "chord-gitar-e-f",
    "g": "chord-gitar-g-h",
    "h": "chord-gitar-g-h",
    "i": "chord-gitar-i-j",
    "j": "chord-gitar-i-j",
    "k": "chord-gitar-k-l",
    "l": "chord-gitar-k-l",
    "m": "chord-gitar-m-n",
    "n": "chord-gitar-m-n",
    "o": "chord-gitar-o-p",
    "p": "chord-gitar-o-p",
    "q": "chord-gitar-q-r",
    "r": "chord-gitar-q-r",
    "s": "chord-gitar-s-t",
    "t": "chord-gitar-s-t",
    "u": "chord-gitar-u-v",
    "v": "chord-gitar-u-v",
    "w": "chord-gitar-w-x",
    "x": "chord-gitar-w-x",
    "y": "chord-gitar-y-z",
    "z": "chord-gitar-y-z",
}


def _normalize(text: str) -> str:
    """Lowercase, strip accents, keep only alphanum + spaces."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", " ", ascii_str.lower()).strip()


class ChordtelaScraper(BaseChordScraper):
    """Scraper for Chordtela (chordtela.com)."""

    SOURCE_NAME = "chordtela"
    BASE_URL = "https://www.chordtela.com"

    def __init__(self, delay: float = 1.5):
        super().__init__(delay=delay)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_artist_slugs(self, first_letter: str) -> List[Tuple[str, str]]:
        """
        Ambil semua (artist_name, artist_slug) dari halaman indeks artis
        sesuai huruf pertama.
        Kembalikan list of (display_name, slug_url).
        """
        letter = first_letter.lower()
        page_slug = _INDEX_PAGE.get(letter, f"chord-gitar-{letter}")
        url = f"{self.BASE_URL}/{page_slug}"
        soup = self._get(url)
        if soup is None:
            return []

        results: List[Tuple[str, str]] = []
        # Artist links: <a href="/chord/SLUG"><span class="name">NAME</span></a>
        for a in soup.select("a[href*='/chord/']"):
            href = a.get("href", "")
            # Pastikan bukan link navigasi seperti /chord/lagu-pop-indonesia
            if not re.search(r"/chord/[a-z0-9\-]+$", href):
                continue
            name_tag = a.select_one("span.name")
            name = name_tag.get_text(strip=True) if name_tag else a.get_text(strip=True)
            if name:
                results.append((name, href))
        return results

    def _get_artist_songs(self, artist_url: str) -> List[Tuple[str, str]]:
        """
        Ambil semua (song_display_title, song_url) dari halaman artis.
        Hanya ambil link dari area konten utama (div.main-wrapper),
        abaikan sidebar yang berisi lagu populer/terbaru dari artis lain.
        """
        soup = self._get(artist_url)
        if soup is None:
            return []

        # Batasi pencarian ke main-wrapper agar tidak ambil link sidebar
        container = soup.select_one("div.main-wrapper") or soup

        songs: List[Tuple[str, str]] = []
        for a in container.select("a[href]"):
            href = a.get("href", "")
            if _POST_URL_RE.match(href):
                text = a.get_text(strip=True)
                if text:
                    songs.append((text, href))
        # Hapus duplikat (sama href)
        seen: set = set()
        unique: List[Tuple[str, str]] = []
        for t, u in songs:
            if u not in seen:
                seen.add(u)
                unique.append((t, u))
        return unique

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        Cari lagu Chordtela.

        Strategi:
        1. Cari artis dari token pertama query di halaman indeks artis.
        2. Buka halaman artis, ambil semua lagu.
        3. Filter berdasarkan substring query (case-insensitive).
        4. Jika tidak ada artist match, fallback: coba semua huruf dari query.
        """
        norm_query = _normalize(query)
        results: List[SearchResult] = []

        # Ambil kata-kata dari query untuk mencari artis
        tokens = norm_query.split()
        if not tokens:
            return []

        # Token bermakna untuk artist matching (abaikan token 1 huruf seperti
        # "d" dari "D'Masiv" agar tidak match setiap artis yang mengandung "d")
        meaningful_tokens = [t for t in tokens if len(t) >= 2]

        # Gabungan semua token tanpa spasi — berguna untuk nama artis yg ditulis
        # menyatu di Chordtela (e.g. "dmasiv" untuk "D'Masiv")
        joined_query = "".join(tokens)

        # Coba cari artis berdasarkan huruf pertama query (bukan tiap token)
        # Ini menghindari fetch halaman indeks ganda (mis. D & M untuk "D'Masiv")
        first_letter = tokens[0][0]

        matched_artists: List[Tuple[str, str]] = []  # (name, url)

        slugs = self._get_artist_slugs(first_letter)
        for artist_name, artist_url in slugs:
            norm_artist = _normalize(artist_name)
            artist_joined = norm_artist.replace(" ", "")

            # --- Slug match: bandingkan joined_query dengan slug URL ---
            # e.g. joined_query = "dmasiv", slug = "/chord/dmasiv"
            slug_part = artist_url.rstrip("/").rsplit("/", 1)[-1]
            slug_match = (
                joined_query == slug_part
                or slug_part.startswith(joined_query)
                or joined_query.startswith(slug_part)
            )

            # --- Joined match: bandingkan tanpa spasi ---
            joined_match = (
                joined_query == artist_joined
                or artist_joined.startswith(joined_query)
                or joined_query.startswith(artist_joined)
            )

            # --- Token match: semua meaningful tokens harus ada sebagai kata
            # utuh di nama artis (bukan substring, agar "noah" tidak match
            # "menoah") ---
            artist_words = set(norm_artist.split())
            token_match = meaningful_tokens and all(
                tok in artist_words for tok in meaningful_tokens
            )

            if slug_match or joined_match or token_match:
                matched_artists.append((artist_name, artist_url))

        # Fallback: jika tidak ada artis yang cocok, jangan load semua —
        # hanya lanjut ke tahap lagu dengan daftar kosong (hasil = kosong)
        # Ini mencegah hang karena iterasi seluruh halaman indeks.
        if not matched_artists:
            # Coba cari di huruf pertama token terpanjang sebagai upaya terakhir
            longest = max(tokens, key=len)
            if longest[0] != first_letter:
                slugs = self._get_artist_slugs(longest[0])
                joined_query_alt = longest
                for artist_name, artist_url in slugs:
                    norm_artist = _normalize(artist_name)
                    if joined_query_alt in norm_artist.replace(" ", ""):
                        matched_artists.append((artist_name, artist_url))

        for artist_name, artist_url in matched_artists:
            songs = self._get_artist_songs(artist_url)
            for song_title, song_url in songs:
                norm_title = _normalize(song_title)
                # Filter: semua token query harus muncul sebagai kata utuh
                # di gabungan artis+judul (bukan substring)
                combined = _normalize(artist_name) + " " + norm_title
                combined_words = set(combined.split())
                if all(tok in combined_words for tok in tokens):
                    # Parse "Title - Artist" atau "Artist - Title"
                    m = re.match(r"^(.+?)\s*[-–]\s*(.+)$", song_title)
                    if m:
                        part1, part2 = m.group(1).strip(), m.group(2).strip()
                        # Tentukan mana artis mana judul berdasarkan nama artis
                        norm_artist = _normalize(artist_name)
                        if _normalize(
                            part2
                        ) in norm_artist or norm_artist in _normalize(part2):
                            title, artist = part1, part2
                        else:
                            title, artist = part2, part1
                    else:
                        title, artist = song_title, artist_name

                    if song_url not in [r.url for r in results]:
                        results.append(
                            SearchResult(
                                title=title,
                                artist=artist,
                                url=song_url,
                                source=self.SOURCE_NAME,
                            )
                        )
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

        return results

    # ------------------------------------------------------------------
    # Song detail
    # ------------------------------------------------------------------

    def get_song(self, url: str) -> Optional[ChordSong]:
        """Scrape a Chordtela song page."""
        soup = self._get(url)
        if soup is None:
            return None

        # -- Title --------------------------------------------------------
        title_tag = soup.select_one(
            "h1.post-title a, h1.entry-title a, h1.post-title, h1.entry-title, h1"
        )
        raw_title = title_tag.get_text(strip=True) if title_tag else ""
        # Strip prefix "Kunci Gitar " and suffix " Chord Dasar ©ChordTela.com"
        raw_title = re.sub(r"^Kunci\s+Gitar\s+", "", raw_title, flags=re.I).strip()
        raw_title = re.sub(r"\s+Chord\s+Dasar.*$", "", raw_title, flags=re.I).strip()

        # -- Artist via JSON-LD (paling akurat) ----------------------------
        artist = None
        song_name_ld = None
        for sc in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(sc.string or "")
                if isinstance(data, list):
                    data = next(
                        (d for d in data if d.get("@type") == "MusicRecording"), None
                    )
                if data and data.get("@type") == "MusicRecording":
                    artist = data.get("byArtist", {}).get("name")
                    song_name_ld = data.get("name")  # e.g. "Vierra - Seandainya"
                    break
            except (json.JSONDecodeError, AttributeError):
                pass

        # Fallback: dari div.chord-artis-title
        if not artist:
            artis_tag = soup.select_one("div.chord-artis-title ul.chord-artis li a")
            if artis_tag:
                artist = re.sub(
                    r"^Chord\s+", "", artis_tag.get_text(strip=True), flags=re.I
                ).strip()

        artist = artist or "Unknown Artist"

        # Tentukan title dari JSON-LD jika ada, hapus bagian artis
        if song_name_ld:
            # Format JSON-LD: "Artist - Song" atau "Song"
            m = re.match(r"^(.+?)\s*[-–]\s*(.+)$", song_name_ld)
            if m:
                norm_artist = _normalize(artist)
                if _normalize(m.group(1)) in norm_artist or norm_artist in _normalize(
                    m.group(1)
                ):
                    title = m.group(2).strip()
                else:
                    title = m.group(1).strip()
            else:
                title = song_name_ld.strip()
        elif raw_title:
            # Coba hapus nama artis dari judul
            m = re.match(r"^(.+?)\s*[-–]\s*(.+)$", raw_title)
            if m:
                norm_artist = _normalize(artist)
                if _normalize(m.group(1)) in norm_artist or norm_artist in _normalize(
                    m.group(1)
                ):
                    title = m.group(2).strip()
                else:
                    title = raw_title
            else:
                title = raw_title
        else:
            title = "Unknown Title"

        # -- Metadata (key, capo, tempo) ----------------------------------
        key = capo = tempo = None
        # Metadata biasanya ada di div/table di area .chord-info, .kunci-info, dll.
        for item in soup.select(
            ".kunci-info li, .chord-info li, .info-lagu li, table.chord-info tr"
        ):
            text = item.get_text(separator=" ", strip=True).lower()
            val_tag = item.select_one("span, b, strong, td:last-child")
            val = val_tag.get_text(strip=True) if val_tag else ""
            if ("kunci" in text or "key" in text) and not key:
                key = val or None
            elif "capo" in text and not capo:
                capo = val or None
            elif ("tempo" in text or "bpm" in text) and not tempo:
                tempo = val or None

        # -- Chord content from div.telabox --------------------------------
        telabox = soup.select_one("div.telabox")
        chord_content = ""
        if telabox:
            # Hapus semua script/style dari telabox sebelum parsing
            for tag in telabox.find_all(["script", "style"]):
                tag.decompose()
            chord_content = self._parse_telabox(telabox)

            chord_content = re.sub(
                r"(?mi)^[\[\(=\-\s]*ORIGINAL\s+(?:CHORD\s+)?DARI\s+[^\n]*$",
                "",
                chord_content,
            ).strip()

            # Chordtela sering menambahkan bagian "ORIGINAL CHORD" (versi
            # tanpa capo) di bawah versi capo.  Marker bervariasi:
            #   [[[ORIGINAL CHORD]]]  /  ===ORIGINAL CHORD===
            #   ||===ORIGINAL CHORD===||  /  ===ORIGINAL CHORD))
            #
            # Strategi: jika original chord tersedia dan cukup lengkap
            # (≥ 50 % occurrence chord dari versi capo), pakai original
            # karena itu nada aslinya — lebih akurat untuk analisis harmoni.
            # Jika tidak ada atau terlalu pendek, pakai versi capo saja.
            _ORIG_MARKER = re.compile(
                r"^[|=\[\]\-\+\s]*ORIGINAL\s*CHORD[|=\[\]\)\s]*$",
                re.IGNORECASE | re.MULTILINE,
            )
            parts = _ORIG_MARKER.split(chord_content, maxsplit=1)
            if len(parts) == 2:
                capo_part = parts[0].rstrip()
                orig_part = parts[1].strip()
                # Hitung kemunculan chord di masing-masing bagian untuk
                # menentukan apakah original chord cukup lengkap.
                capo_n = len(CHORD_PATTERN.findall(capo_part))
                orig_n = len(CHORD_PATTERN.findall(orig_part))
                if orig_n >= capo_n * 0.5 and orig_n > 0:
                    # Original lengkap → pakai, set capo = None
                    chord_content = orig_part
                    capo = None
                else:
                    # Original terlalu pendek → buang, pakai versi capo
                    chord_content = capo_part

            # Strip blok "Catatan:" / "Catatan;" yang kadang muncul di
            # awal/akhir konten (penjelasan capo, penyederhanaan chord, dsb).
            # Blok dimulai dari baris "Catatan" dan berlanjut sampai
            # paragraf berikutnya (baris kosong + baris non-kosong) atau EOF.
            chord_content = re.sub(
                r"(?mi)^[ \t]*catatan[;:\.]?.*?(?=\n[ \t]*\n(?=\S)|\Z)",
                "",
                chord_content,
                flags=re.DOTALL,
            ).strip()
            # Buang baris separator yang tersisa (hanya tanda -)
            chord_content = re.sub(
                r"^[ \t]*-{4,}[ \t]*$", "", chord_content, flags=re.MULTILINE
            ).strip()

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
            key=key,
            capo=capo,
            tempo=tempo,
            chord_content=chord_content,
            chords_used=chords_used,
            detected_key=detected_key,
            key_confidence=key_confidence,
            harmonic_map=harmonic_map,
        )

    # ------------------------------------------------------------------
    # Telabox parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_telabox(telabox) -> str:
        """
        Konversi isi div.telabox ke teks chord+lirik biasa.

        Struktur telabox:
          - <a class="tbi-tooltip" href="#">Am<span class="custom tbi-Am"></span></a>
            → chord name = teks node langsung di <a> (bukan teks <span>)
          - <br> → newline
          - Teks biasa → lirik
        Hasil: string multi-baris, chord dan lirik sesuai posisi.
        """

        # Rekursif iterasi children
        # (chord anchor di-decompose span-nya agar hanya teks chord yang diambil)
        def process(element) -> str:
            from bs4 import NavigableString, Tag

            result = []
            for child in element.children:
                if isinstance(child, NavigableString):
                    result.append(str(child))
                elif isinstance(child, Tag):
                    if child.name == "br":
                        result.append("\n")
                    elif child.name in ("script", "style"):
                        # Abaikan script/style anti-scraping yang mungkin
                        # disuntikkan ke dalam konten chord
                        pass
                    elif "tbi-tooltip" in child.get("class", []):
                        # Ambil teks langsung (bukan dari span di dalamnya)
                        chord_text = "".join(
                            str(c)
                            for c in child.children
                            if hasattr(c, "string")
                            and c.name is None  # NavigableString
                            or (hasattr(c, "name") and c.name is None)
                        )
                        # Lebih sederhana: get_text tapi strip isi span
                        for span in child.find_all("span"):
                            span.decompose()
                        chord_text = child.get_text()
                        result.append(chord_text)
                    else:
                        result.append(process(child))
            return "".join(result)

        text = process(telabox)
        # Bersihkan: ganti \xa0 (non-breaking space) dengan space biasa
        text = text.replace("\xa0", " ")
        # Normalisasi multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
