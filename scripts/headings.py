#!/usr/bin/env python3
"""headings.py — Detección ESTRUCTURAL de headings de leyes mexicanas: artículos,
ordinales (decretos/transitorios), fracciones, incisos y headings de sección
(Título/Capítulo/Sección).

Extraído de `pdf_to_md.py` (Sprint 3.1 — modularización); `pdf_to_md` re-exporta
estas funciones y los regex transversales (los usan build_ast y build_markdown),
así que la salida es byte-idéntica y la API pública no cambia. La detección de
header de PÁGINA (is_header_line, marcadores) queda en pdf_to_md por su acoplamiento
con la extracción (estado `_running_header`).
"""

import re

from constants import (
    DESCRIPTIVE_NAME_MAX_LENGTH,
    DESCRIPTIVE_NAME_TITLE_CASE_MAX_LENGTH,
)


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
