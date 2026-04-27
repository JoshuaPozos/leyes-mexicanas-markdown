"""Tests adicionales de helpers puros de pdf_to_md.

Complementan tests/test_helpers.py cubriendo:
- _is_descriptive_name
- _strip_running_header_inline
- _post_split_incisos
- _is_reform_note / _parse_reform_note
- _parse_table_lines
- _load_catalog_entry (I/O simple sobre catalogo.json)
- parse_args (CLI)
- render_markdown / _render_content / _render_table / _render_node (pure)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pdf_to_md as p
import pytest

# ---------------------------------------------------------------------------
# _is_descriptive_name
# ---------------------------------------------------------------------------


class TestIsDescriptiveName:
    @pytest.mark.parametrize("line", [
        "DISPOSICIONES GENERALES",
        "DEL OBJETO DE LA LEY",
        "DE LA AUTORIDAD COMPETENTE",
    ])
    def test_all_caps_with_long_word(self, line: str) -> None:
        assert p._is_descriptive_name(line) is True

    @pytest.mark.parametrize("line", [
        "De la Violencia Familiar",
        "Del Procedimiento",
        "Sobre Reforma Política",
        "Disposiciones Comunes",
    ])
    def test_title_case_with_descriptive_prefix(self, line: str) -> None:
        assert p._is_descriptive_name(line) is True

    def test_empty_returns_false(self) -> None:
        assert p._is_descriptive_name("") is False
        assert p._is_descriptive_name("   ") is False

    def test_too_long_returns_false(self) -> None:
        long_line = "X" * 101
        assert p._is_descriptive_name(long_line) is False

    def test_starts_with_digit_returns_false(self) -> None:
        assert p._is_descriptive_name("1. Esto no es nombre") is False

    def test_article_heading_returns_false(self) -> None:
        assert p._is_descriptive_name("Artículo 5") is False

    def test_section_heading_returns_false(self) -> None:
        assert p._is_descriptive_name("TÍTULO PRIMERO") is False

    def test_lowercase_paragraph_returns_false(self) -> None:
        assert p._is_descriptive_name("este es un párrafo común") is False


# ---------------------------------------------------------------------------
# _strip_running_header_inline
# ---------------------------------------------------------------------------


class TestStripRunningHeaderInline:
    def test_empty_header_passthrough(self) -> None:
        assert p._strip_running_header_inline("hola", "") == "hola"

    def test_header_not_in_line(self) -> None:
        assert (
            p._strip_running_header_inline("texto normal", "ENCABEZADO REPETIDO")
            == "texto normal"
        )

    def test_strips_when_present(self) -> None:
        result = p._strip_running_header_inline(
            "antes ENCABEZADO después", "ENCABEZADO"
        )
        # Reemplaza por un solo espacio: queda "antes   después"
        # (espacio original + el de reemplazo + espacio original)
        assert "ENCABEZADO" not in result
        assert result == "antes   después"

    def test_strips_outer_whitespace(self) -> None:
        # Si el header está al inicio o final, .strip() elimina los espacios sobrantes
        assert p._strip_running_header_inline("ENCABEZADO texto", "ENCABEZADO") == "texto"
        assert p._strip_running_header_inline("texto ENCABEZADO", "ENCABEZADO") == "texto"


# ---------------------------------------------------------------------------
# _post_split_incisos
# ---------------------------------------------------------------------------


class TestPostSplitIncisos:
    def test_splits_inline_incisos(self) -> None:
        # Línea con incisos que quedaron unidos por la unión de párrafos
        lines = ["Lo siguiente. a) primero. b) segundo. c) tercero."]
        result = p._post_split_incisos(lines)
        # Debe haber al menos 3 fragmentos separados por strings vacíos
        assert any(frag.startswith("a) primero") for frag in result)
        assert any(frag.startswith("b) segundo") for frag in result)
        assert any(frag.startswith("c) tercero") for frag in result)
        # Los fragmentos están separados por cadenas vacías
        assert "" in result

    def test_passes_through_headings(self) -> None:
        lines = ["# Título", "## Subtítulo", "### Artículo 1"]
        assert p._post_split_incisos(lines) == lines

    def test_passes_through_blockquotes(self) -> None:
        lines = ["> placeholder de tabla"]
        assert p._post_split_incisos(lines) == lines

    def test_passes_through_separators(self) -> None:
        lines = ["---"]
        assert p._post_split_incisos(lines) == lines

    def test_passes_through_bold_markers(self) -> None:
        lines = ["**Primero.-** algo"]
        assert p._post_split_incisos(lines) == lines

    def test_no_split_when_no_inline_incisos(self) -> None:
        lines = ["Texto plano sin incisos."]
        assert p._post_split_incisos(lines) == lines

    def test_empty_lines_passthrough(self) -> None:
        lines = ["", "texto", ""]
        result = p._post_split_incisos(lines)
        assert result == ["", "texto", ""]


# ---------------------------------------------------------------------------
# _is_reform_note / _parse_reform_note
# ---------------------------------------------------------------------------


class TestIsReformNote:
    @pytest.mark.parametrize("text", [
        "Párrafo reformado DOF 10-06-2011",
        "Fracción adicionada DOF 01/01/2020",
        "Artículo derogado DOF 15-08-2015",
        "Inciso recorrido DOF 01-02-2020",
        "Capítulo abrogado DOF 12-12-2012",
        "Fe de erratas publicada DOF 03-04-2020",
    ])
    def test_valid_notes(self, text: str) -> None:
        assert p._is_reform_note(text) is True

    def test_no_dof_returns_false(self) -> None:
        assert p._is_reform_note("Párrafo reformado en algún momento") is False

    def test_random_paragraph_returns_false(self) -> None:
        assert p._is_reform_note("DOF aparece pero no hay acción") is False

    def test_empty_returns_false(self) -> None:
        assert p._is_reform_note("") is False


class TestParseReformNote:
    def test_action_reformado(self) -> None:
        node = p._parse_reform_note("Párrafo reformado DOF 10-06-2011")
        assert node["type"] == "reform_note"
        assert node["action"] == "reformado"
        assert node["dof_date"] == "10-06-2011"

    def test_action_adicionado(self) -> None:
        node = p._parse_reform_note("Fracción adicionada DOF 01-01-2020")
        assert node["action"] == "adicionado"

    def test_action_derogado(self) -> None:
        node = p._parse_reform_note("Artículo derogado DOF 15-08-2015")
        assert node["action"] == "derogado"

    def test_action_recorrido(self) -> None:
        node = p._parse_reform_note("Inciso recorrido DOF 01-02-2020")
        assert node["action"] == "recorrido"

    def test_action_abrogado(self) -> None:
        node = p._parse_reform_note("Capítulo abrogado DOF 12-12-2012")
        assert node["action"] == "abrogado"

    def test_action_fe_de_erratas(self) -> None:
        node = p._parse_reform_note("Fe de erratas DOF 03-04-2020")
        assert node["action"] == "fe_de_erratas"

    def test_no_action_match(self) -> None:
        # Texto sin verbo de acción reconocido
        node = p._parse_reform_note("Texto raro sin acción")
        assert node["action"] is None

    def test_takes_last_dof_date(self) -> None:
        node = p._parse_reform_note(
            "Párrafo reformado DOF 01-01-2010 y luego DOF 02-02-2020"
        )
        assert node["dof_date"] == "02-02-2020"

    def test_normalizes_slashes_to_dashes(self) -> None:
        node = p._parse_reform_note("Párrafo reformado DOF 11/03/2024")
        assert node["dof_date"] == "11-03-2024"

    def test_no_date_returns_none(self) -> None:
        node = p._parse_reform_note("Párrafo reformado")
        assert node["dof_date"] is None


# ---------------------------------------------------------------------------
# _parse_table_lines
# ---------------------------------------------------------------------------


class TestParseTableLines:
    def test_basic_table(self) -> None:
        lines = [
            "| col1 | col2 |",
            "| --- | --- |",
            "| a | b |",
            "| c | d |",
        ]
        result = p._parse_table_lines(lines)
        assert result["type"] == "table"
        assert result["headers"] == ["col1", "col2"]
        assert result["rows"] == [["a", "b"], ["c", "d"]]

    def test_skips_separator_row(self) -> None:
        lines = ["| h |", "| --- |", "| v |"]
        result = p._parse_table_lines(lines)
        assert result["headers"] == ["h"]
        assert result["rows"] == [["v"]]

    def test_no_data_rows(self) -> None:
        lines = ["| h |", "| --- |"]
        result = p._parse_table_lines(lines)
        assert result["headers"] == ["h"]
        assert result["rows"] == []


# ---------------------------------------------------------------------------
# _load_catalog_entry
# ---------------------------------------------------------------------------


class TestLoadCatalogEntry:
    def test_returns_empty_when_catalog_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Apuntar el path "raíz" al tmp_path (no existe catalogo.json en él)
        monkeypatch.setattr(
            p, "__file__", str(tmp_path / "scripts" / "pdf_to_md.py")
        )
        # Crear scripts dir
        (tmp_path / "scripts").mkdir()
        result = p._load_catalog_entry(tmp_path / "anything.pdf")
        assert result == {}

    def test_finds_by_pdf_filename(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        monkeypatch.setattr(p, "__file__", str(scripts / "pdf_to_md.py"))

        catalog = [
            {"pdf_filename": "ley_a.pdf", "nombre": "Ley A", "md_slug": "LA_a"},
            {"pdf_filename": "ley_b.pdf", "nombre": "Ley B", "md_slug": "LB_b"},
        ]
        (tmp_path / "catalogo.json").write_text(
            json.dumps(catalog), encoding="utf-8"
        )

        result = p._load_catalog_entry(tmp_path / "ley_a.pdf")
        assert result["nombre"] == "Ley A"

    def test_falls_back_to_md_slug(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        monkeypatch.setattr(p, "__file__", str(scripts / "pdf_to_md.py"))

        catalog = [
            {"pdf_filename": "x.pdf", "md_slug": "LX_my_law", "nombre": "Mi Ley"},
        ]
        (tmp_path / "catalogo.json").write_text(
            json.dumps(catalog), encoding="utf-8"
        )

        # El nombre del archivo no es x.pdf, pero su stem coincide con md_slug
        result = p._load_catalog_entry(tmp_path / "LX_my_law.pdf")
        assert result["nombre"] == "Mi Ley"

    def test_returns_empty_when_no_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        monkeypatch.setattr(p, "__file__", str(scripts / "pdf_to_md.py"))

        (tmp_path / "catalogo.json").write_text("[]", encoding="utf-8")

        result = p._load_catalog_entry(tmp_path / "huerfano.pdf")
        assert result == {}


# ---------------------------------------------------------------------------
# parse_args (CLI)
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_minimal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["pdf_to_md.py", "input.pdf"])
        args = p.parse_args()
        assert args.pdf == Path("input.pdf")
        assert args.output is None
        assert args.title is None
        assert args.verbose is False
        assert args.canonical_dir is None
        assert args.format == "both"
        assert args.validate is False

    def test_all_options(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "pdf_to_md.py",
                "in.pdf",
                "-o",
                "out.md",
                "-t",
                "Mi Ley",
                "-v",
                "-c",
                "canonical/",
                "--format",
                "json",
                "--validate",
            ],
        )
        args = p.parse_args()
        assert args.pdf == Path("in.pdf")
        assert args.output == Path("out.md")
        assert args.title == "Mi Ley"
        assert args.verbose is True
        assert args.canonical_dir == Path("canonical/")
        assert args.format == "json"
        assert args.validate is True

    def test_invalid_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sys, "argv", ["pdf_to_md.py", "x.pdf", "--format", "yaml"]
        )
        with pytest.raises(SystemExit):
            p.parse_args()


# ---------------------------------------------------------------------------
# render_markdown / _render_content / _render_table / _render_node
# ---------------------------------------------------------------------------


class TestRenderTable:
    def test_renders_full_table(self) -> None:
        lines: list[str] = []
        table = {
            "title": "Tarifa",
            "headers": ["col1", "col2"],
            "rows": [["a", "b"], ["c", "d"]],
        }
        p._render_table(table, lines)
        # Debe haber título en negritas, encabezado, separador, y dos filas
        assert "**Tarifa**" in lines
        assert "| col1 | col2 |" in lines
        assert "| --- | --- |" in lines
        assert "| a | b |" in lines

    def test_renders_without_title(self) -> None:
        lines: list[str] = []
        p._render_table(
            {"headers": ["h"], "rows": [["v"]]}, lines
        )
        # No hay línea con **None** ni con doble asterisco vacío
        assert all(not (line.startswith("**") and line.endswith("**"))
                   for line in lines)
        assert "| h |" in lines

    def test_empty_table(self) -> None:
        lines: list[str] = []
        p._render_table({"headers": [], "rows": []}, lines)
        # Solo se añaden las dos líneas vacías de padding
        assert lines == ["", ""]


class TestRenderContent:
    def test_paragraph(self) -> None:
        lines: list[str] = []
        p._render_content([{"type": "paragraph", "text": "Hola mundo."}], lines)
        assert lines == ["Hola mundo."]

    def test_fraccion_with_blank_line_separator(self) -> None:
        lines: list[str] = []
        p._render_content(
            [
                {"type": "paragraph", "text": "Intro."},
                {"type": "fraccion", "ordinal": "I", "text": "primera"},
                {"type": "fraccion", "ordinal": "II", "text": "segunda"},
            ],
            lines,
        )
        assert lines[0] == "Intro."
        assert lines[1] == ""  # separator antes de I
        assert lines[2] == "I. primera"
        assert lines[3] == ""
        assert lines[4] == "II. segunda"

    def test_inciso(self) -> None:
        lines: list[str] = []
        p._render_content(
            [
                {"type": "paragraph", "text": "Antes."},
                {"type": "inciso", "ordinal": "a", "text": "uno"},
            ],
            lines,
        )
        assert "a) uno" in lines

    def test_reform_note(self) -> None:
        lines: list[str] = []
        p._render_content(
            [{"type": "reform_note", "text": "Párrafo reformado DOF 10-06-2011"}],
            lines,
        )
        assert lines == ["Párrafo reformado DOF 10-06-2011"]

    def test_table(self) -> None:
        lines: list[str] = []
        p._render_content(
            [{"type": "table", "headers": ["h"], "rows": [["v"]]}],
            lines,
        )
        assert "| h |" in lines


class TestRenderNode:
    def test_titulo_node(self) -> None:
        lines: list[str] = []
        p._render_node(
            {
                "type": "titulo",
                "heading": "TÍTULO PRIMERO",
                "descriptor": "Disposiciones Generales",
                "content": [],
                "children": [],
            },
            lines,
        )
        assert any(
            "## TÍTULO PRIMERO — Disposiciones Generales" in ln for ln in lines
        )

    def test_titulo_without_descriptor(self) -> None:
        lines: list[str] = []
        p._render_node(
            {
                "type": "titulo",
                "heading": "TÍTULO ÚNICO",
                "content": [],
                "children": [],
            },
            lines,
        )
        assert any(ln == "## TÍTULO ÚNICO" for ln in lines)

    def test_articulo_node(self) -> None:
        lines: list[str] = []
        p._render_node(
            {
                "type": "articulo",
                "heading": "Artículo 5",
                "content": [{"type": "paragraph", "text": "Las personas..."}],
                "children": [],
            },
            lines,
        )
        assert "### Artículo 5" in lines
        assert "Las personas..." in lines

    def test_transitorio_articulo_with_ordinal(self) -> None:
        lines: list[str] = []
        p._render_node(
            {
                "type": "transitorio_articulo",
                "heading": "Primero",
                "ordinal": "Primero",
                "content": [{"type": "paragraph", "text": "Esta ley entra..."}],
                "children": [],
            },
            lines,
        )
        # Formato **Ordinal.-** texto
        assert any(ln.startswith("**Primero.-**") for ln in lines)

    def test_transitorio_articulo_with_articulo_heading(self) -> None:
        lines: list[str] = []
        p._render_node(
            {
                "type": "transitorio_articulo",
                "heading": "ARTÍCULO PRIMERO",
                "ordinal": "Primero",
                "content": [],
                "children": [],
            },
            lines,
        )
        assert "### ARTÍCULO PRIMERO" in lines

    def test_transitorio_articulo_ordinal_without_content(self) -> None:
        lines: list[str] = []
        p._render_node(
            {
                "type": "transitorio_articulo",
                "heading": "Primero",
                "ordinal": "Primero",
                "content": [],
                "children": [],
            },
            lines,
        )
        # Sin contenido, queda solo el bold
        assert "**Primero.-**" in lines

    def test_renders_children_recursively(self) -> None:
        lines: list[str] = []
        p._render_node(
            {
                "type": "capitulo",
                "heading": "CAPÍTULO I",
                "content": [],
                "children": [
                    {
                        "type": "articulo",
                        "heading": "Artículo 1",
                        "content": [
                            {"type": "paragraph", "text": "Contenido."},
                        ],
                        "children": [],
                    }
                ],
            },
            lines,
        )
        assert "## CAPÍTULO I" in lines
        assert "### Artículo 1" in lines
        assert "Contenido." in lines


class TestRenderMarkdown:
    def test_minimal_ast(self) -> None:
        ast = {"name": "Mi Ley", "preamble": [], "structure": []}
        lines = p.render_markdown(ast)
        assert lines[0] == "# Mi Ley"
        assert any("diputados.gob.mx" in ln for ln in lines)

    def test_with_preamble_and_structure(self) -> None:
        ast = {
            "name": "Ley X",
            "preamble": [{"type": "paragraph", "text": "Preámbulo aquí."}],
            "structure": [
                {
                    "type": "articulo",
                    "heading": "Artículo 1",
                    "content": [
                        {"type": "paragraph", "text": "Texto del artículo."}
                    ],
                    "children": [],
                }
            ],
        }
        lines = p.render_markdown(ast)
        joined = "\n".join(lines)
        assert "# Ley X" in joined
        assert "Preámbulo aquí." in joined
        assert "### Artículo 1" in joined
        assert "Texto del artículo." in joined

    def test_missing_name_uses_empty_string(self) -> None:
        lines = p.render_markdown({"preamble": [], "structure": []})
        assert lines[0] == "# "
