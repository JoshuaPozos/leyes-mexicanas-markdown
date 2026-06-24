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
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from _log import get_logger
from constants import (
    ACRONYM_MAX_LENGTH,
    ALLOWED_DOWNLOAD_HOSTS,
    BETWEEN_DOWNLOADS_SLEEP_SECS,
    DOWNLOAD_BACKOFF_BASE_SECS,
    DOWNLOAD_MAX_RETRIES,
    INDEX_FETCH_TIMEOUT_SECS,
    PDF_DOWNLOAD_TIMEOUT_SECS,
    PDF_MAGIC_BYTES,
    SLUG_MAX_LENGTH,
)

logger = get_logger(__name__)

BASE_URL = "https://www.diputados.gob.mx/LeyesBiblio/"
INDEX_URL = BASE_URL + "index.htm"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) mx-md/1.0"

ROOT = Path(__file__).parent.parent
ORIGEN_DIR = ROOT / "origen-docs"
CATALOG_PATH = ROOT / "catalogo.json"


# ---------------------------------------------------------------------------
# Regex pre-compilados (usados dentro de loops sobre filas / leyes / palabras)
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r'\s+')
_LAW_NAME_TRAILING_RE = re.compile(
    r'\s*(Nueva reforma|Ley en vigor.*|Ley Abrogada.*)$',
    re.IGNORECASE,
)
_SLUG_NON_ALNUM_RE = re.compile(r'[^a-z0-9]+')
_PDF_STEM_NUMERIC_SUFFIX_RE = re.compile(r'_\d+$')
_ACRONYM_CLAUSE_BREAK_RE = re.compile(r'[,(]')
_ACRONYM_WORD_BREAK_RE = re.compile(r'[\s\-/]+')


# ---------------------------------------------------------------------------
# Análisis HTML
# ---------------------------------------------------------------------------

class LeyesTableParser(HTMLParser):
    """Analiza la tabla de leyes de diputados.gob.mx/LeyesBiblio/index.htm"""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self._in_tr = False
        self._in_td = False
        self._td_index = 0
        self._current_row: dict = {}
        self._current_text = ""
        self._current_links: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_td:
            self._in_td = False
            text = _WHITESPACE_RE.sub(' ', self._current_text).strip()

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

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._current_text += data


def parse_law_name(raw: str) -> tuple[str, str]:
    """
    Extrae nombre limpio y fecha DOF del texto raw de la celda.
    Devuelve (nombre, dof_date).
    """
    # Eliminar notas "(Abrogado...)" y "(Antes ...)" del nombre,
    # pero conservarlas como referencia
    lines = raw.split("DOF")
    nombre = lines[0].strip().rstrip()
    # Limpiar espacios sobrantes, 'Nueva reforma', etc.
    nombre = _LAW_NAME_TRAILING_RE.sub('', nombre).strip()

    dof_date = ""
    if len(lines) > 1:
        dof_date = "DOF" + lines[1].strip().split("(")[0].strip()
        dof_date = _WHITESPACE_RE.sub(' ', dof_date).strip()

    return nombre, dof_date


def slugify(text: str, max_len: int = SLUG_MAX_LENGTH) -> str:
    """Convierte texto a slug snake_case ASCII."""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower()
    text = _SLUG_NON_ALNUM_RE.sub('_', text)
    text = text.strip('_')
    if len(text) > max_len:
        text = text[:max_len].rstrip('_')
    return text


_STOP_WORDS = {
    'de', 'del', 'la', 'las', 'los', 'el', 'en', 'y', 'e', 'o', 'u', 'a',
    'al', 'con', 'por', 'para', 'que', 'se', 'su', 'sus', 'un', 'una',
    'sobre', 'entre', 'ante', 'sin', 'si', 'no', 'lo',
}

