"""
harmony.py - Key detection & harmonic function analysis

Fitur:
  - detect_key(chords)      → tebak key dari daftar chord
  - chord_harmonic(chord, key) → Roman numeral + fungsi (T/SD/D)
  - analyse_chords(chords)  → return dict dengan key, confidence & harmonic labels

Algoritma key detection:
  Untuk setiap 24 key (12 major + 12 minor), hitung berapa chord dari lagu
  yang masuk ke dalam scale tersebut.  Key dengan skor tertinggi menang.
  Tie-break: major lebih diprioritaskan, lalu urutan circle-of-fifths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Chromatic helpers
# ---------------------------------------------------------------------------

# Semua nama nada dalam bentuk sharp (canonical)
_CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Alias enharmonik → canonical sharp
_ENHARMONIC: Dict[str, str] = {
    "Db": "C#",
    "Eb": "D#",
    "Fb": "E",
    "Gb": "F#",
    "Ab": "G#",
    "Bb": "A#",
    "Cb": "B",
    "E#": "F",
    "B#": "C",
}


def _to_canonical(note: str) -> str:
    """Konversi nama nada ke bentuk canonical (sharp). Contoh: Bb→A#, Db→C#."""
    return _ENHARMONIC.get(note, note)


def _note_index(note: str) -> int:
    """Return index 0–11 dari nada canonical."""
    return _CHROMATIC.index(_to_canonical(note))


# ---------------------------------------------------------------------------
# Scale definitions
# ---------------------------------------------------------------------------

# Interval formula dalam semitone
_MAJOR_INTERVALS = [0, 2, 4, 5, 7, 9, 11]  # W W H W W W H
_MINOR_INTERVALS = [0, 2, 3, 5, 7, 8, 10]  # natural minor

# Chord quality pada tiap derajat tangga nada major
# (triad diatonis: M=major, m=minor, dim=diminished)
_MAJOR_SCALE_QUALITY = ["M", "m", "m", "M", "M", "m", "dim"]
_MINOR_SCALE_QUALITY = ["m", "dim", "M", "m", "m", "M", "M"]

# Roman numeral per derajat
_ROMAN_MAJOR = ["I", "ii", "iii", "IV", "V", "vi", "vii°"]
_ROMAN_MINOR = ["i", "ii°", "III", "iv", "v", "VI", "VII"]

# Fungsi harmonik (Tonic / Subdominant / Dominant)
_FUNCTION_MAJOR = ["T", "SD", "T", "SD", "D", "T", "D"]
_FUNCTION_MINOR = ["T", "D", "T", "SD", "D", "SD", "D"]


# ---------------------------------------------------------------------------
# Borrowed / modal mixture chords (non-diatonic umum di pop)
# ---------------------------------------------------------------------------

# Untuk MAJOR key: chord borrowed dari parallel minor / mode lain.
# Format: interval_from_root → (roman, function)
# Interval dihitung dalam semitone dari root key.
# CATATAN: Hanya chord yang root-nya TIDAK ada di scale diatonis.
#          Chord yang root-nya diatonis tapi quality beda (misal A major
#          di C major, padahal harusnya Am) tetap pakai bracket [vi] saja
#          — agar lebih sederhana untuk analisis level skripsi.
_BORROWED_MAJOR: Dict[Tuple[int, str], Tuple[str, str]] = {
    # --- SECONDARY DOMINANTS (Diubah jadi Absolute Roman) ---
    (2, "M"): ("II", "D"),  # V/V (Secondary Dominant ke V)
    (4, "M"): ("III", "D"),  # V/vi (Secondary Dominant ke vi)
    (9, "M"): ("VI", "D"),  # V/ii (Secondary Dominant ke ii)
    (11, "M"): ("VII", "D"),  # V/iii (Secondary Dominant ke iii)
    # --- MODAL MIXTURE (Pinjaman dari tangga nada Minor/Lainnya) ---
    (0, "m"): ("i", "T"),  # Minor tonic (Modal mixture)
    (3, "M"): ("bIII", "T"),  # Borrowed dari parallel minor
    (5, "m"): ("iv", "SD"),  # Minor subdominant (Sangat umum di pop)
    (7, "m"): ("v", "D"),  # Minor dominant
    (8, "M"): ("bVI", "SD"),  # Borrowed dari parallel minor
    (10, "M"): ("bVII", "SD"),  # Borrowed dari parallel minor / Mixolydian
    # --- PASSING CHORDS & CHROMATIC (Transisi Mayor & Minor) ---
    (1, "M"): ("bII", "SD"),  # Neapolitan chord
    (1, "m"): ("bii", "SD"),  # Passing minor
    (3, "m"): ("biii", "T"),  # Passing minor
    (6, "M"): ("#IV", "D"),  # Lydian passing chord / bV
    (6, "m"): ("#iv", "SD"),  # Passing minor
    (8, "m"): ("#v", "D"),  # Sharp five minor (G#m di C) -> V/vi substitution
    (10, "m"): ("bvii", "SD"),  # Passing minor
    (11, "m"): ("vii", "D"),  # Minor vii (pengganti diminished)
    # --- DIMINISHED (Biasanya secondary leading-tone) ---
    (1, "dim"): ("#i°", "D"),  # vii°/ii
    (2, "dim"): ("ii°", "SD"),  # Borrowed dari minor
    (3, "dim"): ("#ii°", "D"),  # vii°/iii
    (6, "dim"): ("#iv°", "SD"),  # vii°/V (F#dim di C)
    (8, "dim"): ("#v°", "D"),  # vii°/vi (G#dim di C)
    (9, "dim"): ("#vi°", "D"),  # vii°/vii
}

