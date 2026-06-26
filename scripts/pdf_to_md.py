#!/usr/bin/env python3
"""
pdf_to_md.py — Convierte PDFs de leyes mexicanas a Markdown estructurado.

Uso:
    python scripts/pdf_to_md.py origen-docs/LISR.pdf
    python scripts/pdf_to_md.py origen-docs/LISR.pdf --output leyes/LISR.md
    python scripts/pdf_to_md.py origen-docs/LISR.pdf --verbose
"""

import argparse
import json
import logging
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _log import get_logger
from constants import (
    DESCRIPTIVE_NAME_MAX_LENGTH,
    DESCRIPTIVE_NAME_TITLE_CASE_MAX_LENGTH,
    IMAGE_TABLE_MIN_HEIGHT,
    IMAGE_TABLE_MIN_WIDTH,
    NUMERIC_ROW_FRACTION,
    NUMERIC_ROW_MIN,
    OCR_HEADER_MIN_LETTERS,
    OCR_LANG,
    OCR_MIN_CONFIDENCE,
    OCR_PSM_CONFIG,
    OCR_RESOLUTION_DPI,
    OCR_ROW_TOLERANCE,
    OCR_TABLE_MAX_COLS,
    OCR_TABLE_MIN_DATA_ROWS,
    PDFPLUMBER_X_TOLERANCE,
    PDFPLUMBER_Y_TOLERANCE,
    PROGRESS_LOG_INTERVAL,
    RUNNING_HEADER_MIN_LENGTH,
    RUNNING_HEADER_MIN_REPETITIONS,
    TITLE_HEADER_GAP_RATIO,
    VECTOR_TABLE_MIN_COLS,
    VECTOR_TABLE_MIN_ROWS,
)
from md_render import (  # noqa: F401  # re-exportado (fachada): tests usan pdf_to_md.render_markdown
    _render_content,
    _render_node,
    _render_table,
    render_markdown,
)

logger = get_logger(__name__)

try:
    import pdfplumber