def derive_acronym(nombre: str, max_len: int = ACRONYM_MAX_LENGTH) -> str:
    """
    Deriva un acrónimo del nombre de la ley tomando la primera letra de cada
    palabra significativa en la cláusula principal (antes de la primera coma
    o paréntesis), ignorando las palabras vacías. Máximo max_len caracteres.
    Ej. 'ESTATUTO de Gobierno del Distrito Federal' -> 'EGDF'
        'IMPUESTO sobre Servicios Expresamente Declarados...' -> 'ISEDIP'
    """
    # Tomar solo la cláusula principal (antes de la primera coma o paréntesis)
    main = _ACRONYM_CLAUSE_BREAK_RE.split(nombre)[0].strip()
    words = _ACRONYM_WORD_BREAK_RE.split(main)
    letters = [
        w[0].upper()
        for w in words
        if w and w.lower() not in _STOP_WORDS and w[0].isalpha()
    ]
    return ''.join(letters[:max_len]) or 'LEY'


def compute_md_slug(pdf_stem: str, nombre: str, numero: str) -> str:
    """
    Construye el slug de nombre de archivo: {ABREV}_{nombre_snake}.
    Usa el stem del PDF como abreviatura si parece un acrónimo (empieza con letra),
    eliminando cualquier sufijo numérico al final (ej. LCEC_120419 → LCEC).
    Si no, deriva un acrónimo del nombre de la ley.
    """
    name_slug = slugify(nombre)
    if len(pdf_stem) > 0 and not pdf_stem[0].isdigit():
        # Eliminar sufijo numérico al final (ej. _120419, _270614)
        abbrev = _PDF_STEM_NUMERIC_SUFFIX_RE.sub('', pdf_stem)
    else:
        abbrev = derive_acronym(nombre)
    return f"{abbrev}_{name_slug}"


def fetch_index() -> list[dict]:
    """Obtiene y analiza la página del índice de leyes. Devuelve lista de dicts."""
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": USER_AGENT})
    html = urllib.request.urlopen(req, timeout=INDEX_FETCH_TIMEOUT_SECS).read().decode("latin-1")

    parser = LeyesTableParser()
    parser.feed(html)

    laws = []
    for row in parser.rows:
        numero = row.get("numero", "").strip()
        # Saltar la fila de encabezado
        if not numero or numero.lower() == "no.":
            continue

        nombre, dof = parse_law_name(row.get("nombre_raw", ""))
        ultima_reforma = row.get("ultima_reforma", "").strip()

        # Buscar el enlace al PDF (no pdf_mov)
        pdf_href = ""
        for link in row.get("links", []):
            if link.startswith("pdf/") and link.endswith(".pdf"):
                pdf_href = link
                break

        if not pdf_href:
            continue

        pdf_filename_origen = pdf_href.split("/")[-1]
        pdf_stem = Path(pdf_filename_origen).stem
        pdf_url = BASE_URL + pdf_href
        md_slug = compute_md_slug(pdf_stem, nombre, numero)
        pdf_filename = f"{md_slug}.pdf"

        laws.append({
            "numero": numero,
            "nombre": nombre,
            "dof": dof,
            "ultima_reforma": ultima_reforma,
            "pdf_url": pdf_url,
            "pdf_filename": pdf_filename,
            "pdf_filename_origen": pdf_filename_origen,
            "md_slug": md_slug,
        })

    return laws


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _is_url_allowed(url: str, allowed_hosts: tuple[str, ...]) -> bool:
    """True si el host de `url` está en la allowlist. Lista vacía = sin
    restricción (útil para tests). Acepta solo http/https."""
    if not allowed_hosts:
        return True
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    return parsed.hostname in allowed_hosts


