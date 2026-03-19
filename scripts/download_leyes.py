#!/usr/bin/env python3
"""
download_leyes.py — Descarga los PDFs de todas las leyes federales vigentes
desde la Cámara de Diputados (diputados.gob.mx).

Uso:
    python scripts/download_leyes.py                  # Descarga todo
    python scripts/download_leyes.py --list           # Solo muestra el catálogo
    python scripts/download_leyes.py --limit 5        # Solo las primeras 5
    python scripts/download_leyes.py --skip-existing   # No re-descarga
"""

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.request
import urllib.error
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "https://www.diputados.gob.mx/LeyesBiblio/"
INDEX_URL = BASE_URL + "index.htm"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) mx-md/1.0"

ROOT = Path(__file__).parent.parent
ORIGEN_DIR = ROOT / "origen-docs"
CATALOG_PATH = ROOT / "catalogo.json"


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

class LeyesTableParser(HTMLParser):
    """Parses the leyes table from diputados.gob.mx/LeyesBiblio/index.htm"""

    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []
        self._in_tr = False
        self._in_td = False
        self._td_index = 0
        self._current_row: dict = {}
        self._current_text = ""
        self._current_links: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "tr":
            self._in_tr = True
            self._td_index = 0
            self._current_row = {}
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._current_text = ""
            self._current_links = []
        elif tag == "a" and self._in_td:
            href = attrs_dict.get("href", "")
            if href:
                self._current_links.append(href)

    def handle_endtag(self, tag):
        if tag == "td" and self._in_td:
            self._in_td = False
            text = re.sub(r'\s+', ' ', self._current_text).strip()

            if self._td_index == 0:
                self._current_row["numero"] = text
            elif self._td_index == 1:
                self._current_row["nombre_raw"] = text
            elif self._td_index == 2:
                self._current_row["ultima_reforma"] = text
            elif self._td_index == 3:
                self._current_row["links"] = self._current_links[:]

            self._td_index += 1
        elif tag == "tr" and self._in_tr:
            self._in_tr = False
            if "numero" in self._current_row and "links" in self._current_row:
                self.rows.append(self._current_row)

    def handle_data(self, data):
        if self._in_td:
            self._current_text += data


def parse_law_name(raw: str) -> tuple[str, str]:
    """
    Extrae nombre limpio y fecha DOF del texto raw de la celda.
    Returns (nombre, dof_date).
    """
    # Remove "(Abrogado...)" and "(Antes ...)" notes for the name
    # but keep them for reference
    lines = raw.split("DOF")
    nombre = lines[0].strip().rstrip()
    # Clean trailing whitespace, 'Nueva reforma', etc.
    nombre = re.sub(r'\s*(Nueva reforma|Ley en vigor.*|Ley Abrogada.*)$', '', nombre, flags=re.IGNORECASE).strip()

    dof_date = ""
    if len(lines) > 1:
        dof_date = "DOF" + lines[1].strip().split("(")[0].strip()
        dof_date = re.sub(r'\s+', ' ', dof_date).strip()

    return nombre, dof_date


def slugify(text: str, max_len: int = 70) -> str:
    """Convert text to snake_case ASCII slug."""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = text.strip('_')
    if len(text) > max_len:
        text = text[:max_len].rstrip('_')
    return text


_STOP_WORDS = {
    'de', 'del', 'la', 'las', 'los', 'el', 'en', 'y', 'e', 'o', 'u', 'a',
    'al', 'con', 'por', 'para', 'que', 'se', 'su', 'sus', 'un', 'una',
    'sobre', 'entre', 'ante', 'sin', 'si', 'no', 'lo',
}

def derive_acronym(nombre: str, max_len: int = 8) -> str:
    """
    Derives an acronym from the law's name by taking the first letter of each
    significant word in the main clause (before the first comma or parenthesis),
    ignoring stop words. Max max_len characters.
    E.g. 'ESTATUTO de Gobierno del Distrito Federal' -> 'EGDF'
         'IMPUESTO sobre Servicios Expresamente Declarados...' -> 'ISEDIP'
    """
    # Take only the main clause (before first comma or parenthesis)
    main = re.split(r'[,(]', nombre)[0].strip()
    words = re.split(r'[\s\-/]+', main)
    letters = [
        w[0].upper()
        for w in words
        if w and w.lower() not in _STOP_WORDS and w[0].isalpha()
    ]
    return ''.join(letters[:max_len]) or 'LEY'