# Untuk MINOR key: chord borrowed
_BORROWED_MINOR: Dict[Tuple[int, str], Tuple[str, str]] = {
    # --- HARMONIC/MELODIC MINOR & MODAL ---
    (0, "M"): ("I", "T"),  # Picardy third (Kord Mayor di akhir lagu minor)
    (2, "m"): ("ii", "SD"),  # Borrowed dari Dorian mode
    (5, "M"): ("IV", "SD"),  # Borrowed dari Dorian mode
    (7, "M"): ("V", "D"),  # Dominant dari Harmonic Minor (SANGAT UMUM)
    (9, "dim"): ("#vi°", "SD"),  # Dari melodic minor
    (11, "dim"): ("vii°", "D"),  # Dari harmonic minor
    (11, "M"): ("VII", "D"),  # Subtonic major (misal Bb di C minor)
    # --- SECONDARY DOMINANTS & PASSING ---
    (1, "M"): ("bII", "SD"),  # Neapolitan chord
    (1, "m"): ("bii", "SD"),  # Passing
    (3, "m"): ("biii", "T"),  # Passing
    (4, "M"): ("III", "D"),  # V/VI
    (4, "m"): ("iii", "T"),  # Minor v dari VI
    (6, "M"): ("#IV", "D"),  # Passing
    (6, "m"): ("#iv", "SD"),  # Passing
    (8, "m"): ("bvi", "SD"),  # Passing
    (9, "m"): ("vi", "SD"),  # Passing
    (10, "m"): ("bvii", "SD"),  # Passing
}


def _build_scale_notes(root: str, intervals: List[int]) -> List[str]:
    """Return daftar 7 nada (canonical) dari suatu tangga nada."""
    root_idx = _note_index(root)
    return [_CHROMATIC[(root_idx + step) % 12] for step in intervals]


# Precompute semua scale
_ALL_KEYS: Dict[str, Tuple[List[str], List[str], List[str], List[str]]] = {}
# key: "C major" → (scale_notes, qualities, romans, functions)

for _root in _CHROMATIC:
    # Major
    _notes = _build_scale_notes(_root, _MAJOR_INTERVALS)
    _ALL_KEYS[f"{_root} major"] = (
        _notes,
        _MAJOR_SCALE_QUALITY,
        _ROMAN_MAJOR,
        _FUNCTION_MAJOR,
    )
    # Minor
    _notes = _build_scale_notes(_root, _MINOR_INTERVALS)
    _ALL_KEYS[f"{_root} minor"] = (
        _notes,
        _MINOR_SCALE_QUALITY,
        _ROMAN_MINOR,
        _FUNCTION_MINOR,
    )


# ---------------------------------------------------------------------------
# Chord parser
# ---------------------------------------------------------------------------

# Regex untuk parse nama chord: root + modifier (m, maj, aug, dim, sus, …)
_CHORD_RE = re.compile(
    r"^([A-G][#b]?)"  # root note
    r"(m(?:aj)?|dim|aug|sus[24]?|add)?"  # quality prefix
    r"([0-9]*)"  # extension number
    r"(?:/([A-G][#b]?))?$"  # optional bass note
)


@dataclass
class ParsedChord:
    root: str  # canonical root (C, C#, D, …)
    quality: str  # "M" (major) or "m" (minor) or "dim" / "aug"
    raw: str  # original chord name
    bass: Optional[str] = None


def parse_chord(chord_str: str) -> Optional[ParsedChord]:
    """Parse chord string menjadi ParsedChord. Return None jika tidak valid."""
    chord_str = chord_str.strip()
    m = _CHORD_RE.match(chord_str)
    if not m:
        return None
    root_raw, quality_prefix, _ext, bass_raw = m.groups()
    root = _to_canonical(root_raw)

    if quality_prefix in ("m",):
        quality = "m"
    elif quality_prefix == "dim":
        quality = "dim"
    elif quality_prefix == "aug":
        quality = "aug"
    else:
        # maj, sus, add, None → dianggap major untuk tujuan key detection
        quality = "M"

    bass = _to_canonical(bass_raw) if bass_raw else None
    return ParsedChord(root=root, quality=quality, raw=chord_str, bass=bass)


