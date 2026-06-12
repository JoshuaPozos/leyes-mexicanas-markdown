"""Tests del reconstructor de tablas OCR (`_build_table_from_spatial`).

Cubren las correcciones de la auditoría de calidad OCR (2026-06-11):
- _ocr_rows_as_text — sanitización de pipes en texto plano (CR-6: el
  sniffer de build_ast fabricaba pseudo-tablas de líneas que empiezan
  con '|').
- Guardia de plausibilidad — reconstrucciones con muy pocas filas de
  datos o demasiadas columnas emiten el marcador honesto "[Tabla no
  extraíble]" + texto plano, no basura estructurada.
- Marcador de procedencia src=ocr con página (consumido por build_ast →
  source_method='ocr', source_page=N).
- build_ast descarta nodos tabla sin filas de datos.
"""

from __future__ import annotations

import pdf_to_md as p
from constants import OCR_TABLE_MAX_COLS

# ---------------------------------------------------------------------------
# Helpers: construir el dict espacial que devuelve pytesseract.image_to_data
# ---------------------------------------------------------------------------

ROW_HEIGHT = 40  # separación vertical entre filas (>> OCR_ROW_TOLERANCE)
COL_WIDTH = 100  # separación horizontal entre columnas


def _spatial(rows: list[list[str]]) -> dict:
    """Convierte filas de tokens en el dict {text, conf, left, top, ...}
    que produce Tesseract, con una rejilla regular de posiciones."""
    data: dict = {"text": [], "conf": [], "left": [], "top": [],
                  "width": [], "height": []}
    for r, row in enumerate(rows):
        for c, token in enumerate(row):
            data["text"].append(token)
            data["conf"].append(90)
            data["left"].append(c * COL_WIDTH)
            data["top"].append(r * ROW_HEIGHT)
            data["width"].append(50)
            data["height"].append(12)
    return data


# ---------------------------------------------------------------------------
# _ocr_rows_as_text
# ---------------------------------------------------------------------------


class TestOcrRowsAsText:
    def test_pipes_are_removed(self) -> None:
        rows = [[{"text": "|"}, {"text": "16]0.63|"}, {"text": "ruido"}]]
        lines = p._ocr_rows_as_text(rows)  # type: ignore[arg-type]
        assert lines == ["16]0.63 ruido"]
        assert not any(ln.startswith("|") for ln in lines)

    def test_empty_rows_dropped(self) -> None:
        rows = [[{"text": "|"}], [{"text": "hola"}]]
        lines = p._ocr_rows_as_text(rows)  # type: ignore[arg-type]
        assert lines == ["hola"]


# ---------------------------------------------------------------------------
# _build_table_from_spatial — guardia de plausibilidad y procedencia
# ---------------------------------------------------------------------------


class TestBuildTableGuard:
    def test_valid_table_emits_marker_and_rows(self) -> None:
        data = _spatial([
            ["Concepto", "Monto", "Tasa"],
            ["100", "200", "1.5%"],
            ["300", "400", "2.5%"],
        ])
        md = p._build_table_from_spatial(data, page_num=53)
        assert "<!--mxmd:table src=ocr page=53-->" in md
        table_rows = [ln for ln in md if ln.startswith("|")]
        # header + separador + 2 filas de datos
        assert len(table_rows) == 4
        assert "| 100 | 200 | 1.5% |" in md

    def test_single_data_row_falls_to_honest_marker(self) -> None:
        # 1 sola fila de datos reconstruida = la tabla real colapsó →
        # marcador honesto + texto plano, nunca tabla de 1 fila
        data = _spatial([
            ["Puesto", "Nivel", "Sueldo"],
            ["111,423", "137,582", "191,657"],
        ])
        md = p._build_table_from_spatial(data, page_num=79)
        assert any("[Tabla no extraíble — ver PDF original, página 79]" in ln
                   for ln in md)
        assert not any(ln.startswith("|") for ln in md)
        # El contenido OCR sobrevive como texto plano (greppable)
        assert any("111,423" in ln for ln in md)

    def test_too_many_columns_fall_to_honest_marker(self) -> None:
        # target_cols > OCR_TABLE_MAX_COLS = filas machacadas como columnas
        n = OCR_TABLE_MAX_COLS + 1
        wide_row_1 = [str(100 + i) for i in range(n)]
        wide_row_2 = [str(200 + i) for i in range(n)]
        data = _spatial([wide_row_1, wide_row_2])
        md = p._build_table_from_spatial(data, page_num=80)
        assert any("[Tabla no extraíble" in ln for ln in md)
        assert not any(ln.startswith("|") for ln in md)

    def test_no_numeric_rows_plain_text_without_pipes(self) -> None:
        # Texto sin estructura (partituras LEBHN, listas simples):
        # texto plano sanitizado, sin marcador y sin fabricar tablas
        data = _spatial([
            ["|", "Me-xi-ca-nos", "al"],
            ["|", "gri-to", "de", "gue-rra"],
        ])
        md = p._build_table_from_spatial(data, page_num=19)
        assert not any(ln.startswith("|") for ln in md)
        assert not any("[Tabla no extraíble" in ln for ln in md)
        assert any("Me-xi-ca-nos" in ln for ln in md)

    def test_empty_input_returns_empty(self) -> None:
        assert p._build_table_from_spatial(_spatial([]), page_num=1) == []


# ---------------------------------------------------------------------------
# build_ast — marcador src=ocr y descarte de nodos sin filas
# ---------------------------------------------------------------------------

META = {"md_slug": "ley_de_prueba", "nombre": "Ley de Prueba"}


def _tables_in(ast: dict) -> list[dict]:
    return [n for n in ast["preamble"] if n.get("type") == "table"]


class TestBuildAstOcrMeta:
    def test_ocr_marker_sets_provenance(self) -> None:
        lines = [
            "<!--mxmd:table src=ocr page=88-->",
            "| Col A | Col B |",
            "| --- | --- |",
            "| 1 | 2 |",
            "",
        ]
        ast = p.build_ast(lines, META)
        tables = _tables_in(ast)
        assert len(tables) == 1
        assert tables[0]["source_method"] == "ocr"
        assert tables[0]["source_page"] == 88

    def test_rowless_table_node_is_dropped(self) -> None:
        # Artefactos OCR (headers-basura sin cuerpo, nodos vacíos) no
        # deben llegar al AST
        lines = [
            "| es | basura |",
            "| --- | --- |",
            "",
            "párrafo normal",
            "",
        ]
        ast = p.build_ast(lines, META)
        assert _tables_in(ast) == []

    def test_single_row_vector_table_survives(self) -> None:
        # La tabla de una fila del flujo vectorial (headers vacíos + 1
        # fila de datos) SÍ es válida y conserva su procedencia
        lines = p._render_vector_table([["524", "100%"]], page_num=245)
        ast = p.build_ast(lines, META)
        tables = _tables_in(ast)
        assert len(tables) == 1
        assert tables[0]["headers"] == ["", ""]
        assert tables[0]["rows"] == [["524", "100%"]]
        assert tables[0]["source_method"] == "text"
        assert tables[0]["source_page"] == 245
