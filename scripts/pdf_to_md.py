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

# OCR opcional para tablas-imagen
_HAS_OCR = False
try:
    import pytesseract
    from PIL import Image
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
    if not s or len(s) > 100:
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
    # ALL CAPS con al menos una palabra de 3+ letras
    if s == s.upper() and re.search(r'[A-ZÁÉÍÓÚÑ]{3,}', s):
        return True
    # Title Case con prefijo descriptivo
    if re.match(r'^(?:De |Del |Sobre |Para |En |Por |Disposiciones )', s) and len(s) < 80:
        return True
    return False


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

            # --- Issue 9: Detectar tablas-imagen y extraer con OCR ---
            large_imgs = [img for img in (page.images or [])
                          if abs(img.get('x1', 0) - img.get('x0', 0)) > 200
                          and abs(img.get('y1', 0) - img.get('y0', 0)) > 100]
            if large_imgs:
                tables = page.extract_tables()
                if not tables:
                    ocr_result = _ocr_page_table(page, large_imgs, page_num + 1, verbose)
                    all_lines.extend(ocr_result)

    return all_lines, total


def _ocr_page_table(page, large_imgs: list, page_num: int, verbose: bool) -> list[str]:
    """Extrae tablas-imagen de una página usando OCR (Tesseract).
    Usa image_to_data para obtener posiciones espaciales y reconstruir la tabla."""
    if not _HAS_OCR:
        return [f"> **[Tabla no extraíble — ver PDF original, página {page_num}]**"]

    result_lines: list[str] = []
    for img in large_imgs:
        x0 = img.get('x0', 0)
        y0 = min(img.get('top', img.get('y0', 0)), img.get('y0', 0))
        x1 = img.get('x1', 0)
        y1 = max(img.get('bottom', img.get('y1', 0)), img.get('y1', 0))
        try:
            cropped = page.crop((x0, y0, x1, y1))
            pil_img = cropped.to_image(resolution=300).original
            # Obtener datos espaciales con --psm 6 (bloque uniforme)
            data = pytesseract.image_to_data(
                pil_img, lang='spa+eng', config='--psm 6',
                output_type=pytesseract.Output.DICT,
            )
            md_table = _build_table_from_spatial(data, verbose)
            if not md_table:
                result_lines.append(f"> **[Tabla no extraíble — ver PDF original, página {page_num}]**")
                continue
            if verbose:
                n = sum(1 for l in md_table if l.startswith('|'))
                print(f"    🔍 OCR tabla página {page_num}: {n} filas", flush=True)
            result_lines.extend(md_table)
        except Exception as e:
            if verbose:
                print(f"    ⚠️ OCR falló página {page_num}: {e}", flush=True)
            result_lines.append(f"> **[Tabla no extraíble — ver PDF original, página {page_num}]**")
    return result_lines