# ---------------------------------------------------------------------------
# Key detection
# ---------------------------------------------------------------------------


def detect_key(chords: List[str], top_n: int = 3) -> List[Tuple[str, float]]:
    """
    Deteksi key dari daftar nama chord.

    Return list of (key_name, score) diurutkan dari skor tertinggi.
    Score = fraksi chord yang cocok dengan tangga nada tersebut (0.0–1.0).

    Parameters
    ----------
    chords  : list of chord name strings (e.g. ["Am", "F", "G", "C"])
    top_n   : berapa banyak kandidat key yang dikembalikan

    Returns
    -------
    List of (key_name, score), contoh: [("C major", 1.0), ("A minor", 1.0), ...]
    """
    parsed = [parse_chord(c) for c in chords]
    parsed = [p for p in parsed if p is not None]
    if not parsed:
        return []

    scores: Dict[str, float] = {}

    for key_name, (scale_notes, qualities, _, _) in _ALL_KEYS.items():
        match_count = 0
        key_root = key_name.rsplit(" ", 1)[0]
        key_mode = key_name.rsplit(" ", 1)[1]
        key_root_idx = _note_index(key_root)
        borrowed_table = _BORROWED_MAJOR if key_mode == "major" else _BORROWED_MINOR

        for pc in parsed:
            # Cek apakah root ada di scale
            if pc.root in scale_notes:
                degree = scale_notes.index(pc.root)
                expected_q = qualities[degree]
                # Cek kecocokan quality
                if pc.quality == expected_q:
                    match_count += 1
                elif pc.quality == "M" and expected_q == "M":
                    match_count += 1
                elif pc.quality == "m" and expected_q == "m":
                    match_count += 1
                elif pc.quality == "M" and expected_q == "dim":
                    # Chord major pada derajat vii (borrowed/secondary) → partial credit
                    match_count += 0.5
                elif pc.quality in ("M", "m"):
                    # Root ada di scale tapi quality beda → partial credit
                    match_count += 0.3
            else:
                # Root tidak di scale → cek apakah borrowed chord
                chord_interval = (_note_index(pc.root) - key_root_idx) % 12
                if (chord_interval, pc.quality) in borrowed_table:
                    match_count += 0.6  # borrowed chord = significant partial credit

        scores[key_name] = match_count / len(parsed)

    # Urutkan: skor tertinggi, major diprioritaskan, circle-of-fifths order
    _cof_order = ["C", "G", "D", "A", "E", "B", "F#", "C#", "F", "A#", "D#", "G#"]

    def sort_key(item):
        name, score = item
        root, mode = name.rsplit(" ", 1)
        mode_priority = 0 if mode == "major" else 1
        cof_priority = (
            _cof_order.index(_to_canonical(root))
            if _to_canonical(root) in _cof_order
            else 99
        )
        return (-score, mode_priority, cof_priority)

    ranked = sorted(scores.items(), key=sort_key)
    return ranked[:top_n]


def best_key(chords: List[str]) -> Optional[str]:
    """Return nama key terbaik (string), atau None jika tidak ada chord."""
    results = detect_key(chords, top_n=1)
    return results[0][0] if results else None


# ---------------------------------------------------------------------------
# Harmonic function mapping
# ---------------------------------------------------------------------------


@dataclass
class HarmonicLabel:
    chord: str  # original chord name
    key: str  # key context
    degree: int  # 1-based scale degree (1–7), 0 = non-diatonic
    roman: str  # e.g. "IV", "vi", "V"
    function: str  # "T" (tonic), "SD" (subdominant), "D" (dominant), "?" (non-diatonic)
    is_diatonic: bool