def compute_md_slug(pdf_stem: str, nombre: str, numero: str) -> str:
    """
    Computes a clean filename slug: {ABBREV}_{nombre_snake}.
    Uses the PDF stem as abbreviation if it looks like an acronym (starts with a letter).
    Otherwise derives an acronym from the law name.
    """
    name_slug = slugify(nombre, max_len=70)
    if len(pdf_stem) > 0 and not pdf_stem[0].isdigit():
        abbrev = pdf_stem
    else:
        abbrev = derive_acronym(nombre)
    return f"{abbrev}_{name_slug}"


def fetch_index() -> list[dict]:
    """Fetches and parses the leyes index page. Returns list of law dicts."""
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": USER_AGENT})
    html = urllib.request.urlopen(req, timeout=30).read().decode("latin-1")

    parser = LeyesTableParser()
    parser.feed(html)

    laws = []
    for row in parser.rows:
        numero = row.get("numero", "").strip()
        # Skip the header row
        if not numero or numero.lower() == "no.":
            continue

        nombre, dof = parse_law_name(row.get("nombre_raw", ""))
        ultima_reforma = row.get("ultima_reforma", "").strip()

        # Find the PDF link (not pdf_mov)
        pdf_href = ""
        for link in row.get("links", []):
            if link.startswith("pdf/") and link.endswith(".pdf"):
                pdf_href = link
                break

        if not pdf_href:
            continue

        pdf_filename = pdf_href.split("/")[-1]
        pdf_stem = Path(pdf_filename).stem
        pdf_url = BASE_URL + pdf_href
        md_slug = compute_md_slug(pdf_stem, nombre, numero)

        laws.append({
            "numero": numero,
            "nombre": nombre,
            "dof": dof,
            "ultima_reforma": ultima_reforma,
            "pdf_url": pdf_url,
            "pdf_filename": pdf_filename,
            "md_slug": md_slug,
        })

    return laws


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_pdf(url: str, dest: Path, verbose: bool = False) -> bool:
    """Downloads a single PDF. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        resp = urllib.request.urlopen(req, timeout=60)
        data = resp.read()

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)

        if verbose:
            size_mb = len(data) / (1024 * 1024)
            print(f"  ✅ {dest.name} ({size_mb:.1f} MB)")
        return True

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  ❌ Error descargando {url}: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga PDFs de leyes federales vigentes desde diputados.gob.mx",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Solo muestra el catálogo sin descargar.",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limita la descarga a N leyes (0 = todas).",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="No re-descarga PDFs que ya existen en origen-docs/.",
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=ORIGEN_DIR,
        help=f"Directorio de salida para los PDFs (default: {ORIGEN_DIR}).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Muestra progreso detallado.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("📡 Obteniendo catálogo de leyes desde diputados.gob.mx...", flush=True)
    laws = fetch_index()
    print(f"📋 {len(laws)} leyes encontradas.\n", flush=True)

    # Save catalog
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(laws, f, ensure_ascii=False, indent=2)
    print(f"💾 Catálogo guardado en {CATALOG_PATH}\n")

    if args.list:
        for law in laws:
            print(f"  {law['numero']:>3}  {law['nombre'][:80]}")
            print(f"       PDF: {law['pdf_filename']}  |  Reforma: {law['ultima_reforma']}")
        return

    # Download
    subset = laws[:args.limit] if args.limit > 0 else laws
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    for i, law in enumerate(subset, 1):
        dest = output_dir / law["pdf_filename"]
        label = f"[{i}/{len(subset)}] {law['pdf_filename']}"

        if args.skip_existing and dest.exists():
            if args.verbose:
                print(f"  ⏭️  {label} (ya existe)")
            skipped += 1
            continue

        print(f"  ⬇️  {label}...", end="", flush=True)
        if download_pdf(law["pdf_url"], dest, verbose=False):
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f" ✅ ({size_mb:.1f} MB)")
            downloaded += 1
        else:
            failed += 1

        # Be polite to the server
        time.sleep(0.3)

    print(f"\n📊 Resultado: {downloaded} descargados, {skipped} omitidos, {failed} errores")
    print(f"📁 PDFs en: {output_dir}")


if __name__ == "__main__":
    main()
