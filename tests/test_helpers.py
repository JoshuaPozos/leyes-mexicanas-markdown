"""Tests de helpers puros de pdf_to_md.

Cubre funciones sin I/O y sin estado externo (salvo `is_header_line` que
depende del global `_running_header`, que reseteamos en su fixture)."""

from __future__ import annotations

import re

import pdf_to_md as p
import pytest


# ---------------------------------------------------------------------------
# _slugify_ordinal
# ---------------------------------------------------------------------------

class TestSlugifyOrdinal:
    @pytest.mark.parametrize("raw,expected", [
        ("I", "i"),
        ("II", "ii"),
        ("XVI", "xvi"),
        ("XXIX-A", "xxix-a"),
        ("L", "l"),
    ])
    def test_roman_numerals(self, raw: str, expected: str) -> None:
        assert p._slugify_ordinal(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        # NOTA: la regex `[°ºo.]+$` aplicada al inicio de la función borra
        # cualquier 'o' al final, no solo el indicador ordinal. Por eso
        # 'primero' → 'primer' (la 'o' final se trunca). Es un bug latente
        # documentado en shitty/HALLAZGOS.md; los tests reflejan el
        # comportamiento actual, no el deseado.
        ("Primero", "primer"),
        ("SEGUNDO", "segund"),
        ("Tercero", "tercer"),
        ("Décimo Primero", "decimo-primer"),
        ("Único", "unic"),
    ])
    def test_spanish_ordinals_current_behavior(self, raw: str, expected: str) -> None:
        assert p._slugify_ordinal(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        ("1", "1"),
        ("123", "123"),
        ("4-A", "4-a"),
        ("15-Bis", "15-bis"),
        ("1o.", "1"),
        ("2°", "2"),
    ])
    def test_numerals(self, raw: str, expected: str) -> None:
        assert p._slugify_ordinal(raw) == expected

    def test_strips_accents(self) -> None:
        # Misma nota que en test_spanish_ordinals_current_behavior: la 'o' final
        # se borra, así 'Décimo' → 'decim'.
        assert p._slugify_ordinal("Décimo") == "decim"
        assert p._slugify_ordinal("ÚNICO") == "unic"

    def test_collapses_separators(self) -> None:
        assert p._slugify_ordinal("a   b") == "a-b"
        assert p._slugify_ordinal("a---b") == "a-b"
        assert p._slugify_ordinal("---a---") == "a"

    def test_unknown_for_empty_or_pure_punctuation(self) -> None:
        assert p._slugify_ordinal("") == "unknown"
        assert p._slugify_ordinal("---") == "unknown"
        assert p._slugify_ordinal("...") == "unknown"


# ---------------------------------------------------------------------------
# is_article_heading
# ---------------------------------------------------------------------------

class TestIsArticleHeading:
    @pytest.mark.parametrize("line", [
        "Artículo 1",
        "Artículo 5",
        "Artículo 123",
        "Artículo 4-A",
        "Artículo 15 Bis",
        "Artículo 9o. Lo dispuesto...",
    ])
    def test_valid_headings(self, line: str) -> None:
        assert p.is_article_heading(line) is True

    @pytest.mark.parametrize("line", [
        "artículo 1",                            # minúscula inicial
        "el artículo 1 de esta Ley",             # referencia mid-sentence
        "Articulo 1",                            # sin tilde
        "Art. 1",                                # abreviado
        "ARTÍCULO 1",                            # ALL CAPS
        "Disposición 1",                         # otra palabra
        "",
        "   ",
    ])
    def test_invalid_headings(self, line: str) -> None:
        assert p.is_article_heading(line) is False


# ---------------------------------------------------------------------------
# split_article_heading
# ---------------------------------------------------------------------------

class TestSplitArticleHeading:
    def test_simple_with_body(self) -> None:
        # El punto separador queda al inicio del body (la regex no lo consume).
        heading, body = p.split_article_heading("Artículo 5. Las personas...")
        assert heading == "Artículo 5"
        assert body == ". Las personas..."

    def test_no_body_returns_none(self) -> None:
        heading, body = p.split_article_heading("Artículo 5")
        assert heading == "Artículo 5"
        assert body is None

    def test_with_suffix(self) -> None:
        heading, body = p.split_article_heading("Artículo 4-A. Texto del artículo.")
        assert heading == "Artículo 4-A"
        assert body == ". Texto del artículo."

    def test_strips_trailing_dot(self) -> None:
        heading, _ = p.split_article_heading("Artículo 9o. Lo dispuesto.")
        assert not heading.endswith('.')


# ---------------------------------------------------------------------------
# _is_roman_numeral
# ---------------------------------------------------------------------------

class TestIsRomanNumeral:
    @pytest.mark.parametrize("s", [
        "I", "II", "III", "IV", "V", "VI", "IX", "X",
        "XV", "XVI", "XXIX", "XL", "XLIX", "L",
    ])
    def test_valid(self, s: str) -> None:
        assert p._is_roman_numeral(s) is True

    @pytest.mark.parametrize("s", [
        "",
        "A",        # no es romano
        "0",        # número árabe
        "IIII",     # romano malformado (4 = IV, no IIII)
        "VV",       # malformado
        "LL",       # malformado
        "XLIIII",   # malformado
        "abc",
        "i",        # minúsculas no aceptadas
    ])
    def test_invalid(self, s: str) -> None:
        assert p._is_roman_numeral(s) is False


# ---------------------------------------------------------------------------
# build_page_marker_re
# ---------------------------------------------------------------------------

