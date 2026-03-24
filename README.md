# 🎸 Chord Scraper

Sistem scraping chord lagu dari berbagai situs musik populer, dibangun dengan Python.
Dilengkapi dengan **deteksi key otomatis** dan **analisis fungsi harmonik** (Roman numerals).

## Fitur
- Scraping dari **Chordtela** (lagu Indonesia & internasional)
- Scraping dari **Ultimate Guitar** (database chord internasional terbesar)
- Ekstraksi otomatis chord yang digunakan dalam sebuah lagu
- **Deteksi key otomatis** — algoritma diatonic fit scoring pada 24 key (12 major + 12 minor)
- **Analisis fungsi harmonik** — setiap chord dilabeli Roman numeral (I, ii, iii, IV, V, vi, vii°) dan fungsi (Tonic / Subdominant / Dominant)
- Export hasil ke **CSV**, **JSON**, atau **TXT** (chord sheet)
- Mode **batch**: cari banyak lagu sekaligus dari file teks
- Tampilan terminal yang rapi menggunakan `rich`

## Struktur Proyek
```
Chord Scrapping/
├── main.py             ← Entry point / CLI
├── models.py           ← Data model (ChordSong, SearchResult)
├── harmony.py          ← Deteksi key & analisis fungsi harmonik
├── exporter.py         ← Export ke CSV / JSON / TXT
├── requirements.txt
├── queries.txt         ← Contoh file batch query
├── output/             ← Hasil scraping disimpan di sini
└── scrapers/
    ├── __init__.py
    ├── base.py         ← Abstract base scraper (cloudscraper session)
    ├── chordtela.py    ← Scraper Chordtela
    └── ultimateguitar.py ← Scraper Ultimate Guitar
```

## Instalasi

```bash
pip install -r requirements.txt
```

> **Catatan:** Proyek ini menggunakan `cloudscraper` untuk melewati proteksi Cloudflare pada beberapa situs.

## Cara Penggunaan

### 1. Cari lagu (search only)
```bash
python main.py search "Madu Kangen Band" --source chordtela --max 5
```

### 2. Cari + langsung ambil detail chord
```bash
python main.py search "Yellow Coldplay" --source ultimateguitar --max 3 --fetch --export csv
```

### 3. Ambil chord dari URL langsung
```bash
python main.py fetch "https://www.chordtela.com/2016/08/vierra-perih.html" --export text
```

### 4. Batch search dari file
```bash
python main.py batch queries.txt --source chordtela --max 2 --export json
```

### 5. Cari di semua sumber sekaligus
```bash
python main.py search "Wonderwall" --source all --max 3 --fetch --export csv
```

## Argumen CLI

| Argumen | Deskripsi |
|---------|-----------|
| `--source` | `chordtela`, `ultimateguitar`, atau `all` |
| `--max` | Jumlah hasil pencarian per sumber |
| `--fetch` | Langsung ambil detail setiap hasil pencarian |
| `--export` | Format ekspor: `csv`, `json`, atau `text` |
| `--output-dir` | Folder tujuan file hasil (default: `output/`) |

## Output

Semua file hasil disimpan di folder `output/`:
- `chords.csv` — semua lagu dalam satu tabel
- `chords.json` — data terstruktur JSON
- `<judul lagu>.txt` — chord sheet per lagu

### Field Output
| Field | Deskripsi |
|-------|-----------|
| `title` | Judul lagu |
| `artist` | Nama artis |
| `key` | Key asli dari situs (jika tersedia) |
| `detected_key` | Key hasil deteksi otomatis (e.g. `C major`, `A minor`) |
| `key_confidence` | Tingkat kepercayaan deteksi key (0.0 – 1.0) |
| `harmonic_map` | Mapping chord → Roman numeral & fungsi harmonik |
| `chords_used` | Daftar chord unik yang digunakan |
| `chord_content` | Teks chord + lirik lengkap |

## Analisis Harmonik

Modul `harmony.py` secara otomatis mendeteksi key dan memberikan label fungsi harmonik pada setiap chord:

- **Algoritma**: Diatonic fit scoring — tiap 24 key (12 major + 12 minor) dievaluasi berdasarkan berapa chord lagu yang cocok dengan scale + quality. Tie-break: major diprioritaskan, lalu urutan circle-of-fifths.
- **Output**: Roman numeral (I, ii, iii, IV, V, vi, vii°) dan fungsi (Tonic / Subdominant / Dominant)

Contoh output untuk lagu dengan chord `[F, Em, Am, Dm, G, C]` di key C major (confidence 100%):
```
  F = IV   (Subdominant)
  Em = iii (Tonic)
  Am = vi  (Tonic)
  Dm = ii  (Subdominant)
  G = V    (Dominant)
  C = I    (Tonic)
```

## Catatan
- Scraper menghormati server dengan delay antar request (~1–2 detik)
- Beberapa situs mungkin memblokir bot; gunakan secara wajar
- Ultimate Guitar menggunakan data JSON yang disematkan di halaman HTML
- Chordtela menggunakan strategi navigasi halaman indeks artis (bukan search, karena halaman search dirender via JavaScript)
