#!/usr/bin/env python3
"""
pdf_to_md.py — Convierte PDFs de leyes mexicanas a Markdown estructurado.

Uso:
    python scripts/pdf_to_md.py origen-docs/LISR.pdf
    python scripts/pdf_to_md.py origen-docs/LISR.pdf --output leyes/LISR.md
    python scripts/pdf_to_md.py origen-docs/LISR.pdf --verbose
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("Error: pdfplumber no está instalado. Ejecuta: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Encabezados de página que se repiten en cada hoja y deben eliminarse
# ---------------------------------------------------------------------------
HEADER_SKIP = [
    "CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN",
    "Secretaría General",
    "Secretaría de Servicios Parlamentarios",
]

# Patrones de encabezado dinámicos (título de la ley + fecha de reforma)
HEADER_PATTERN_RE = re.compile(
    r'(LEY DEL|LEY FEDERAL|LEY GENERAL|CÓDIGO|REGLAMENTO).{0,80}(RENTA|VALOR|FEDERAL|GENERAL)',
    re.IGNORECASE,
)
REFORMA_RE = re.compile(r'(Última\s+Reforma\s+DOF|Reforma\s+publicada)', re.IGNORECASE)

# Título de la ley en ALL CAPS — se detecta dinámicamente y se usa para
# eliminar el running header que se repite en cada página del PDF.
_running_header: str = ""


def is_header_line(line: str) -> bool:
    """Devuelve True si la línea es un encabezado de página repetitivo."""
    stripped = line.strip()
    for h in HEADER_SKIP:
        if h in stripped:
            return True
    if HEADER_PATTERN_RE.search(stripped):
        return True
    if REFORMA_RE.search(stripped):
        return True
    # Running header dinámico (título de la ley en ALL CAPS)
    if _running_header and _running_header in stripped:
        return True
    return False


def build_page_marker_re(total_pages: int) -> re.Pattern:
    """Crea un regex para eliminar marcadores como '12 de 313'."""
    return re.compile(rf'\s*\d{{1,4}}\s+de\s+{total_pages}\s*')


def clean_page_markers(line: str, marker_re: re.Pattern) -> str:
    """Elimina marcadores de página embebidos en el texto."""
    return marker_re.sub(' ', line).strip()


def is_article_heading(line: str) -> bool:
    """Detecta líneas que abren un artículo: 'Artículo 5', 'Artículo 4-A', etc."""
    return bool(re.match(r'^Artículo\s+\d+', line.strip(), re.IGNORECASE))


def split_article_heading(line: str) -> tuple[str, str | None]:
    """
    Separa 'Artículo 5. Texto...' en ('Artículo 5', 'Texto...').
    Retorna (heading, cuerpo_o_None).
    """
    m = re.match(
        r'^(Artículo\s+\d[\w\-]*(?:\s+[A-ZÁÉÍÓÚÑ]{1,2}\.)?)\s*(.*)',
        line.strip(),
        re.IGNORECASE,
    )
    if m:
        heading = m.group(1).strip().rstrip('.')
        body = m.group(2).strip()
        return heading, body or None
    return line.strip(), None


# ---------------------------------------------------------------------------
# Ordinales en texto (para artículos de decreto y transitorios)
# ---------------------------------------------------------------------------
_ORDINALS = (
    r'(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SÉPTIMO|OCTAVO|NOVENO|'
    r'DÉCIMO(?:\s+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SÉPTIMO|OCTAVO|NOVENO))?|'
    r'VIGÉSIMO(?:\s+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SÉPTIMO|OCTAVO|NOVENO))?|'
    r'TRIGÉSIMO|ÚNICO)'
)
_ORDINALS_TC = (
    r'(?:Primero|Segundo|Tercero|Cuarto|Quinto|Sexto|Séptimo|Octavo|Noveno|'
    r'Décimo(?:\s+(?:Primero|Segundo|Tercero|Cuarto|Quinto|Sexto|Séptimo|Octavo|Noveno))?|'
    r'Vigésimo(?:\s+(?:Primero|Segundo|Tercero|Cuarto|Quinto|Sexto|Séptimo|Octavo|Noveno))?|'
    r'Trigésimo|Único|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SÉPTIMO|OCTAVO|NOVENO|'
    r'DÉCIMO(?:\s+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SÉPTIMO|OCTAVO|NOVENO))?|'
    r'VIGÉSIMO(?:\s+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SÉPTIMO|OCTAVO|NOVENO))?|'
    r'TRIGÉSIMO|ÚNICO)'
)

ARTICLE_ORDINAL_RE = re.compile(
    rf'^(ARTÍCULO\s+{_ORDINALS}(?:\s+A\s+ARTÍCULO\s+{_ORDINALS})?)\s*(.*)', re.IGNORECASE
)
TRANSITORIO_HEADING_RE = re.compile(r'^(Transitorios?)\b', re.IGNORECASE)
TRANSITORIO_ORDINAL_RE = re.compile(
    rf'^((?:Artículo\s+)?{_ORDINALS_TC})\.?-?\.?\s*(.*)', re.IGNORECASE
)


def is_section_heading(line: str) -> bool:
    """Detecta TÍTULO I, CAPÍTULO II, SECCIÓN III, etc. (sin IGNORECASE para evitar falsos positivos)."""
    return bool(
        re.match(r'^(TÍTULO|CAPÍTULO|SECCIÓN|Título|Capítulo|Sección)\s+[IVXLCDM\d]+', line.strip())
    )


# ---------------------------------------------------------------------------
# Extracción
# ---------------------------------------------------------------------------

def extract_lines(pdf_path: Path, verbose: bool = False) -> tuple[list[str], int]:
    """
    Extrae todas las líneas de texto del PDF, filtrando encabezados repetitivos
    y marcadores de página.

    Retorna (líneas_limpias, total_páginas).
    """
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        if verbose:
            print(f"📄 Total de páginas: {total}", flush=True)

        marker_re = build_page_marker_re(total)
        all_lines: list[str] = []

        for page_num, page in enumerate(pdf.pages):
            if verbose and page_num % 20 == 0:
                print(f"  Procesando página {page_num + 1}/{total}...", flush=True)

            text = page.extract_text(layout=False, x_tolerance=2, y_tolerance=2)
            if not text:
                continue

            for raw_line in text.split('\n'):
                line = clean_page_markers(raw_line.strip(), marker_re)
                if not line:
                    continue
                if is_header_line(line):
                    continue
                all_lines.append(line)

    return all_lines, total


def _detect_running_header(lines: list[str]) -> str:
    """
    Detecta el running header (título de la ley en ALL CAPS) que se repite
    en cada página del PDF.  Busca la cadena ALL CAPS más frecuente.
    """
    from collections import Counter
    candidates: Counter[str] = Counter()
    for line in lines:
        stripped = line.strip()
        # Los running headers son ALL CAPS, largos, y contienen el nombre de la ley
        if len(stripped) > 15 and stripped == stripped.upper() and re.search(r'[A-ZÁÉÍÓÚÑ]{4,}', stripped):
            # Normalizar espacios
            norm = ' '.join(stripped.split())
            candidates[norm] += 1
    if not candidates:
        return ""
    # El running header es la cadena ALL CAPS que más se repite
    most_common, count = candidates.most_common(1)[0]
    # Solo si aparece al menos 3 veces (varias páginas)
    if count >= 3:
        return most_common
    return ""


def _strip_running_header_inline(line: str, header: str) -> str:
    """Elimina el running header cuando aparece embebido dentro de un párrafo."""
    if not header or header not in line:
        return line
    return line.replace(header, ' ').strip()


# ---------------------------------------------------------------------------
# Formateo Markdown
# ---------------------------------------------------------------------------

def build_markdown(lines: list[str], meta_header: list[str]) -> list[str]:
    """
    Une líneas de continuación y aplica jerarquía Markdown:
      ##  → TÍTULO / CAPÍTULO / SECCIÓN / Transitorios
      ### → Artículo N / ARTÍCULO ORDINAL
    """
    # --- Detectar y limpiar running header ---
    global _running_header
    _running_header = _detect_running_header(lines)
    if _running_header:
        # Filtrar líneas que son solo el header, y limpiar inline
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            norm = ' '.join(stripped.split())
            if norm == _running_header:
                continue  # línea es solo el running header
            cleaned.append(_strip_running_header_inline(stripped, _running_header))
        lines = cleaned

    joined: list[str] = []
    buffer = ""
    in_transitorios = False  # rastrear si estamos en sección de transitorios

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if buffer:
                joined.append(buffer.strip())
                buffer = ""
            joined.append("")
            continue

        # --- Detectar "Transitorios" como heading ---
        tm = TRANSITORIO_HEADING_RE.match(stripped)
        if tm:
            if buffer:
                joined.append(buffer.strip())
                buffer = ""
            heading_text = tm.group(1)
            rest = stripped[tm.end():].strip()
            joined.append("")
            joined.append(f"## {heading_text}")
            joined.append("")
            in_transitorios = True
            if rest:
                # El resto puede empezar con un ordinal
                stripped = rest
                # fall through to ordinal check below
            else:
                continue

        # --- Detectar ARTÍCULO + ORDINAL como heading (decretos) ---
        am = ARTICLE_ORDINAL_RE.match(stripped)
        if am and stripped[:8].upper().startswith('ARTÍCULO'):
            if buffer:
                joined.append(buffer.strip())
                buffer = ""
            heading = am.group(1).strip().rstrip('.')
            body = am.group(2).strip().lstrip('.-').strip() if am.group(2) else None
            joined.append("")
            joined.append(f"### {heading}")
            if body:
                buffer = body
            continue

        # --- Artículo numérico ---
        if is_article_heading(stripped):
            if buffer:
                joined.append(buffer.strip())
                buffer = ""
            heading, body = split_article_heading(stripped)
            joined.append("")
            joined.append(f"### {heading}")
            in_transitorios = False
            if body:
                buffer = body
            continue

        # --- TÍTULO / CAPÍTULO / SECCIÓN ---
        if is_section_heading(stripped):
            if buffer:
                joined.append(buffer.strip())
                buffer = ""
            joined.append("")
            joined.append(f"## {stripped}")
            continue

        # --- Ordinales en transitorios: poner en negritas ---
        if in_transitorios:
            om = TRANSITORIO_ORDINAL_RE.match(stripped)
            if om:
                if buffer:
                    joined.append(buffer.strip())
                    buffer = ""
                ordinal = om.group(1).strip().rstrip('.')
                rest = om.group(2).strip().lstrip('.-').strip()
                # Separador original (.- o .)
                sep = '.-' if '.-' in stripped[:len(om.group(1))+3] else '.'
                formatted = f"**{ordinal}{sep}** {rest}" if rest else f"**{ordinal}{sep}**"
                buffer = formatted
                continue

        # Unión de líneas: guión al final → unir directamente
        if buffer.endswith('-'):
            buffer = buffer[:-1] + stripped
        # Fin de oración → nuevo párrafo
        elif buffer and buffer[-1] in '.;:' and stripped[0].isupper():
            joined.append(buffer.strip())
            buffer = stripped
        else:
            buffer = (buffer + " " + stripped).strip() if buffer else stripped

    if buffer:
        joined.append(buffer.strip())

    return meta_header + joined


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convierte un PDF de ley mexicana a Markdown estructurado.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("pdf", type=Path, help="Ruta al archivo PDF fuente.")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Ruta de salida del .md (default: leyes/<nombre>.md).",
    )
    parser.add_argument(
        "--title", "-t",
        type=str,
        default=None,
        help='Título para el H1 del Markdown (default: nombre del archivo).',
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Muestra progreso página a página.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    pdf_path: Path = args.pdf.resolve()
    if not pdf_path.exists():
        print(f"Error: no se encontró el archivo '{pdf_path}'", file=sys.stderr)
        sys.exit(1)

    # Output por defecto: markdown/<nombre>.md
    if args.output is None:
        output_path = Path(__file__).parent.parent / "markdown" / (pdf_path.stem + ".md")
    else:
        output_path = args.output.resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    title = args.title or pdf_path.stem.replace("_", " ").replace("-", " ")

    print(f"Extrayendo texto de: {pdf_path.name}", flush=True)
    lines, _ = extract_lines(pdf_path, verbose=args.verbose)

    meta_header = [
        f"# {title}",
        "",
        "> Documento generado automáticamente a partir del PDF oficial.",
        "> Fuente: Cámara de Diputados del H. Congreso de la Unión — [diputados.gob.mx](https://www.diputados.gob.mx)",
        "",
        "---",
        "",
    ]

    print("Estructurando Markdown...", flush=True)
    md_lines = build_markdown(lines, meta_header)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))

    print(f"✅ Listo → {output_path}")
    print(f"   Líneas totales: {len(md_lines)}")


if __name__ == "__main__":
    main()
