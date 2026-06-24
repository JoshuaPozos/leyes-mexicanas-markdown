"""Tests del flujo de tablas vectoriales (Sprint 3.0).

Cubren:
- _clean_cell — colapso de celdas pdfplumber a una línea.
- _is_valid_vector_table — filtro de validez (N×1, vacías, mínimo de filas).
- _render_vector_table — emisión markdown + marcador de procedencia.
- _parse_table_lines con meta — override de source_method/source_page.
- build_ast — consumo del marcador: nodo table con procedencia correcta,
  default histórico ('ocr', None) intacto, sin fugas de meta entre tablas.
"""

from __future__ import annotations

import pdf_to_md as p
import pytest

# ---------------------------------------------------------------------------
# _clean_cell
# ---------------------------------------------------------------------------


class TestCleanCell:
    def test_none_becomes_empty(self) -> None:
        assert p._clean_cell(None) == ""

    def test_multiline_collapses_to_single_line(self) -> None:
        assert p._clean_cell("Tasa\naplicable") == "Tasa aplicable"

    def test_multiple_spaces_collapse(self) -> None:
        assert p._clean_cell("  Monto   de\n  ingresos ") == "Monto de ingresos"

    def test_pipe_is_sanitized(self) -> None:
        # Un pipe literal dentro de la celda rompería la fila markdown
        assert p._clean_cell("a|b") == "a/b"

    def test_plain_text_unchanged(self) -> None:
        assert p._clean_cell("1.00 %") == "1.00 %"


# ---------------------------------------------------------------------------
# _is_valid_vector_table
# ---------------------------------------------------------------------------


class TestIsValidVectorTable:
    def test_real_table_accepted(self) -> None:
        data = [
            ["Monto", "Tasa"],
            ["Hasta 25,000.00", "1.00 %"],
            ["Hasta 50,000.00", "1.10 %"],
        ]
        assert p._is_valid_vector_table(data) is True

    def test_single_row_with_content_accepted(self) -> None:
        # Filas de datos dibujadas como tabla propia de una fila (tablas
        # de valuación LFT): válidas si tienen ≥2 celdas con contenido
        assert p._is_valid_vector_table([["524", "100%"]]) is True

    def test_single_row_single_cell_rejected(self) -> None:
        # Recuadro decorativo: 1 fila con una sola celda llena
        assert p._is_valid_vector_table([["texto", "", None]]) is False

    def test_empty_rejected(self) -> None:
        assert p._is_valid_vector_table([]) is False

    @pytest.mark.parametrize("n_rows", [2, 49])
    def test_single_column_rejected(self, n_rows: int) -> None:
        # El audit mostró que las N×1 (2×1, 49×1) son layouts de dos
        # columnas o listas que pdfplumber confunde con tabla.
        data = [[f"línea {i}"] for i in range(n_rows)]
        assert p._is_valid_vector_table(data) is False

    def test_all_empty_cells_rejected(self) -> None:
        data = [[None, ""], ["", None]]
        assert p._is_valid_vector_table(data) is False

    def test_ragged_rows_use_widest(self) -> None:
        # La fila más ancha define el número de columnas
        data = [["solo"], ["a", "b"]]
        assert p._is_valid_vector_table(data) is True


# ---------------------------------------------------------------------------
# _route_page
# ---------------------------------------------------------------------------


class TestRoutePage:
    def test_image_without_tables_goes_ocr(self) -> None:
        assert p._route_page(True, 0) == "ocr"

    def test_valid_vector_tables_win_over_image(self) -> None:
        # Si pdfplumber lee las celdas nativamente, OCR solo degradaría
        assert p._route_page(True, 2) == "vector"

    def test_vector_tables_without_image(self) -> None:
        assert p._route_page(False, 1) == "vector"

    def test_plain_page_goes_text(self) -> None:
        assert p._route_page(False, 0) == "text"

    def test_image_with_only_invalid_detections_still_goes_ocr(self) -> None:
        # Regresión del edge case: una imagen-tabla en página donde
        # find_tables() solo devuelve falsos positivos N×1 (que el filtro
        # descarta → n_vector_tables == 0) debe ir a OCR, no aplanarse.
        # El gate anterior (`not found_tables`) la perdía en silencio.
        assert p._route_page(True, 0) == "ocr"


# ---------------------------------------------------------------------------
# _render_vector_table
# ---------------------------------------------------------------------------