class TestBuildPageMarkerRe:
    def test_returns_compiled_pattern(self) -> None:
        rx = p.build_page_marker_re(313)
        assert isinstance(rx, re.Pattern)

    def test_matches_valid_marker(self) -> None:
        rx = p.build_page_marker_re(313)
        assert rx.search(" 12 de 313 ") is not None
        assert rx.search("texto 1 de 313 más texto") is not None

    def test_does_not_match_other_total(self) -> None:
        rx = p.build_page_marker_re(313)
        assert rx.search(" 12 de 200 ") is None

    def test_clean_page_markers_removes_match(self) -> None:
        rx = p.build_page_marker_re(313)
        cleaned = p.clean_page_markers("hola 12 de 313 mundo", rx)
        assert "12 de 313" not in cleaned
        assert "hola" in cleaned and "mundo" in cleaned


# ---------------------------------------------------------------------------
# is_section_heading
# ---------------------------------------------------------------------------

class TestIsSectionHeading:
    @pytest.mark.parametrize("line", [
        "TÍTULO PRIMERO",
        "TÍTULO I",
        "Título Primero",
        "CAPÍTULO II",
        "Capítulo Único",
        "Sección Cuarta",
        "SECCIÓN II",
    ])
    def test_valid_section_headings(self, line: str) -> None:
        assert p.is_section_heading(line) is True

    @pytest.mark.parametrize("line", [
        "Sección II de este Capítulo.",     # texto de cuerpo
        "Capítulo Único de la sección.",    # cuerpo
        "Artículo 1",                       # otro tipo
        "Disposiciones generales",          # sin keyword
        "",
    ])
    def test_invalid_section_headings(self, line: str) -> None:
        assert p.is_section_heading(line) is False


# ---------------------------------------------------------------------------
# is_header_line (depende de _running_header global)
# ---------------------------------------------------------------------------

class TestIsHeaderLine:
    @pytest.fixture(autouse=True)
    def _reset_running_header(self) -> None:
        original = p._running_header
        p._running_header = ""
        yield
        p._running_header = original

    @pytest.mark.parametrize("line", [
        "CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN",
        "Secretaría General",
        "Secretaría de Servicios Parlamentarios",
        "Última Reforma DOF 03/03/2026",
    ])
    def test_static_headers(self, line: str) -> None:
        assert p.is_header_line(line) is True

    def test_running_header_match(self) -> None:
        p._running_header = "LEY DEL IMPUESTO SOBRE LA RENTA"
        assert p.is_header_line("LEY DEL IMPUESTO SOBRE LA RENTA") is True
        assert p.is_header_line(" LEY DEL IMPUESTO SOBRE LA RENTA  ") is True

    def test_normal_paragraph_is_not_header(self) -> None:
        assert p.is_header_line("Las personas físicas...") is False
        assert p.is_header_line("Artículo 5") is False


# ---------------------------------------------------------------------------
# _detect_running_header
# ---------------------------------------------------------------------------

class TestDetectRunningHeader:
    def test_repeated_header(self) -> None:
        lines = [
            "LEY DEL IMPUESTO SOBRE LA RENTA",
            "Algún contenido",
            "LEY DEL IMPUESTO SOBRE LA RENTA",
            "Más contenido",
            "LEY DEL IMPUESTO SOBRE LA RENTA",
        ]
        assert p._detect_running_header(lines) == "LEY DEL IMPUESTO SOBRE LA RENTA"

    def test_no_repeated_header_returns_empty(self) -> None:
        lines = ["Contenido 1", "Contenido 2", "Contenido 3"]
        assert p._detect_running_header(lines) == ""

    def test_below_threshold_returns_empty(self) -> None:
        # La función exige al menos 3 ocurrencias
        lines = [
            "LEY DEL IMPUESTO SOBRE LA RENTA",
            "x",
            "LEY DEL IMPUESTO SOBRE LA RENTA",
        ]
        assert p._detect_running_header(lines) == ""

    def test_short_uppercase_strings_ignored(self) -> None:
        # Cadenas <16 chars no califican como running header
        lines = ["LEY", "LEY", "LEY", "LEY"]
        assert p._detect_running_header(lines) == ""

    def test_normalizes_whitespace(self) -> None:
        lines = [
            "LEY  DEL  IMPUESTO   SOBRE LA RENTA",
            "x",
            "LEY DEL IMPUESTO SOBRE LA RENTA",
            "y",
            "LEY DEL IMPUESTO SOBRE LA RENTA",
        ]
        # Las dos formas se normalizan y cuentan como la misma cadena
        result = p._detect_running_header(lines)
        assert result == "LEY DEL IMPUESTO SOBRE LA RENTA"


# ---------------------------------------------------------------------------
# clean_page_markers (función pura cercana)
# ---------------------------------------------------------------------------

class TestCleanPageMarkers:
    def test_removes_marker_in_middle(self) -> None:
        # El regex consume los espacios alrededor del marcador, así que el
        # resultado tiene un único espacio (no triple).
        rx = p.build_page_marker_re(313)
        assert p.clean_page_markers("antes 5 de 313 después", rx) == "antes después"

    def test_strips_outer_whitespace(self) -> None:
        rx = p.build_page_marker_re(313)
        assert p.clean_page_markers("  hola  ", rx) == "hola"

    def test_no_match_passthrough(self) -> None:
        rx = p.build_page_marker_re(313)
        assert p.clean_page_markers("solo texto", rx) == "solo texto"