except ImportError:
    print("Error: pdfplumber no está instalado. Ejecuta: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)

# OCR opcional para tablas-imagen
_HAS_OCR = False
try:
    import pytesseract
    from PIL import (
        Image,  # noqa: F401  # Verifica que Pillow esté instalado (requerido por pytesseract)
    )
    _HAS_OCR = True
except ImportError:
    pass


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
    """Detecta líneas que abren un artículo: 'Artículo 5', 'Artículo 4-A', etc.
    Solo reconoce 'Artículo' con A mayúscula para evitar falsos positivos
    de referencias mid-sentence como 'el artículo 96 de esta Ley'."""
    return bool(re.match(r'^Artículo\s+\d+', line.strip()))


def split_article_heading(line: str) -> tuple[str, str | None]:
    """
    Separa 'Artículo 5. Texto...' en ('Artículo 5', 'Texto...').
    Retorna (heading, cuerpo_o_None).
    """
    m = re.match(
        r'^(Artículo\s+\d[\w\-]*(?:\s+[A-ZÁÉÍÓÚÑ]{1,2}\.)?)\s*(.*)',
        line.strip(),
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
    rf'^((?:ARTÍCULO|Artículo)\s+{_ORDINALS_TC}(?:\s+[Aa]\s+(?:ARTÍCULO|Artículo)\s+{_ORDINALS_TC})?)\s*(.*)'
)
TRANSITORIO_HEADING_RE = re.compile(r'^(Transitorios?)\b', re.IGNORECASE)
TRANSITORIO_ORDINAL_RE = re.compile(
    rf'^((?:Artículo\s+)?{_ORDINALS_TC})\.?-?\.?\s*(.*)', re.IGNORECASE
)

# Fracciones con numerales romanos: I., II., XVI., XXIX., etc.
FRACCION_ROMAN_RE = re.compile(r'^([IVXL]{1,7})\.\s')

# Incisos: a), b), c), etc.
INCISO_RE = re.compile(r'^[a-z]\)\s')

# Preposiciones/artículos que al final del buffer indican que el siguiente
# "Artículo N" es una referencia mid-sentence, no un heading real.
_ARTICLE_REF_TRAILING_RE = re.compile(
    r'\b(?:el|del|al|los|las|un|una|dicho|mismo|citado|referido|'
    r'previsto|señalado|establecido|dispuesto|contenido|mencionado|'
    r'indicado|en|conforme|según)\s*$',
    re.IGNORECASE,
)

# Patrones usados dentro de loops calientes (extracción OCR / detección de
# headers): pre-compilados a nivel módulo para evitar recompilarlos en cada
# fila/línea/página de un PDF largo.
_OCR_NUM_RE = re.compile(r'^[\d$%,.]+%?$')
_OCR_UNIT_RE = re.compile(r'^[\$%#€£¥]+$')
_INCISO_INLINE_SPLIT_RE = re.compile(r'(?<=[\.:])\s+(?=[a-z]\)\s)')
_RUNNING_HEADER_LETTERS_RE = re.compile(r'[A-ZÁÉÍÓÚÑ]{4,}')


def _is_roman_numeral(s: str) -> bool:
    """Verifica si una cadena es un numeral romano válido (I-L)."""
    return len(s) > 0 and bool(re.fullmatch(r'(?:XL|L?X{0,3})(?:IX|IV|V?I{0,3})', s))


# Regex para headings de sección: keyword + numeral/ordinal, captura heading y resto
_SECTION_ORD = (
    r'(?:PRIMER|SEGUND|TERCER|CUART|QUINT|SEXT|SÉPTIM|OCTAV|NOVEN|DÉCIM|ÚNIC)[OA]'
    r'|(?:Primer|Segund|Tercer|Cuart|Quint|Sext|Séptim|Octav|Noven|Décim|Únic)[oa]'
)
_SECTION_NUM = r'[IVXLCDM\d]+(?:\s+(?:BIS|Bis|TER|Ter|QUÁTER|Quáter|QUINQUIES|Quinquies))?'

SECTION_HEADING_RE = re.compile(
    r'^((?:TÍTULO|CAPÍTULO|SECCIÓN|Título|Capítulo|Sección)\s+'
    rf'(?:{_SECTION_ORD}|{_SECTION_NUM}))'
    r'\s*(.*)'
)

_SECTION_BODY_RE = re.compile(
    r'^[,.\s]*(?:de|del|y |o |en |a |que |según|no |se |la |el |las |los |al |con |por |sin |ni |para '
    r'|sección|secciones|capítulo|título)',
    re.IGNORECASE,
)


def _match_section_heading(line: str) -> re.Match | None:
    """Detecta TÍTULO I, CAPÍTULO II, Capítulo Único, SECCIÓN CUARTA, etc.
    Rechaza falsos positivos como 'Sección II de este Capítulo.' (texto de cuerpo)."""
    m = SECTION_HEADING_RE.match(line.strip())
    if not m:
        return None
    rest = m.group(2).strip()
    if not rest:
        return m
    if _SECTION_BODY_RE.match(rest):
        return None
    return m


def is_section_heading(line: str) -> bool:
    """Wrapper booleano para compatibilidad."""
    return _match_section_heading(line) is not None


def _is_descriptive_name(line: str) -> bool:
    """Detecta nombres descriptivos de sección: 'DISPOSICIONES GENERALES', 'De la Violencia Familiar'."""
    s = line.strip()
    if not s or len(s) > DESCRIPTIVE_NAME_MAX_LENGTH:
        return False
    if re.match(r'^\d', s):
        return False
    if is_article_heading(s) or is_section_heading(s):
        return False
    if ARTICLE_ORDINAL_RE.match(s):
        return False
    if TRANSITORIO_HEADING_RE.match(s):
        return False
    rm = FRACCION_ROMAN_RE.match(s)
    if rm and _is_roman_numeral(rm.group(1)):
        return False
    # ALL CAPS con al menos una palabra de ≥3 letras
    if s == s.upper() and re.search(r'[A-ZÁÉÍÓÚÑ]{3,}', s):
        return True
    # Title Case con prefijo descriptivo
    if re.match(r'^(?:De |Del |Sobre |Para |En |Por |Disposiciones )', s) and len(s) < DESCRIPTIVE_NAME_TITLE_CASE_MAX_LENGTH:
        return True
    return False


# ---------------------------------------------------------------------------
# Extracción
# ---------------------------------------------------------------------------

# Marcador interno que precede a las líneas `| ... |` de una tabla y
# transporta su procedencia hasta build_ast: método de extracción
# ('text' = tabla vectorial nativa del PDF, 'ocr' = Tesseract) y página
# de origen (1-indexed). build_ast lo consume y lo descarta del stream —
# nunca llega al Markdown final ni al JSON como texto.
_TABLE_META_RE = re.compile(r'^<!--mxmd:table src=(text|ocr) page=(\d+)-->$')

# Caracteres Unicode de área privada (U+E000-U+F8FF): los PDFs de la Cámara
# los usan para bullets de fuentes embebidas (Wingdings/Symbol). Sin la
# fuente original son ilegibles; se sustituyen por un guion.
_PRIVATE_USE_RE = re.compile('[\ue000-\uf8ff]')


def _clean_cell(cell: Any) -> str:
    """Colapsa una celda de pdfplumber a una sola línea.

    None → '' (pdfplumber usa None para celdas vacías y celdas fusionadas);
    saltos de línea y espacios múltiples → un espacio (headers multi-línea);
    '|' → '/' (un pipe literal dentro de la celda rompería la fila markdown);
    chars de área privada (bullets de fuentes embebidas) → '-'.
    """
    if cell is None:
        return ""
    text = _PRIVATE_USE_RE.sub("-", str(cell).replace("|", "/"))
    return " ".join(text.split())


def _is_valid_vector_table(data: list[list[Any]]) -> bool:
    """Filtro de validez para tablas vectoriales de `find_tables()`.

    Descarta detecciones que no son tablas reales:
    - menos de `VECTOR_TABLE_MIN_COLS` columnas (layouts de dos columnas
      o listas largas que pdfplumber confunde con tabla N×1),
    - tablas sin contenido (todas las celdas vacías).

    Las tablas de UNA fila se aceptan solo si la fila tiene al menos
    `VECTOR_TABLE_MIN_COLS` celdas con contenido: los PDFs de la Cámara
    dibujan filas de datos como tablas independientes de una fila (las
    tablas de valuación de la LFT, 18 casos); descartarlas las aplana a
    texto con los valores inyectados a mitad de oración. Un recuadro
    decorativo (1×N con una sola celda llena) sigue rechazado.
    """
    if not data:
        return False
    if len(data) < VECTOR_TABLE_MIN_ROWS:
        return sum(1 for c in data[0] if _clean_cell(c)) >= VECTOR_TABLE_MIN_COLS
    if max(len(row) for row in data) < VECTOR_TABLE_MIN_COLS:
        return False
    return any(_clean_cell(c) for row in data for c in row)


def _route_page(has_large_imgs: bool, n_vector_tables: int) -> str:
    """Decide el flujo de extracción de una página: 'ocr' | 'vector' | 'text'.

    Precedencia: las tablas vectoriales *válidas* ganan sobre el OCR —
    si pdfplumber puede leer las celdas nativamente, el OCR solo
    degradaría. El OCR aplica cuando hay imagen grande y NINGUNA tabla
    vectorial válida; las detecciones inválidas (N×1, vacías) no cuentan
    como tabla y por tanto no suprimen el OCR (una página con
    imagen-tabla + falso positivo N×1 debe seguir yendo a OCR, no
    aplanarse como texto).
    """
    if n_vector_tables:
        return "vector"
    if has_large_imgs:
        return "ocr"
    return "text"


def _render_vector_table(data: list[list[Any]], page_num: int) -> list[str]:
    """Emite una tabla vectorial como líneas markdown `| ... |` compatibles
    con `_parse_table_lines`, precedidas del marcador de procedencia que
    `build_ast` consume (source_method='text', source_page=page_num).

    La primera fila se trata como encabezados; filas más cortas que la
    más ancha se rellenan con celdas vacías para mantener la rejilla.
    Normalizaciones sobre la rejilla:
    - columnas 100 % vacías (artefacto de detección de find_tables, p.ej.
      LIGIE p.881 con 9 columnas sobre 5 reales) se colapsan, siempre que
      queden al menos `VECTOR_TABLE_MIN_COLS`;
    - filas de datos 100 % vacías (espaciado visual de la rejilla) se
      omiten;
    - una tabla de UNA fila (fila de datos dibujada como tabla propia,
      sin header en el PDF) se emite con encabezados vacíos y la fila
      como dato — no al revés.
    """
    n_cols = max(len(row) for row in data)
    grid = [
        [_clean_cell(c) for c in row] + [''] * (n_cols - len(row))
        for row in data
    ]

    keep = [c for c in range(n_cols) if any(row[c] for row in grid)]
    if VECTOR_TABLE_MIN_COLS <= len(keep) < n_cols:
        grid = [[row[c] for c in keep] for row in grid]
        n_cols = len(keep)

    if len(grid) == 1:
        headers: list[str] = [''] * n_cols
        body = grid
    else:
        headers = grid[0]
        body = [row for row in grid[1:] if any(row)]

    md: list[str] = ['', f'<!--mxmd:table src=text page={page_num}-->']
    md.append('| ' + ' | '.join(headers) + ' |')
    md.append('| ' + ' | '.join(['---'] * n_cols) + ' |')
    for row in body:
        md.append('| ' + ' | '.join(row) + ' |')
    md.append('')
    return md


def _extract_region_lines(page: Any, y0: float, y1: float,
                          marker_re: re.Pattern, page_num: int,
                          context: str) -> list[str]:
    """Extrae texto de la franja vertical [y0, y1) de una página, limpiando
    marcadores de página y encabezados repetitivos.

    Es el paso común de los flujos que intercalan tablas (imagen u
    vectoriales) con el texto circundante. Coordenadas degeneradas se
    loggean en debug y devuelven lista vacía (esperable en bordes).
    """
    lines: list[str] = []
    try:
        region = page.crop((0, y0, page.width, y1))
        text = region.extract_text(
            layout=False,
            x_tolerance=PDFPLUMBER_X_TOLERANCE,
            y_tolerance=PDFPLUMBER_Y_TOLERANCE,
        )
    except (ValueError, AttributeError) as e:
        logger.debug("crop %s falló (page=%d, y0=%s, y1=%s): %s",
                     context, page_num, y0, y1, e)
        return lines
    except Exception:
        logger.exception("error inesperado extrayendo texto (%s) en página %d",
                         context, page_num)
        return lines
    if not text:
        return lines
    for raw_line in text.split('\n'):
        line = clean_page_markers(raw_line.strip(), marker_re)
        if not line:
            continue
        if is_header_line(line):
            continue
        lines.append(line)
    return lines


def extract_lines(pdf_path: Path) -> tuple[list[str], int]:
    """
    Extrae todas las líneas de texto del PDF, filtrando encabezados repetitivos
    y marcadores de página.

    Retorna (líneas_limpias, total_páginas).
    """
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        logger.info("Total de páginas: %d", total)

        marker_re = build_page_marker_re(total)
        all_lines: list[str] = []

        for page_num, page in enumerate(pdf.pages):
            if page_num % PROGRESS_LOG_INTERVAL == 0:
                logger.debug("Procesando página %d/%d", page_num + 1, total)

            # --- Detectar tablas-imagen para intercalar OCR en posición correcta ---
            large_imgs = [img for img in (page.images or [])
                          if abs(img.get('x1', 0) - img.get('x0', 0)) > IMAGE_TABLE_MIN_WIDTH
                          and abs(img.get('y1', 0) - img.get('y0', 0)) > IMAGE_TABLE_MIN_HEIGHT]

            # --- Detectar tablas vectoriales (celdas dibujadas como vectores
            # PDF, sin imagen embebida). find_tables() expone bbox + contenido;
            # el filtro de validez descarta los falsos positivos N×1. ---
            found_tables = page.find_tables()
            vector_tables = []
            for t in found_tables:
                data = t.extract()
                if _is_valid_vector_table(data):
                    vector_tables.append((t.bbox, data))

            route = _route_page(bool(large_imgs), len(vector_tables))

            if route == "ocr":
                # Página con tablas-imagen: extraer texto por regiones verticales
                # para insertar la tabla OCR en su posición correcta.
                # Ordenar imágenes por posición vertical (top). Solo coords
                # top-down ('top'/'bottom'): mezclarlas con 'y0'/'y1'
                # (bottom-up) producía bboxes espejados que tragaban texto
                # del cuerpo (auditoría OCR 2026-06-11, CR-1).
                sorted_imgs = sorted(large_imgs, key=lambda im: im.get('top', 0))
                cursor_y: float = 0
                for img in sorted_imgs:
                    img_top = img.get('top', 0)
                    img_bottom = img.get('bottom', page.height)

                    # Texto ANTES de la imagen (región superior de la página)
                    if img_top > cursor_y + 1:
                        all_lines.extend(_extract_region_lines(
                            page, cursor_y, img_top, marker_re, page_num + 1,
                            "sobre tabla-imagen"))

                    # OCR de la imagen (tabla)
                    ocr_result = _ocr_page_table(page, [img], page_num + 1)
                    all_lines.extend(ocr_result)

                    cursor_y = img_bottom

                # Texto DESPUÉS de la última imagen
                if cursor_y < page.height - 1:
                    all_lines.extend(_extract_region_lines(
                        page, cursor_y, page.height, marker_re, page_num + 1,
                        "bajo tabla-imagen"))
            elif route == "vector":
                # Página con tablas vectoriales: texto por franjas verticales
                # complementarias a los bboxes, intercalando cada tabla como
                # markdown en su posición (mismo ordenamiento por top que el
                # flujo de tablas-imagen).
                cursor_y = 0
                for bbox, data in sorted(vector_tables, key=lambda vt: vt[0][1]):
                    table_top, table_bottom = bbox[1], bbox[3]
                    if table_top > cursor_y + 1:
                        all_lines.extend(_extract_region_lines(
                            page, cursor_y, table_top, marker_re, page_num + 1,
                            "sobre tabla vectorial"))
                    all_lines.extend(_render_vector_table(data, page_num + 1))
                    cursor_y = max(cursor_y, table_bottom)
                if cursor_y < page.height - 1:
                    all_lines.extend(_extract_region_lines(
                        page, cursor_y, page.height, marker_re, page_num + 1,
                        "bajo tabla vectorial"))
            else:
                # Página sin tablas: extracción normal
                text = page.extract_text(
                    layout=False,
                    x_tolerance=PDFPLUMBER_X_TOLERANCE,
                    y_tolerance=PDFPLUMBER_Y_TOLERANCE,
                )
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


def _ocr_page_table(page: Any, large_imgs: list, page_num: int) -> list[str]:
    """Extrae tablas-imagen de una página usando OCR (Tesseract).
    Usa image_to_data para obtener posiciones espaciales y reconstruir la tabla."""
    if not _HAS_OCR:
        return [f"> **[Tabla no extraíble — ver PDF original, página {page_num}]**"]

    result_lines: list[str] = []
    for img in large_imgs:
        # Solo coordenadas top-down ('top'/'bottom'): mezclarlas con
        # 'y0'/'y1' (bottom-up) producía un crop espejado verticalmente
        # que OCR-eaba párrafos del cuerpo recortados al ancho de la
        # imagen (auditoría OCR 2026-06-11, CR-1).
        x0 = img.get('x0', 0)
        top = img.get('top', 0)
        x1 = img.get('x1', page.width)
        bottom = img.get('bottom', page.height)
        try:
            cropped = page.crop((x0, top, x1, bottom))
            pil_img = cropped.to_image(resolution=OCR_RESOLUTION_DPI).original
            # Obtener datos espaciales con --psm 6 (bloque de texto uniforme)
            data = pytesseract.image_to_data(
                pil_img, lang=OCR_LANG, config=OCR_PSM_CONFIG,
                output_type=pytesseract.Output.DICT,
            )
            md_table = _build_table_from_spatial(data, page_num)
            if not md_table:
                result_lines.append(f"> **[Tabla no extraíble — ver PDF original, página {page_num}]**")
                continue
            n = sum(1 for line in md_table if line.startswith('|'))
            logger.info("OCR tabla página %d: %d filas", page_num, n)
            result_lines.extend(md_table)
        except pytesseract.TesseractNotFoundError:
            logger.error(
                "Tesseract no encontrado. Instala con: brew install tesseract / apt install tesseract-ocr",
            )
            result_lines.append(f"> **[Tabla no extraíble — ver PDF original, página {page_num}]**")
        except (pytesseract.TesseractError, OSError, ValueError):
            logger.warning("OCR falló en página %d", page_num, exc_info=True)
            result_lines.append(f"> **[Tabla no extraíble — ver PDF original, página {page_num}]**")
        except Exception:
            logger.exception("error OCR inesperado en página %d", page_num)
            result_lines.append(f"> **[Tabla no extraíble — ver PDF original, página {page_num}]**")
    return result_lines


def _ocr_rows_as_text(rows: list[list[dict]]) -> list[str]:
    """Vuelca filas de palabras OCR como líneas de texto plano, sanitizadas.

    Los pipes que Tesseract lee de los bordes de celda se eliminan: una
    línea de texto plano que empiece con '|' haría que build_ast la
    confundiera con fila de tabla y fabricara pseudo-tablas a partir de
    ruido OCR (auditoría 2026-06-11, CR-6: las 11 tablas fantasma de
    LISSSTE nacieron así).
    """
    lines: list[str] = []
    for row in rows:
        text = ' '.join(w['text'] for w in row).replace('|', ' ')
        text = ' '.join(text.split())
        if text:
            lines.append(text)
    return lines


def _build_table_from_spatial(data: dict, page_num: int) -> list[str]:
    """Reconstruye una tabla markdown a partir de datos espaciales de Tesseract.
    Agrupa palabras por fila (y-position) y columna (x-position).

    Si la reconstrucción no supera la guardia de plausibilidad (mínimo de
    filas de datos, máximo de columnas), emite el marcador honesto
    "[Tabla no extraíble]" seguido del texto OCR plano, en lugar de datos
    corruptos con apariencia de válidos.
    """
    from collections import defaultdict

    # Extraer palabras con posición y confianza mínima
    words = []
    for i in range(len(data['text'])):
        txt = (data['text'][i] or '').strip()
        if not txt or data['conf'][i] < OCR_MIN_CONFIDENCE:
            continue
        words.append({
            'text': txt,
            'left': data['left'][i],
            'top': data['top'][i],
            'width': data['width'][i],
            'height': data['height'][i],
        })

    if not words:
        return []

    # --- Paso 1: agrupar palabras en filas por y-center ---
    rows_map: dict[int, list[dict]] = {}
    for w in words:
        y_center = w['top'] + w['height'] // 2
        assigned = False
        for key in rows_map:
            if abs(y_center - key) <= OCR_ROW_TOLERANCE:
                rows_map[key].append(w)
                assigned = True
                break
        if not assigned:
            rows_map[y_center] = [w]

    # Ordenar filas por posición vertical, palabras por posición horizontal
    sorted_rows = []
    for key in sorted(rows_map):
        row_words = sorted(rows_map[key], key=lambda w: w['left'])
        sorted_rows.append(row_words)

    if not sorted_rows:
        return []

    # --- Paso 2: detectar columnas a partir de los datos numéricos ---
    # Las filas de datos numéricos son las que mejor definen las columnas.
    # Detectar filas numéricas (regex pre-compilado: _OCR_NUM_RE).
    numeric_rows = []
    for row in sorted_rows:
        num_count = sum(1 for w in row if _OCR_NUM_RE.match(w['text']))
        if num_count >= max(len(row) * NUMERIC_ROW_FRACTION, NUMERIC_ROW_MIN):
            numeric_rows.append(row)

    if not numeric_rows:
        # Sin filas numéricas → emitir texto plano (sanitizado)
        return ['', *_ocr_rows_as_text(sorted_rows), '']

    # Encontrar el número de columnas más frecuente en filas numéricas
    from collections import Counter
    col_counts = Counter(len(r) for r in numeric_rows)
    target_cols = col_counts.most_common(1)[0][0]

    # Calcular posiciones x centrales de cada columna usando las filas numéricas
    col_positions: list[float] = []
    matching_rows = [r for r in numeric_rows if len(r) == target_cols]
    if matching_rows:
        for col_idx in range(target_cols):
            centers = [r[col_idx]['left'] + r[col_idx]['width'] / 2
                       for r in matching_rows if col_idx < len(r)]
            if centers:
                col_positions.append(sum(centers) / len(centers))

    # --- Paso 3: asignar cada palabra de cada fila a una columna ---
    # Calcular boundaries entre columnas (punto medio entre centros adyacentes)
    col_boundaries: list[float] = []
    for i in range(len(col_positions) - 1):
        col_boundaries.append((col_positions[i] + col_positions[i + 1]) / 2)

    def assign_to_columns(row_words: list[dict]) -> list[str]:
        """Asigna palabras a columnas usando boundaries entre centros."""
        if not col_positions:
            return [w['text'] for w in row_words]
        cols: dict[int, list[str]] = defaultdict(list)
        for w in row_words:
            w_center = w['left'] + w['width'] / 2
            # Avanzar con boundaries: si el centro de la palabra supera el boundary, siguiente columna
            col = 0
            for b in col_boundaries:
                if w_center > b:
                    col += 1
                else:
                    break
            cols[col].append(w['text'])
        # '|' dentro de una celda (bordes de rejilla que Tesseract lee como
        # texto) rompería la fila markdown → '/'
        return [' '.join(cols.get(c, [''])).replace('|', '/')
                for c in range(target_cols)]

    # --- Paso 4: separar título, encabezados de columna, filas de datos, texto posterior ---
    # Encontrar el índice de la primera fila numérica
    first_num_idx = None
    for i, row in enumerate(sorted_rows):
        num_count = sum(1 for w in row if _OCR_NUM_RE.match(w['text']))
        if num_count >= max(len(row) * NUMERIC_ROW_FRACTION, NUMERIC_ROW_MIN):
            first_num_idx = i
            break

    if first_num_idx is None:
        # Sin filas numéricas → texto plano (no debería llegar aquí)
        return ['', *_ocr_rows_as_text(sorted_rows), '']

    # Clasificar filas pre-tabla: título vs encabezados de columna.
    # Heurística: encontrar el mayor salto vertical (gap) entre filas pre-tabla.
    # Todo lo que está por encima del mayor gap es título; por debajo es header.
    pre_rows = sorted_rows[:first_num_idx]
    title_rows: list[list[dict]] = []
    header_rows: list[list[dict]] = []

    if len(pre_rows) <= 1:
        # 0-1 filas pre-tabla: no hay separación título/encabezado posible
        title_rows = pre_rows
    elif col_positions:
        # Calcular y-center de cada fila pre-tabla
        def _row_y(row: list[dict]) -> float:
            return sum(w['top'] + w['height'] / 2 for w in row) / len(row)
        pre_ys = [_row_y(r) for r in pre_rows]
        # Encontrar el mayor salto vertical (gap) entre filas pre-tabla
        max_gap = 0.0
        split_idx = 0  # índice de corte: [0..split_idx) = título, [split_idx..] = encabezado
        for i in range(1, len(pre_ys)):
            gap = pre_ys[i] - pre_ys[i - 1]
            if gap > max_gap:
                max_gap = gap
                split_idx = i
        # Solo separar si el gap es significativo (>150% del gap promedio)
        avg_gap = (pre_ys[-1] - pre_ys[0]) / max(len(pre_ys) - 1, 1)
        if max_gap > avg_gap * TITLE_HEADER_GAP_RATIO and split_idx > 0:
            title_rows = pre_rows[:split_idx]
            header_rows = pre_rows[split_idx:]
        else:
            # Gap uniforme → todo es header (no hay título)
            header_rows = pre_rows
    else:
        title_rows = pre_rows

    # Reconstruir encabezados de columna: asignar cada fila de encabezado a columnas
    # y fusionar verticalmente (encabezados multi-línea)
    col_headers: list[list[str]] = [[] for _ in range(target_cols)]

    def _assign_header_row(row: list[dict]) -> list[str]:
        """Asigna una fila de header a columnas.
        Si todas las palabras caen en una zona reducida (1-2 columnas adyacentes)
        y ninguna en las primeras columnas, unir todo en una sola columna.
        Se asigna a max_col (la columna más a la derecha) porque los headers
        anchos de la última columna suelen extenderse hacia la izquierda."""
        base = assign_to_columns(row)
        if len(row) >= 2 and col_boundaries:
            word_cols = []
            for w in row:
                wc = w['left'] + w['width'] / 2
                c = 0
                for b in col_boundaries:
                    if wc > b:
                        c += 1
                    else:
                        break
                word_cols.append(c)
            occupied = set(word_cols)
            if len(occupied) <= 2:
                min_col = min(occupied)
                max_col = max(occupied)
                if max_col - min_col <= 1 and min_col > 0:
                    # Ninguna palabra en columnas anteriores a min_col: texto del encabezado derecho
                    min_x = min(w['left'] for w in row)
                    left_boundary = col_boundaries[min_col - 1]
                    if min_x > left_boundary:
                        merged = ['' for _ in range(target_cols)]
                        merged[max_col] = ' '.join(w['text'] for w in row)
                        return merged
        return base

    for row in header_rows:
        # Filtrar filas de ruido OCR: requiere al menos una palabra "real"
        has_real_word = any(
            sum(c.isalpha() for c in w['text']) >= OCR_HEADER_MIN_LETTERS for w in row
        )
        if not has_real_word:
            continue
        assigned_row = _assign_header_row(row)
        for c in range(target_cols):
            val = assigned_row[c].strip() if c < len(assigned_row) else ''
            if val and val not in (',', '.', '-'):
                col_headers[c].append(val)

    # Construir nombres de columna finales a partir de los fragmentos recopilados
    header_names = [' '.join(parts) if parts else f'Col {c+1}'
                    for c, parts in enumerate(col_headers)]

    # Detectar si la primera fila numérica es una fila de unidades (ej. $ $ $ %)
    # y si es así, incorporarla a los encabezados
    data_start_idx = first_num_idx
    first_data_row = sorted_rows[first_num_idx]
    first_row_vals = assign_to_columns(first_data_row)
    if all(_OCR_UNIT_RE.match(v.strip()) for v in first_row_vals if v.strip()):
        # Fila de unidades detectada → incorporar al nombre de columna
        for c, val in enumerate(first_row_vals):
            unit = val.strip()
            if unit and c < len(header_names):
                header_names[c] = f'{header_names[c]} ({unit})' if header_names[c] != f'Col {c+1}' else unit
        data_start_idx = first_num_idx + 1

    # Clasificar filas de datos vs texto posterior
    data_rows: list[list[str]] = []
    post_rows: list[list[dict]] = []
    for row in sorted_rows[data_start_idx:]:
        num_count = sum(1 for w in row if _OCR_NUM_RE.match(w['text']))
        is_numeric = num_count >= max(len(row) * NUMERIC_ROW_FRACTION, NUMERIC_ROW_MIN)
        if is_numeric and not post_rows:
            data_rows.append(assign_to_columns(row))
        else:
            post_rows.append(row)

    # Guardia de plausibilidad (auditoría OCR 2026-06-11): muy pocas filas
    # de datos o demasiadas columnas = la reconstrucción machacó la tabla
    # (filas reales convertidas en headers, columnas fantasma por conteo
    # de palabras). Marcador honesto + texto plano > basura estructurada.
    if (len(data_rows) < OCR_TABLE_MIN_DATA_ROWS
            or target_cols > OCR_TABLE_MAX_COLS):
        return [
            '',
            f'> **[Tabla no extraíble — ver PDF original, página {page_num}]**',
            '',
            *_ocr_rows_as_text(sorted_rows),
            '',
        ]

    # Emitir Markdown
    md: list[str] = ['']

    # Título (texto previo que no alinea con columnas); sanitizar pipes
    # para que build_ast no lo confunda con fila de tabla
    for row in title_rows:
        text = ' '.join(' '.join(w['text'] for w in row).replace('|', ' ').split())
        if not text:
            continue
        md.append(f'**{text}**' if text == text.upper() and len(text) > 3 else text)

    # Marcador de procedencia (source_method='ocr', source_page) + tabla
    md.append(f'<!--mxmd:table src=ocr page={page_num}-->')
    md.append('| ' + ' | '.join(h.replace('|', '/') for h in header_names) + ' |')
    md.append('| ' + ' | '.join(['---'] * target_cols) + ' |')
    for cols in data_rows:
        md.append('| ' + ' | '.join(cols) + ' |')

    post_text = _ocr_rows_as_text(post_rows)
    if post_text:
        md.append('')
        md.extend(post_text)

    md.append('')
    return md


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
        if (
            len(stripped) > RUNNING_HEADER_MIN_LENGTH
            and stripped == stripped.upper()
            and _RUNNING_HEADER_LETTERS_RE.search(stripped)
        ):
            # Normalizar espacios múltiples
            norm = ' '.join(stripped.split())
            candidates[norm] += 1
    if not candidates:
        return ""
    # El running header es la cadena ALL CAPS que más se repite
    most_common, count = candidates.most_common(1)[0]
    # Solo si aparece en suficientes páginas
    if count >= RUNNING_HEADER_MIN_REPETITIONS:
        return most_common
    return ""


def _strip_running_header_inline(line: str, header: str) -> str:
    """Elimina el running header cuando aparece embebido dentro de un párrafo."""
    if not header or header not in line:
        return line
    return line.replace(header, ' ').strip()


def _post_split_incisos(lines: list[str]) -> list[str]:
    """Separa incisos a), b), c) que quedaron inline después de la unión de párrafos."""
    result: list[str] = []
    for line in lines:
        if not line or line.startswith('#') or line.startswith('>') or line.startswith('---') or line.startswith('**'):
            result.append(line)
            continue
        parts = _INCISO_INLINE_SPLIT_RE.split(line)
        if len(parts) > 1:
            for i, part in enumerate(parts):
                result.append(part.strip())
                if i < len(parts) - 1:
                    result.append("")
        else:
            result.append(line)
    return result


# ---------------------------------------------------------------------------
# Reform note detection
# ---------------------------------------------------------------------------

REFORM_NOTE_RE = re.compile(
    r'^(?:Párrafo|Párrafos|Fracción|Fracciones|Inciso|Incisos|'
    r'Artículo|Artículos|Numeral|Numerales|Sección|Capítulo|Título|'
    r'Denominación[^.]{0,30}|Apartado|Fe de erratas)'
    r'\s+(?:reformad|adicionad|derogad|recorrid|abrogad|publicad)',
    re.IGNORECASE,
)

_REFORM_DOF_RE = re.compile(r'DOF\s+(\d{2}[/-]\d{2}[/-]\d{4})')
_REFORM_ACTION_RE = re.compile(
    r'(reformad[oa]s?|adicionad[oa]s?|derogad[oa]s?|recorrid[oa]s?|'
    r'abrogad[oa]s?|fe de erratas)',
    re.IGNORECASE,
)


def _is_reform_note(text: str) -> bool:
    """Detect reform annotation lines like 'Párrafo reformado DOF 10-06-2011'."""
    s = text.strip()
    if 'DOF' not in s:
        return False
    return bool(REFORM_NOTE_RE.match(s))


def _parse_reform_note(text: str) -> dict:
    """Parse a reform annotation into a structured dict."""
    node: dict = {"type": "reform_note", "text": text.strip()}
    m = _REFORM_ACTION_RE.search(text)
    if m:
        raw = m.group(1).lower()
        if raw.startswith('reformad'):
            node["action"] = "reformado"
        elif raw.startswith('adicionad'):
            node["action"] = "adicionado"
        elif raw.startswith('derogad'):
            node["action"] = "derogado"
        elif raw.startswith('recorrid'):
            node["action"] = "recorrido"
        elif raw.startswith('abrogad'):
            node["action"] = "abrogado"
        elif 'fe de erratas' in raw:
            node["action"] = "fe_de_erratas"
        else:
            node["action"] = None
    else:
        node["action"] = None
    dates = _REFORM_DOF_RE.findall(text)
    node["dof_date"] = dates[-1].replace('/', '-') if dates else None
    return node


def _slugify_ordinal(text: str) -> str:
    """Normalize an ordinal for use in stable IDs.
    'I' → 'i', 'Primero' → 'primero', '1o.' → '1', '15-A' → '15-a'."""
    s = text.strip().lower()
    s = re.sub(r'[°ºo.]+$', '', s)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9\-]', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s or 'unknown'


