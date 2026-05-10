"""Tests de helpers puros de download_leyes (parsing, slugify, acrónimos)."""

from __future__ import annotations

import download_leyes as dl
import pytest

# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    @pytest.mark.parametrize("raw,expected", [
        ("Hola Mundo", "hola_mundo"),
        ("Constitución Política", "constitucion_politica"),
        ("LEY DEL ISR", "ley_del_isr"),
        ("Año 2026", "ano_2026"),
        ("a-b-c", "a_b_c"),
    ])
    def test_basic(self, raw: str, expected: str) -> None:
        assert dl.slugify(raw) == expected

    def test_strips_accents(self) -> None:
        assert dl.slugify("Código Civil Federal") == "codigo_civil_federal"

    def test_collapses_separators(self) -> None:
        assert dl.slugify("a   b") == "a_b"
        assert dl.slugify("a___b") == "a_b"

    def test_truncates_to_max_len(self) -> None:
        long_text = "una palabra larga que debe truncarse en algun punto exacto del nombre"
        result = dl.slugify(long_text, max_len=20)
        assert len(result) <= 20

    def test_no_trailing_underscore_after_truncate(self) -> None:
        # Si el truncado cae en un separador, se hace rstrip
        result = dl.slugify("aa bb cc dd", max_len=5)
        assert not result.endswith("_")


# ---------------------------------------------------------------------------
# derive_acronym
# ---------------------------------------------------------------------------

class TestDeriveAcronym:
    def test_estatuto_gobierno(self) -> None:
        result = dl.derive_acronym("ESTATUTO de Gobierno del Distrito Federal")
        assert result == "EGDF"

    def test_filters_stop_words(self) -> None:
        # "de", "del", "la" se filtran
        result = dl.derive_acronym("Ley del Impuesto sobre la Renta")
        assert result == "LIR"

    def test_truncates_to_max_len(self) -> None:
        long_name = "Alfa Beta Gamma Delta Épsilon Zeta Eta Theta Iota"
        result = dl.derive_acronym(long_name, max_len=4)
        assert len(result) == 4

    def test_takes_only_main_clause(self) -> None:
        # Solo antes de la primera coma o paréntesis
        result = dl.derive_acronym("Constitución Política, reformada en 2024")
        assert result == "CP"

    def test_fallback_when_empty(self) -> None:
        # Sin letras válidas → fallback "LEY"
        assert dl.derive_acronym("") == "LEY"
        assert dl.derive_acronym(",") == "LEY"


# ---------------------------------------------------------------------------
# parse_law_name
# ---------------------------------------------------------------------------

class TestParseLawName:
    def test_simple_with_dof(self) -> None:
        nombre, dof = dl.parse_law_name("Ley del ISR DOF 11/12/2013")
        assert nombre == "Ley del ISR"
        assert "DOF" in dof and "11/12/2013" in dof

    def test_strips_nueva_reforma_suffix(self) -> None:
        nombre, _ = dl.parse_law_name("CONSTITUCIÓN Política Nueva reforma DOF05/02/1917")
        assert "Nueva reforma" not in nombre

    def test_no_dof_returns_empty_dof(self) -> None:
        nombre, dof = dl.parse_law_name("Sin fecha")
        assert nombre == "Sin fecha"
        assert dof == ""

    def test_drops_parenthetical_after_dof(self) -> None:
        # El paréntesis tras la fecha no debe quedar en dof_date
        _, dof = dl.parse_law_name("Ley X DOF 01/01/2020 (Abrogada)")
        assert "(" not in dof


# ---------------------------------------------------------------------------
# compute_md_slug
# ---------------------------------------------------------------------------

class TestComputeMdSlug:
    def test_uses_pdf_stem_as_acronym_when_short(self) -> None:
        # Si el pdf_stem es corto y todo en mayúsculas, se usa como acrónimo
        result = dl.compute_md_slug("CPEUM", "Constitución Política", "001")
        assert result.startswith("CPEUM_")

    def test_derives_acronym_from_numeric_stem(self) -> None:
        # Si el stem es numérico, se deriva del nombre
        result = dl.compute_md_slug("123", "Ley del Impuesto sobre la Renta", "045")
        # debe arrancar con un acrónimo de letras, no con "123"
        prefix = result.split("_", 1)[0]
        assert prefix.isupper()
        assert prefix != "123"

    def test_slug_has_acronym_underscore_slug(self) -> None:
        result = dl.compute_md_slug("CPEUM", "Constitución Política", "001")
        # formato: ABREV_nombre_snake
        parts = result.split("_", 1)
        assert len(parts) == 2