def _sha256_file(path: Path) -> str:
    """SHA-256 hex de un archivo local, leído en bloques (no carga todo a RAM)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_pdf(
    url: str,
    dest: Path,
    verbose: bool = False,
    *,
    max_retries: int = DOWNLOAD_MAX_RETRIES,
    allowed_hosts: tuple[str, ...] = ALLOWED_DOWNLOAD_HOSTS,
) -> str | None:
    """Descarga un PDF con retry + validación. Retorna el SHA-256 hex en
    éxito, `None` en cualquier fallo (URL fuera de allowlist, bytes mágicos
    inválidos, error de red tras agotar reintentos)."""
    if not _is_url_allowed(url, allowed_hosts):
        logger.error("URL fuera de allowlist (rechazada): %s", url)
        print(f"  ❌ URL no permitida: {url}", file=sys.stderr)
        return None

    last_err: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            resp = urllib.request.urlopen(req, timeout=PDF_DOWNLOAD_TIMEOUT_SECS)
            data = resp.read()

            if not data.startswith(PDF_MAGIC_BYTES):
                logger.error("Bytes mágicos inválidos (no es PDF) para %s", url)
                print(f"  ❌ Respuesta no es un PDF válido: {url}", file=sys.stderr)
                return None

            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)

            sha = hashlib.sha256(data).hexdigest()
            if verbose:
                size_mb = len(data) / (1024 * 1024)
                print(f"  ✅ {dest.name} ({size_mb:.1f} MB, sha256={sha[:12]}…)")
            return sha

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            if attempt < max_retries:
                backoff = DOWNLOAD_BACKOFF_BASE_SECS * (2 ** attempt)
                logger.warning(
                    "Descarga falló (intento %d/%d) %s: %s. Reintento en %.1fs",
                    attempt + 1, max_retries + 1, url, e, backoff,
                )
                time.sleep(backoff)
                continue
            break

    logger.error(
        "Falló descarga tras %d intentos: %s — último error: %s",
        max_retries + 1, url, last_err,
    )
    print(f"  ❌ Error descargando {url}: {last_err}", file=sys.stderr)
    return None


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

    # Guardar catálogo
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(laws, f, ensure_ascii=False, indent=2)
    print(f"💾 Catálogo guardado en {CATALOG_PATH}\n")

    if args.list:
        for law in laws:
            print(f"  {law['numero']:>3}  {law['nombre'][:80]}")
            print(f"       PDF: {law['pdf_filename']}  |  Reforma: {law['ultima_reforma']}")
        return

    # Descargar
    subset = laws[:args.limit] if args.limit > 0 else laws
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    catalog_dirty = False
    for i, law in enumerate(subset, 1):
        dest = output_dir / law["pdf_filename"]
        label = f"[{i}/{len(subset)}] {law['pdf_filename']}"

        if args.skip_existing and dest.exists():
            # Aun saltando la descarga, registramos el sha256 del PDF local para
            # preservar la procedencia (fix: antes el catálogo quedaba sin sha256
            # al re-correr con --skip-existing).
            law["sha256"] = _sha256_file(dest)
            catalog_dirty = True
            if args.verbose:
                print(f"  ⏭️  {label} (ya existe)")
            skipped += 1
            continue

        print(f"  ⬇️  {label}...", end="", flush=True)
        sha = download_pdf(law["pdf_url"], dest, verbose=False)
        if sha:
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f" ✅ ({size_mb:.1f} MB, sha256={sha[:12]}…)")
            law["sha256"] = sha
            catalog_dirty = True
            downloaded += 1
        else:
            failed += 1

        # Ser amable con el servidor
        time.sleep(BETWEEN_DOWNLOADS_SLEEP_SECS)

    # Si se descargó al menos un PDF, re-escribir el catálogo con los SHAs
    # anotados. Detecta reformas upstream comparando contra corridas previas.
    if catalog_dirty:
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(laws, f, ensure_ascii=False, indent=2)

    print(f"\n📊 Resultado: {downloaded} descargados, {skipped} omitidos, {failed} errores")
    print(f"📁 PDFs en: {output_dir}")


if __name__ == "__main__":
    main()