def _parse_table_lines(table_lines: list[str], meta: dict | None = None) -> dict:
    """Parse markdown table lines (| ... |) into a table content node.

    `meta` (opcional) trae la procedencia registrada por extract_lines vía
    el marcador `_TABLE_META_RE` ({'source_method', 'source_page'}); sin
    ella se asume el default histórico: tabla OCR sin página conocida.
    """
    headers: list[str] = []
    rows: list[list[str]] = []
    have_headers = False
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        # Fila separadora: al menos una celda con contenido y todas las no
        # vacías son guiones. Una fila 100 % vacía NO es separador — es el
        # header vacío de una tabla de una fila (sin header en el PDF).
        non_empty = [c for c in cells if c]
        if non_empty and all(re.fullmatch(r'-{2,}', c) for c in non_empty):
            continue  # separator row
        if not have_headers:
            headers = cells
            have_headers = True
        else:
            rows.append(cells)
    node = {
        "type": "table",
        "title": None,
        "headers": headers,
        "rows": rows,
        "source_method": "ocr",
        "source_page": None,
    }
    if meta:
        node.update(meta)
    return node


def _load_catalog_entry(pdf_path: Path) -> dict:
    """Load catalog metadata for a PDF from catalogo.json."""
    catalog_path = Path(__file__).parent.parent / "catalogo.json"
    if not catalog_path.exists():
        return {}
    with open(catalog_path, encoding="utf-8") as f:
        laws = json.load(f)
    for law in laws:
        if law.get("pdf_filename") == pdf_path.name:
            return law
        if pdf_path.stem == law.get("md_slug"):
            return law
    return {}