class TestRenderVectorTable:
    def test_structure_marker_header_separator_rows(self) -> None:
        data = [["Col A", "Col B"], ["1", "2"]]
        md = p._render_vector_table(data, page_num=146)
        assert md == [
            "",
            "<!--mxmd:table src=text page=146-->",
            "| Col A | Col B |",
            "| --- | --- |",
            "| 1 | 2 |",
            "",
        ]

    def test_multiline_headers_collapse(self) -> None:
        data = [["Tasa\naplicable", "Monto de\ningresos"], ["1.00 %", "25,000"]]
        md = p._render_vector_table(data, page_num=1)
        assert "| Tasa aplicable | Monto de ingresos |" in md

    def test_none_cells_become_empty(self) -> None:
        data = [["a", "b"], [None, "2"]]
        md = p._render_vector_table(data, page_num=1)
        assert "|  | 2 |" in md

    def test_ragged_rows_padded_to_widest(self) -> None:
        data = [["a", "b", "c"], ["1", "2"]]
        md = p._render_vector_table(data, page_num=1)
        assert "| 1 | 2 |  |" in md

    def test_marker_matches_meta_regex(self) -> None:
        md = p._render_vector_table([["a", "b"], ["1", "2"]], page_num=99)
        mm = p._TABLE_META_RE.match(md[1])
        assert mm is not None
        assert mm.group(1) == "text"
        assert mm.group(2) == "99"

    def test_single_row_table_gets_empty_headers(self) -> None:
        # Una fila de datos dibujada como tabla propia: headers vacíos,
        # la fila va como dato (no promovida a header)
        md = p._render_vector_table([["524", "100%"]], page_num=7)
        assert md == [
            "",
            "<!--mxmd:table src=text page=7-->",
            "|  |  |",
            "| --- | --- |",
            "| 524 | 100% |",
            "",
        ]

    def test_all_empty_columns_collapse(self) -> None:
        # Columnas 100% vacías (artefacto de detección) se colapsan
        data = [["A", None, "B"], ["1", "", "2"], ["3", None, "4"]]
        md = p._render_vector_table(data, page_num=1)
        assert "| A | B |" in md
        assert "| 1 | 2 |" in md

    def test_collapse_keeps_minimum_columns(self) -> None:
        # No colapsar por debajo de VECTOR_TABLE_MIN_COLS: una tabla 2-col
        # con una columna vacía se emite tal cual (no como lista N×1)
        data = [["A", ""], ["1", None], ["2", ""]]
        md = p._render_vector_table(data, page_num=1)
        assert "| A |  |" in md

    def test_all_empty_data_rows_skipped(self) -> None:
        # Filas 100% vacías (espaciado visual de la rejilla) se omiten
        data = [["A", "B"], ["", None], ["1", "2"]]
        md = p._render_vector_table(data, page_num=1)
        assert "| 1 | 2 |" in md
        assert "|  |  |" not in md

    def test_private_use_chars_become_hyphen(self) -> None:
        # Bullets de fuentes embebidas (área privada Unicode) → '-'
        data = [["Clase", "Criterio"], ["\uf0a7 I", "\uf0b7 leve"]]
        md = p._render_vector_table(data, page_num=1)
        assert "| - I | - leve |" in md


# ---------------------------------------------------------------------------
# _parse_table_lines con meta
# ---------------------------------------------------------------------------


class TestParseTableLinesMeta:
    LINES = [
        "| Col A | Col B |",
        "| --- | --- |",
        "| 1 | 2 |",
    ]

    def test_default_is_ocr_without_page(self) -> None:
        node = p._parse_table_lines(self.LINES)
        assert node["source_method"] == "ocr"
        assert node["source_page"] is None

    def test_meta_overrides_provenance(self) -> None:
        meta = {"source_method": "text", "source_page": 146}
        node = p._parse_table_lines(self.LINES, meta)
        assert node["source_method"] == "text"
        assert node["source_page"] == 146
        assert node["headers"] == ["Col A", "Col B"]
        assert node["rows"] == [["1", "2"]]


# ---------------------------------------------------------------------------
# build_ast — consumo del marcador de procedencia
# ---------------------------------------------------------------------------


def _tables_in(ast: dict) -> list[dict]:
    """Tablas en preamble (las líneas de prueba no llevan headings)."""
    return [n for n in ast["preamble"] if n.get("type") == "table"]


class TestBuildAstTableMeta:
    META = {"md_slug": "ley_de_prueba", "nombre": "Ley de Prueba"}

    def test_vector_table_gets_text_provenance(self) -> None:
        lines = p._render_vector_table(
            [["Col A", "Col B"], ["1", "2"]], page_num=146)
        ast = p.build_ast(lines, self.META)
        tables = _tables_in(ast)
        assert len(tables) == 1
        assert tables[0]["source_method"] == "text"
        assert tables[0]["source_page"] == 146
        assert tables[0]["headers"] == ["Col A", "Col B"]
        assert tables[0]["rows"] == [["1", "2"]]

    def test_marker_never_leaks_as_text(self) -> None:
        lines = p._render_vector_table(
            [["Col A", "Col B"], ["1", "2"]], page_num=7)
        ast = p.build_ast(lines, self.META)
        dumped = str(ast)
        assert "mxmd:table" not in dumped

    def test_table_without_marker_keeps_ocr_default(self) -> None:
        lines = ["| Col A | Col B |", "| --- | --- |", "| 1 | 2 |"]
        ast = p.build_ast(lines, self.META)
        tables = _tables_in(ast)
        assert len(tables) == 1
        assert tables[0]["source_method"] == "ocr"
        assert tables[0]["source_page"] is None

    def test_meta_does_not_leak_to_next_table(self) -> None:
        # Tabla vectorial (con marcador) seguida de tabla OCR (sin marcador):
        # la segunda debe conservar el default histórico.
        lines = [
            *p._render_vector_table([["A", "B"], ["1", "2"]], page_num=5),
            "| Col X | Col Y |",
            "| --- | --- |",
            "| 9 | 8 |",
            "",
        ]
        ast = p.build_ast(lines, self.META)
        tables = _tables_in(ast)
        assert len(tables) == 2
        assert tables[0]["source_method"] == "text"
        assert tables[0]["source_page"] == 5
        assert tables[1]["source_method"] == "ocr"
        assert tables[1]["source_page"] is None