def _build_table_from_spatial(data: dict, verbose: bool = False) -> list[str]:
    """Reconstruye una tabla markdown a partir de datos espaciales de Tesseract.
    Agrupa palabras por fila (y-position) y columna (x-position)."""
    from collections import defaultdict

    # Extraer palabras con posición y confianza mínima
    words = []
    for i in range(len(data['text'])):
        txt = (data['text'][i] or '').strip()
        if not txt or data['conf'][i] < 1:
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
    ROW_TOLERANCE = 12  # píxeles
    rows_map: dict[int, list[dict]] = {}
    for w in words:
        y_center = w['top'] + w['height'] // 2
        assigned = False
        for key in rows_map:
            if abs(y_center - key) <= ROW_TOLERANCE:
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
    # Detectar filas numéricas: >50% de palabras son números/porcentajes
    NUM_RE = re.compile(r'^[\d$%,.]+%?$')
    numeric_rows = []
    for row in sorted_rows:
        num_count = sum(1 for w in row if NUM_RE.match(w['text']))
        if num_count >= max(len(row) * 0.5, 2):
            numeric_rows.append(row)

    if not numeric_rows:
        # Sin filas numéricas → emitir texto plano
        lines = []
        for row in sorted_rows:
            lines.append(' '.join(w['text'] for w in row))
        return ['', *lines, '']

    # Encontrar el número de columnas más frecuente en filas numéricas
    from collections import Counter
    col_counts = Counter(len(r) for r in numeric_rows)
    target_cols = col_counts.most_common(1)[0][0]

    # Calcular posiciones x centrales para cada columna usando las filas
    # numéricas con el target_cols correcto
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
            # Usar boundaries: avanzar hasta pasar el boundary correcto
            col = 0
            for b in col_boundaries:
                if w_center > b:
                    col += 1
                else:
                    break
            cols[col].append(w['text'])
        return [' '.join(cols.get(c, [''])) for c in range(target_cols)]

    # --- Paso 4: separar título, encabezados de columna, filas de datos, texto posterior ---
    # Encontrar el índice de la primera fila numérica
    first_num_idx = None
    for i, row in enumerate(sorted_rows):
        num_count = sum(1 for w in row if NUM_RE.match(w['text']))
        if num_count >= max(len(row) * 0.5, 2):
            first_num_idx = i
            break

    if first_num_idx is None:
        # Sin filas numéricas → texto plano (no debería llegar aquí)
        lines = []
        for row in sorted_rows:
            lines.append(' '.join(w['text'] for w in row))
        return ['', *lines, '']

    # Clasificar filas pre-tabla: título vs encabezados de columna.
    # Heurística: encontrar el mayor salto vertical (gap) entre filas pre-tabla.
    # Todo lo que está por encima del mayor gap es título; por debajo es header.
    pre_rows = sorted_rows[:first_num_idx]
    title_rows: list[list[dict]] = []
    header_rows: list[list[dict]] = []

    if len(pre_rows) <= 1:
        # 0-1 filas pre-tabla: no hay encabezados que reconstruir
        title_rows = pre_rows
    elif col_positions:
        # Calcular y-center de cada fila pre-tabla
        def _row_y(row: list[dict]) -> float:
            return sum(w['top'] + w['height'] / 2 for w in row) / len(row)
        pre_ys = [_row_y(r) for r in pre_rows]
        # Encontrar el mayor gap vertical
        max_gap = 0.0
        split_idx = 0  # split: [0..split_idx) = title, [split_idx..] = header
        for i in range(1, len(pre_ys)):
            gap = pre_ys[i] - pre_ys[i - 1]
            if gap > max_gap:
                max_gap = gap
                split_idx = i
        # Solo separar si el gap es significativo (> 50% del gap promedio)
        avg_gap = (pre_ys[-1] - pre_ys[0]) / max(len(pre_ys) - 1, 1)
        if max_gap > avg_gap * 1.5 and split_idx > 0:
            title_rows = pre_rows[:split_idx]
            header_rows = pre_rows[split_idx:]
        else:
            # Gap uniforme → todo es header (no hay título)
            header_rows = pre_rows
    else:
        title_rows = pre_rows

    # Reconstruir encabezados de columna: asignar cada fila de header a columnas
    # y unir verticalmente (multi-line headers)
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
                    # Ninguna palabra en las columnas anteriores a min_col
                    min_x = min(w['left'] for w in row)
                    left_boundary = col_boundaries[min_col - 1]
                    if min_x > left_boundary:
                        merged = ['' for _ in range(target_cols)]
                        merged[max_col] = ' '.join(w['text'] for w in row)
                        return merged
        return base

    for row in header_rows:
        # Filtrar filas de ruido OCR: requiere al menos una palabra de >= 4 letras
        has_real_word = any(
            sum(c.isalpha() for c in w['text']) >= 4 for w in row
        )
        if not has_real_word:
            continue
        assigned = _assign_header_row(row)
        for c in range(target_cols):
            val = assigned[c].strip() if c < len(assigned) else ''
            if val and val not in (',', '.', '-'):
                col_headers[c].append(val)

    # Construir nombres de columna finales
    header_names = [' '.join(parts) if parts else f'Col {c+1}'
                    for c, parts in enumerate(col_headers)]

    # Detectar si la primera fila numérica es una fila de unidades (ej. $ $ $ %)
    # y si es así, incorporarla a los encabezados
    data_start_idx = first_num_idx
    first_data_row = sorted_rows[first_num_idx]
    UNIT_RE = re.compile(r'^[\$%#€£¥]+$')
    first_row_vals = assign_to_columns(first_data_row)
    if all(UNIT_RE.match(v.strip()) for v in first_row_vals if v.strip()):
        # Es fila de unidades → agregar al header
        for c, val in enumerate(first_row_vals):
            unit = val.strip()
            if unit and c < len(header_names):
                header_names[c] = f'{header_names[c]} ({unit})' if header_names[c] != f'Col {c+1}' else unit
        data_start_idx = first_num_idx + 1

    # Emitir markdown
    md: list[str] = ['']

    # Título (texto previo que no alinea con columnas)
    for row in title_rows:
        text = ' '.join(w['text'] for w in row)
        md.append(f'**{text}**' if text == text.upper() and len(text) > 3 else text)

    # Tabla: header
    md.append('| ' + ' | '.join(header_names) + ' |')
    md.append('| ' + ' | '.join(['---'] * target_cols) + ' |')

    # Tabla: filas de datos
    post_text: list[str] = []
    for row in sorted_rows[data_start_idx:]:
        num_count = sum(1 for w in row if NUM_RE.match(w['text']))
        is_numeric = num_count >= max(len(row) * 0.5, 2)
        if is_numeric and not post_text:
            cols = assign_to_columns(row)
            md.append('| ' + ' | '.join(cols) + ' |')
        else:
            post_text.append(' '.join(w['text'] for w in row))

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


def _post_split_incisos(lines: list[str]) -> list[str]:
    """Separa incisos a), b), c) que quedaron inline después de la unión de párrafos."""
    result: list[str] = []
    for line in lines:
        if not line or line.startswith('#') or line.startswith('>') or line.startswith('---') or line.startswith('**'):
            result.append(line)
            continue
        parts = re.split(r'(?<=[\.:])\s+(?=[a-z]\)\s)', line)
        if len(parts) > 1:
            for i, part in enumerate(parts):
                result.append(part.strip())
                if i < len(parts) - 1:
                    result.append("")
        else:
            result.append(line)
    return result


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
                # El resto puede empezar con un ordinal
                stripped = rest
                # fall through to ordinal check below
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
                # Separador original (.- o .)
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

    # Post-proceso: separar incisos que quedaron inline
    processed = _post_split_incisos(joined)
    return meta_header + processed


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
