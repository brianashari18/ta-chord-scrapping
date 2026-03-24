"""
main.py - CLI entry point for the Chord Scraper system
Usage:
    python main.py search  "judul lagu" --source chordtela --max 5 --export csv
    python main.py fetch   "https://www.chordtela.com/..." --export json
    python main.py batch   queries.txt --source all --export csv
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from scrapers.chordtela import ChordtelaScraper
from scrapers.ultimateguitar import UltimateGuitarScraper
from exporter import Exporter
from models import ChordSong

console = Console()

# Registry of available scrapers
SCRAPERS = {
    "chordtela": ChordtelaScraper,
    "ultimateguitar": UltimateGuitarScraper,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_scrapers(source: str) -> list:
    """Return instantiated scraper(s) based on the source argument."""
    if source == "all":
        return [cls() for cls in SCRAPERS.values()]
    if source in SCRAPERS:
        return [SCRAPERS[source]()]
    console.print(
        f"[red]Unknown source '{source}'. Choose from: {', '.join(SCRAPERS)} or 'all'[/red]"
    )
    sys.exit(1)


def print_search_table(results):
    table = Table(title="Search Results", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold cyan")
    table.add_column("Artist", style="green")
    table.add_column("Source", style="magenta")
    table.add_column("URL", style="dim", overflow="fold")
    for i, r in enumerate(results, 1):
        table.add_row(str(i), r.title, r.artist, r.source, r.url)
    console.print(table)


def print_song(song: ChordSong):
    info_lines = [
        f"[bold]Title[/bold]  : {song.title}",
        f"[bold]Artist[/bold] : {song.artist}",
        f"[bold]Source[/bold] : {song.source}",
    ]
    if song.key:
        info_lines.append(f"[bold]Key[/bold]    : {song.key}")
    if song.capo:
        info_lines.append(f"[bold]Capo[/bold]   : {song.capo}")
    if song.tempo:
        info_lines.append(f"[bold]Tempo[/bold]  : {song.tempo}")
    if song.chords_used:
        info_lines.append(f"[bold]Chords[/bold] : {', '.join(song.chords_used)}")
    if song.detected_key:
        conf = f" ({song.key_confidence:.0%})" if song.key_confidence else ""
        info_lines.append(f"[bold]Key (auto)[/bold]: {song.detected_key}{conf}")
    if song.harmonic_map:
        # Escape brackets so Rich does not treat [vi] etc. as markup tags
        parts = [
            f"{c}={v['roman'].replace('[', '\\[')}"
            for c, v in song.harmonic_map.items()
        ]
        info_lines.append(f"[bold]Harmonic[/bold]  : {', '.join(parts)}")
    console.print(Panel("\n".join(info_lines), title="Song Info", border_style="blue"))

    if song.chord_content:
        console.print(
            Panel(
                song.chord_content[:2000],
                title="Chord Sheet (preview)",
                border_style="green",
            )
        )


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


def cmd_search(args):
    """Search for a song across one or all sources."""
    scrapers = get_scrapers(args.source)
    exporter = Exporter(output_dir=args.output_dir)

    all_results = []
    for scraper in scrapers:
        console.print(
            f"\n[yellow]Searching '{args.query}' on {scraper.SOURCE_NAME}...[/yellow]"
        )
        results = scraper.search(args.query, max_results=args.max)
        all_results.extend(results)
        console.print(f"  Found {len(results)} result(s).")

    if not all_results:
        console.print("[red]No results found.[/red]")
        return

    print_search_table(all_results)

    if args.fetch:
        songs = []
        for item in all_results:
            scraper = SCRAPERS[item.source]()
            song = scraper.get_song(item.url)
            if song:
                songs.append(song)
                print_song(song)
        _export(songs, exporter, args)


def cmd_fetch(args):
    """Fetch and display a single song by URL."""
    # Auto-detect source from URL
    source = "chordtela" if "chordtela" in args.url else "ultimateguitar"
    if source not in SCRAPERS:
        console.print("[red]Cannot detect source from URL.[/red]")
        sys.exit(1)

    scraper = SCRAPERS[source]()
    console.print(f"[yellow]Fetching {args.url} ...[/yellow]")
    song = scraper.get_song(args.url)

    if not song:
        console.print("[red]Failed to fetch song.[/red]")
        return

    print_song(song)

    exporter = Exporter(output_dir=args.output_dir)
    _export([song], exporter, args)


def cmd_batch(args):
    """Batch-search a list of queries from a text file (one query per line)."""
    query_file = Path(args.file)
    if not query_file.exists():
        console.print(f"[red]File not found: {query_file}[/red]")
        sys.exit(1)

    queries = [
        line.strip()
        for line in query_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    scrapers = get_scrapers(args.source)
    exporter = Exporter(output_dir=args.output_dir)
    all_songs = []

    for query in queries:
        for scraper in scrapers:
            console.print(
                f"[yellow]Batch: searching '{query}' on {scraper.SOURCE_NAME}...[/yellow]"
            )
            songs = scraper.search_and_fetch(query, max_results=args.max)
            all_songs.extend(songs)

    console.print(f"\n[green]Total songs fetched: {len(all_songs)}[/green]")
    _export(all_songs, exporter, args)


def _export(songs, exporter: Exporter, args):
    if not songs or not args.export:
        return
    fmt = args.export.lower()
    if fmt == "csv":
        exporter.to_csv(songs)
    elif fmt == "json":
        exporter.to_json(songs)
    elif fmt == "text":
        for song in songs:
            exporter.to_text(song)
    else:
        console.print(
            f"[red]Unknown export format '{fmt}'. Use csv, json, or text.[/red]"
        )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chord-scraper",
        description="🎸 Chord Scraper - Ambil chord dari berbagai situs musik",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Folder untuk menyimpan hasil (default: output/)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- search ---
    p_search = sub.add_parser("search", help="Cari lagu berdasarkan judul/artis")
    p_search.add_argument("query", help="Kata kunci pencarian")
    p_search.add_argument(
        "--source",
        default="chordtela",
        choices=list(SCRAPERS.keys()) + ["all"],
        help="Sumber data (default: chordtela)",
    )
    p_search.add_argument(
        "--max", type=int, default=5, help="Jumlah hasil (default: 5)"
    )
    p_search.add_argument(
        "--fetch", action="store_true", help="Langsung ambil detail setiap lagu"
    )
    p_search.add_argument(
        "--export", choices=["csv", "json", "text"], help="Format ekspor hasil"
    )
    p_search.set_defaults(func=cmd_search)

    # --- fetch ---
    p_fetch = sub.add_parser("fetch", help="Ambil chord dari satu URL langsung")
    p_fetch.add_argument("url", help="URL halaman chord")
    p_fetch.add_argument(
        "--export", choices=["csv", "json", "text"], help="Format ekspor hasil"
    )
    p_fetch.set_defaults(func=cmd_fetch)

    # --- batch ---
    p_batch = sub.add_parser("batch", help="Cari banyak lagu sekaligus dari file teks")
    p_batch.add_argument(
        "file", help="Path ke file teks berisi daftar query (1 baris = 1 query)"
    )
    p_batch.add_argument(
        "--source",
        default="chordtela",
        choices=list(SCRAPERS.keys()) + ["all"],
        help="Sumber data (default: chordtela)",
    )
    p_batch.add_argument(
        "--max", type=int, default=3, help="Hasil per query (default: 3)"
    )
    p_batch.add_argument(
        "--export", choices=["csv", "json", "text"], help="Format ekspor hasil"
    )
    p_batch.set_defaults(func=cmd_batch)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