def chord_harmonic(chord_str: str, key: str) -> HarmonicLabel:
    """
    Return HarmonicLabel untuk satu chord dalam konteks key tertentu.

    Urutan pengecekan:
    1. Diatonic exact match (root + quality cocok dgn scale)
    2. Diatonic root match tapi quality beda → bracket notation [IV]
    3. Borrowed / modal mixture chord (bVII, V/V, iv, dll.)
    4. Jika semuanya gagal → "?" (truly unknown)

    Parameters
    ----------
    chord_str : nama chord, e.g. "Am", "G7", "F#m"
    key       : key string, e.g. "C major", "A minor"
    """
    pc = parse_chord(chord_str)
    if pc is None or key not in _ALL_KEYS:
        return HarmonicLabel(chord_str, key, 0, "?", "?", False)

    scale_notes, qualities, romans, functions = _ALL_KEYS[key]

    # --- 1. Diatonic check ---
    if pc.root in scale_notes:
        degree = scale_notes.index(pc.root)  # 0-based
        expected_q = qualities[degree]

        # Exact quality match (relaxed: 7th, sus, add → still counts)
        quality_ok = pc.quality == expected_q or (
            pc.quality == "M" and expected_q in ("M", "dim")
        )

        if quality_ok:
            return HarmonicLabel(
                chord=chord_str,
                key=key,
                degree=degree + 1,
                roman=romans[degree],
                function=functions[degree],
                is_diatonic=True,
            )
        # Root di scale tapi quality beda → cek borrowed dulu sebelum bracket

    # --- 2. Borrowed / modal mixture check ---
    # (juga mencakup kasus root diatonis tapi quality non-diatonis,
    #  e.g. A major di C major = V/ii, bukan [vi])
    key_root = key.rsplit(" ", 1)[0]
    key_mode = key.rsplit(" ", 1)[1]  # "major" or "minor"
    key_root_idx = _note_index(key_root)
    chord_interval = (_note_index(pc.root) - key_root_idx) % 12

    borrowed_table = _BORROWED_MAJOR if key_mode == "major" else _BORROWED_MINOR
    lookup = (chord_interval, pc.quality)

    if lookup in borrowed_table:
        roman, func = borrowed_table[lookup]
        return HarmonicLabel(
            chord=chord_str,
            key=key,
            degree=0,  # non-diatonic, no scale degree
            roman=roman,
            function=func,
            is_diatonic=False,
        )

    # --- 3. Diatonic root but non-diatonic quality (bracket fallback) ---
    if pc.root in scale_notes:
        degree = scale_notes.index(pc.root)
        return HarmonicLabel(
            chord=chord_str,
            key=key,
            degree=degree + 1,
            roman=f"[{romans[degree]}]",
            function=functions[degree],
            is_diatonic=False,
        )

    # --- 4. Truly unknown ---
    return HarmonicLabel(chord_str, key, 0, "?", "?", False)


def analyse_chords(chords: List[str], key: Optional[str] = None) -> Dict:
    """
    Analisis lengkap daftar chord: deteksi key + harmonic labeling.

    Return dict:
    {
        "detected_key": "C major",
        "key_confidence": 0.83,
        "key_candidates": [("C major", 1.0), ("A minor", 1.0)],
        "labels": [HarmonicLabel, ...],
        "summary": {"T": [...], "SD": [...], "D": [...], "?": [...]}
    }
    """
    candidates = detect_key(chords)
    if key is None:
        key = candidates[0][0] if candidates else None
    confidence = candidates[0][1] if candidates else 0.0

    labels = [chord_harmonic(c, key) for c in chords] if key else []

    summary: Dict[str, List[str]] = {"T": [], "SD": [], "D": [], "?": []}
    for lbl in labels:
        summary[lbl.function].append(lbl.chord)

    return {
        "detected_key": key,
        "key_confidence": round(confidence, 3),
        "key_candidates": candidates,
        "labels": labels,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------


def print_analysis(chords: List[str], key: Optional[str] = None) -> None:
    """Print analisis harmonik ke stdout (human-readable)."""
    result = analyse_chords(chords, key)

    print(
        f"\n  Detected key : {result['detected_key']}  "
        f"(confidence {result['key_confidence']:.0%})"
    )

    if len(result["key_candidates"]) > 1:
        others = ", ".join(f"{k} ({s:.0%})" for k, s in result["key_candidates"][1:])
        print(f"  Other candidates: {others}")

    print()
    print(f"  {'Chord':<10} {'Roman':<8} {'Function':<12} {'Diatonic'}")
    print(f"  {'-'*10} {'-'*8} {'-'*12} {'-'*8}")
    for lbl in result["labels"]:
        diatonic_mark = "✓" if lbl.is_diatonic else "✗"
        func_name = {
            "T": "Tonic",
            "SD": "Subdominant",
            "D": "Dominant",
            "?": "Non-diatonic",
        }.get(lbl.function, lbl.function)
        print(f"  {lbl.chord:<10} {lbl.roman:<8} {func_name:<12} {diatonic_mark}")

    print()
    print(
        f"  Tonic (T)       : {', '.join(dict.fromkeys(result['summary']['T'])) or '-'}"
    )
    print(
        f"  Subdominant (SD): {', '.join(dict.fromkeys(result['summary']['SD'])) or '-'}"
    )
    print(
        f"  Dominant (D)    : {', '.join(dict.fromkeys(result['summary']['D'])) or '-'}"
    )
    if result["summary"]["?"]:
        print(f"  Non-diatonic    : {', '.join(dict.fromkeys(result['summary']['?']))}")