# ---------------------------------------------------------------------------
# AST Builder — Canonical JSON representation
# ---------------------------------------------------------------------------

def build_ast(lines: list[str], metadata: dict) -> dict:
    """
    Build a canonical AST from extracted text lines and catalog metadata.
    Conforms to schema/law_ast.schema.json.

    The AST is the structured 'source of truth'; Markdown and other formats
    are rendered from it.  The detection logic mirrors build_markdown() but
    constructs a tree instead of flat strings.
    """
    # --- Detect and clean running header (same as build_markdown) ---
    global _running_header
    _running_header = _detect_running_header(lines)
    if _running_header:
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            norm = ' '.join(stripped.split())
            if norm == _running_header:
                continue
            cleaned.append(_strip_running_header_inline(stripped, _running_header))
        lines = cleaned

    # --- Derive abbreviation from slug ---
    md_slug = metadata.get("md_slug", "")
    abbrev = md_slug.split('_')[0] if md_slug else ""

    # --- Initialize root document ---
    root: dict = {
        "schema_version": "1.0.0",
        "id": md_slug,
        "abbreviation": abbrev,
        "name": metadata.get("nombre", ""),
        "catalog_number": metadata.get("numero", ""),
        "source": {
            "pdf_url": metadata.get("pdf_url", ""),
            "pdf_filename_origen": metadata.get("pdf_filename_origen", ""),
            "dof_publication": metadata.get("dof", ""),
            "last_reform": metadata.get("ultima_reforma", ""),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        "preamble": [],
        "structure": [],
    }

    # --- Hierarchy management ---
    # level: titulo=1, capitulo=2, seccion=3, articulo/transitorio_articulo=4
    LEVEL = {"titulo": 1, "capitulo": 2, "seccion": 3, "transitorios": 1,
             "articulo": 4, "transitorio_articulo": 4}

    stack: list[tuple[dict, int]] = []  # (node, level)
    first_structural = False  # True once the first heading is seen
    buffer = ""
    in_transitorios = False
    pending_section = False
    table_accum: list[str] = []
    pending_table_meta: dict | None = None

    # -- inner helpers --

    def _current() -> dict:
        return stack[-1][0] if stack else root

    def _current_id() -> str:
        return stack[-1][0]["id"] if stack else ""

    def _pop_to(level: int) -> None:
        while stack and stack[-1][1] >= level:
            stack.pop()

    def _push(node_type: str, heading: str, ordinal: str | None,
              descriptor: str | None = None) -> dict:
        nonlocal first_structural
        first_structural = True
        level = LEVEL.get(node_type, 4)
        _pop_to(level)
        parent_id = _current_id()
        ord_slug = _slugify_ordinal(ordinal) if ordinal else node_type
        node_id = (f"{parent_id}.{node_type}-{ord_slug}" if parent_id
                   else f"{node_type}-{ord_slug}")
        node: dict = {
            "type": node_type,
            "id": node_id,
            "heading": heading,
            "descriptor": descriptor,
            "ordinal": ordinal,
            "content": [],
            "children": [],
        }
        parent = _current()
        target = parent["children"] if "children" in parent else parent["structure"]
        target.append(node)
        stack.append((node, level))
        return node

    def _target_list() -> list:
        """Return the list to append content nodes into."""
        container = _current()
        if first_structural:
            return container.get("content", [])
        return container.get("preamble", container.get("structure", []))

    def _add_text(text: str) -> None:
        """Classify text and append to current content target."""
        target = _target_list()
        # Reform note
        if _is_reform_note(text):
            target.append(_parse_reform_note(text))
            return
        # Fracción
        fm = FRACCION_ROMAN_RE.match(text)
        if fm and _is_roman_numeral(fm.group(1)):
            target.append({"type": "fraccion", "ordinal": fm.group(1),
                           "text": text[fm.end():].strip()})
            return
        # Inciso
        if INCISO_RE.match(text):
            target.append({"type": "inciso", "ordinal": text[0],
                           "text": text[3:].strip() if len(text) > 3 else ""})
            return
        # Paragraph
        target.append({"type": "paragraph", "text": text})

    def _flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        text = buffer.strip()
        buffer = ""
        if text:
            _add_text(text)

    def _flush_table() -> None:
        nonlocal table_accum, pending_table_meta
        if not table_accum:
            return
        node = _parse_table_lines(table_accum, pending_table_meta)
        table_accum = []
        pending_table_meta = None
        # Una tabla sin filas de datos no es tabla (artefactos OCR: nodos
        # vacíos o headers-basura sin cuerpo) — no ensuciar el AST.
        if node["rows"]:
            _target_list().append(node)

    # ---- Main processing loop ----

    for line in lines:
        stripped = line.strip()

        # Blank line
        if not stripped:
            if table_accum:
                _flush_table()
            if buffer:
                _flush()
            pending_section = False
            continue

        # Marcador de procedencia de tabla (emitido por extract_lines para
        # tablas vectoriales) — capturar la metadata y descartar la línea.
        mm = _TABLE_META_RE.match(stripped)
        if mm:
            pending_table_meta = {
                "source_method": mm.group(1),
                "source_page": int(mm.group(2)),
            }
            continue

        # Blockquotes (table placeholders etc.)
        if stripped.startswith('>'):
            if table_accum:
                _flush_table()
            _flush()
            _target_list().append({"type": "paragraph", "text": stripped})
            pending_section = False
            continue

        # Table rows — accumulate
        if stripped.startswith('|'):
            _flush()
            table_accum.append(stripped)
            pending_section = False
            continue
        elif table_accum:
            _flush_table()

        # Pending descriptive section name (follows a section heading)
        if pending_section:
            pending_section = False
            if _is_descriptive_name(stripped):
                _current()["descriptor"] = stripped
                continue

        # Reform notes — detect early to avoid merging with next paragraph
        if _is_reform_note(stripped):
            _flush()
            _target_list().append(_parse_reform_note(stripped))
            continue

        # Transitorios heading
        tm = TRANSITORIO_HEADING_RE.match(stripped)
        if tm:
            _flush()
            _push("transitorios", tm.group(1), None)
            in_transitorios = True
            rest = stripped[tm.end():].strip()
            if rest:
                stripped = rest
            else:
                continue

        # ARTÍCULO + ORDINAL (decree articles)
        am = ARTICLE_ORDINAL_RE.match(stripped)
        if am:
            if buffer and _ARTICLE_REF_TRAILING_RE.search(buffer.rstrip()):
                buffer = (buffer + " " + stripped).strip()
                continue
            _flush()
            heading = am.group(1).strip().rstrip('.')
            body = am.group(2).strip().lstrip('.-').strip() if am.group(2) else None
            ntype = "transitorio_articulo" if in_transitorios else "articulo"
            _push(ntype, heading, heading)
            if body:
                buffer = body
            continue

        # Artículo numérico
        if is_article_heading(stripped):
            if buffer and _ARTICLE_REF_TRAILING_RE.search(buffer.rstrip()):
                buffer = (buffer + " " + stripped).strip()
                continue
            _flush()
            heading, body = split_article_heading(stripped)
            ordinal_m = re.match(r'^Artículo\s+(.+)', heading)
            ordinal = ordinal_m.group(1).strip() if ordinal_m else heading
            _push("articulo", heading, ordinal)
            in_transitorios = False
            if body:
                buffer = body
            continue

        # TÍTULO / CAPÍTULO / SECCIÓN
        sm = _match_section_heading(stripped)
        if sm:
            _flush()
            heading_text = sm.group(1).strip()
            rest = sm.group(2).strip()
            descriptor = rest if rest else None
            ht_upper = heading_text.upper()
            if 'TÍTULO' in ht_upper or 'TITULO' in ht_upper:
                sec_type = "titulo"
            elif 'CAPÍTULO' in ht_upper or 'CAPITULO' in ht_upper:
                sec_type = "capitulo"
            else:
                sec_type = "seccion"
            parts = heading_text.split(None, 1)
            ordinal = parts[1].strip() if len(parts) > 1 else ""
            _push(sec_type, heading_text, ordinal, descriptor)
            pending_section = descriptor is None
            continue

        # Transitorio ordinals
        if in_transitorios:
            om = TRANSITORIO_ORDINAL_RE.match(stripped)
            if om:
                _flush()
                ordinal = om.group(1).strip().rstrip('.')
                rest = om.group(2).strip().lstrip('.-').strip()
                _push("transitorio_articulo", ordinal, ordinal)
                if rest:
                    buffer = rest
                continue

        # Fracciones romanas → new paragraph
        rm = FRACCION_ROMAN_RE.match(stripped)
        if rm and _is_roman_numeral(rm.group(1)):
            _flush()
            buffer = stripped
            continue

        # Incisos → new paragraph
        if INCISO_RE.match(stripped):
            _flush()
            buffer = stripped
            continue

        # Line joining (same rules as build_markdown)
        if buffer.endswith('-'):
            buffer = buffer[:-1] + stripped
        elif buffer and buffer[-1] in '.;:' and stripped[0].isupper():
            _flush()
            buffer = stripped
        else:
            buffer = (buffer + " " + stripped).strip() if buffer else stripped

    # Final flush
    if table_accum:
        _flush_table()
    _flush()

    return root


# ---------------------------------------------------------------------------
# Render Markdown from AST — el JSON es la fuente de verdad
# ---------------------------------------------------------------------------

# render_markdown / _render_content / _render_table / _render_node viven ahora en
# md_render.py (importados arriba). Se re-exportan vía esta fachada (Sprint 3.1).


# ---------------------------------------------------------------------------
# Formateo Markdown (legacy — usar render_markdown para nuevas conversiones)
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
    _pending_section = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if buffer:
                joined.append(buffer.strip())
                buffer = ""
            joined.append("")
            _pending_section = False
            continue

        # --- Blockquotes (placeholders de tablas, etc.) → párrafo aislado ---
        if stripped.startswith('>'):
            if buffer:
                joined.append(buffer.strip())
                buffer = ""
            joined.append("")
            joined.append(stripped)
            joined.append("")
            _pending_section = False
            continue

        # --- Filas de tabla markdown (| ... |) → emitir sin unir ---
        if stripped.startswith('|'):
            if buffer:
                joined.append(buffer.strip())
                buffer = ""
            joined.append(stripped)
            _pending_section = False
            continue

        # --- Nombre descriptivo de sección (issue 6) ---
        if _pending_section:
            _pending_section = False
            if _is_descriptive_name(stripped):
                joined[-1] += f" — {stripped}"
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
                # El resto puede empezar con un ordinal transitorio
                stripped = rest
                # continuar evaluando ordinales abajo
            else:
                continue

        # --- Detectar ARTÍCULO + ORDINAL como heading (decretos) ---
        am = ARTICLE_ORDINAL_RE.match(stripped)
        if am:
            # Guardia de contexto: si el buffer termina con preposición, es referencia.
            if buffer and _ARTICLE_REF_TRAILING_RE.search(buffer.rstrip()):
                buffer = (buffer + " " + stripped).strip()
                continue
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
            # Guardia de contexto: si el buffer termina con preposición/artículo
            # ("el", "del", "al", etc.) es una referencia mid-sentence, no heading.
            if buffer and _ARTICLE_REF_TRAILING_RE.search(buffer.rstrip()):
                buffer = (buffer + " " + stripped).strip()
                continue
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
        sm = _match_section_heading(stripped)
        if sm:
            if buffer:
                joined.append(buffer.strip())
                buffer = ""
            heading_text = sm.group(1).strip()
            rest = sm.group(2).strip()
            if rest:
                heading_text += f" — {rest}"
            joined.append("")
            joined.append(f"## {heading_text}")
            _pending_section = not bool(rest)
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
                # Separador original (.- o .) para el ordinal transitorio
                sep = '.-' if '.-' in stripped[:len(om.group(1))+3] else '.'
                formatted = f"**{ordinal}{sep}** {rest}" if rest else f"**{ordinal}{sep}**"
                buffer = formatted
                continue

        # --- Fracciones romanas: I., II., III., XVI., etc. → nuevo párrafo ---
        rm = FRACCION_ROMAN_RE.match(stripped)
        if rm and _is_roman_numeral(rm.group(1)):
            if buffer:
                joined.append(buffer.strip())
                joined.append("")
                buffer = ""
            buffer = stripped
            continue

        # --- Incisos: a), b), c), etc. → nuevo párrafo ---
        if INCISO_RE.match(stripped):
            if buffer:
                joined.append(buffer.strip())
                joined.append("")
                buffer = ""
            buffer = stripped
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

    # Post-proceso: separar incisos que quedaron en línea tras la unión de párrafos
    processed = _post_split_incisos(joined)
    return meta_header + processed


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convierte un PDF de ley mexicana a Markdown estructurado + JSON canónico.",
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
    parser.add_argument(
        "--canonical-dir", "-c",
        type=Path,
        default=None,
        help="Directorio para JSON canónico (default: canonical/).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "md", "both"],
        default="both",
        help="Formato de salida: json, md, o both (default: both).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Valida el JSON generado contra el schema.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    pdf_path: Path = args.pdf.resolve()
    if not pdf_path.exists():
        print(f"Error: no se encontró el archivo '{pdf_path}'", file=sys.stderr)
        sys.exit(1)

    # Ruta de salida por defecto: markdown/<nombre>.md
    if args.output is None:
        output_path = Path(__file__).parent.parent / "markdown" / (pdf_path.stem + ".md")
    else:
        output_path = args.output.resolve()

    canonical_dir = args.canonical_dir
    if canonical_dir is None:
        canonical_dir = Path(__file__).parent.parent / "canonical"

    title = args.title or pdf_path.stem.replace("_", " ").replace("-", " ")

    print(f"Extrayendo texto de: {pdf_path.name}", flush=True)
    lines, _ = extract_lines(pdf_path)

    # --- Construir AST canónico (fuente de verdad) ---
    catalog_entry = _load_catalog_entry(pdf_path)
    if not catalog_entry.get("nombre"):
        catalog_entry["nombre"] = title

    print("Construyendo AST canónico...", flush=True)
    ast = build_ast(lines, catalog_entry)

    # --- Escribir JSON ---
    if args.format in ("json", "both"):
        canonical_dir = canonical_dir.resolve()
        canonical_dir.mkdir(parents=True, exist_ok=True)
        json_path = canonical_dir / (pdf_path.stem + ".json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(ast, f, ensure_ascii=False, indent=2)
        print(f"✅ JSON    → {json_path}")

    # --- Validar contra schema ---
    if args.validate:
        schema_path = Path(__file__).parent.parent / "schema" / "law_ast.schema.json"
        if schema_path.exists():
            try:
                import jsonschema
                with open(schema_path) as f:
                    schema = json.load(f)
                jsonschema.validate(ast, schema)
                print("✅ JSON válido contra schema")
            except ImportError:
                print("⚠️  jsonschema no instalado, omitiendo validación", file=sys.stderr)
            except jsonschema.ValidationError as e:
                print(f"❌ Validación: {e.message[:200]}", file=sys.stderr)

    # --- Escribir Markdown (renderizado desde el AST) ---
    if args.format in ("md", "both"):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        md_lines = render_markdown(ast)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))
        print(f"✅ Markdown → {output_path}")
        print(f"   Líneas: {len(md_lines)}")


if __name__ == "__main__":
    main()
