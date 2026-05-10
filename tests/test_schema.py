"""Tests para schema/law_ast.schema.json — patrones y constraints endurecidos."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "schema" / "law_ast.schema.json"
EXAMPLE_PATH = ROOT / "schema" / "example_cpeum_fragment.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema: dict) -> jsonschema.Draft7Validator:
    return jsonschema.Draft7Validator(schema)


def _minimal_doc() -> dict:
    """Documento canónico mínimo aceptable por el schema."""
    return {
        "schema_version": "1.0.0",
        "id": "CPEUM_constitucion_politica",
        "name": "Constitución",
        "source": {
            "pdf_url": "https://www.diputados.gob.mx/x.pdf",
            "captured_at": "2026-05-10T00:00:00Z",
        },
        "structure": [],
    }


class TestSchemaItself:
    def test_schema_loads_and_is_valid_draft7(self, schema: dict) -> None:
        jsonschema.Draft7Validator.check_schema(schema)

    def test_minimal_document_is_valid(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        assert list(validator.iter_errors(_minimal_doc())) == []

    def test_example_cpeum_fragment_is_valid(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        errs = list(validator.iter_errors(example))
        assert errs == [], "Example fragment debe validar contra el schema"


class TestRootIdPattern:
    def test_accepts_real_slugs(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        for sid in [
            "CPEUM_constitucion_politica_de_los_estados_unidos_mexicanos",
            "LISR_ley_del_impuesto_sobre_la_renta",
            "CCom_codigo_de_comercio",
            "LRArt3_MMCE_ley_reglamentaria",
        ]:
            doc = _minimal_doc()
            doc["id"] = sid
            assert list(validator.iter_errors(doc)) == [], f"Debió aceptar {sid}"

    def test_rejects_id_with_space(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = _minimal_doc()
        doc["id"] = "CPEUM con espacios"
        errs = list(validator.iter_errors(doc))
        assert errs and any("id" in list(e.absolute_path) for e in errs)

    def test_rejects_id_starting_with_digit(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = _minimal_doc()
        doc["id"] = "1invalid_start"
        errs = list(validator.iter_errors(doc))
        assert errs and any("id" in list(e.absolute_path) for e in errs)


class TestNodeIdPattern:
    def _doc_with_node_id(self, nid: str) -> dict:
        doc = _minimal_doc()
        doc["structure"] = [{
            "type": "titulo", "id": nid, "content": [], "children": [],
        }]
        return doc

    def test_accepts_dotted_paths(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        for nid in [
            "titulo-1",
            "titulo-primero.capitulo-i",
            "titulo-1.capitulo-2.articulo-15",
            "transitorios",
            "transitorios.transitorio_articulo-primero",
        ]:
            doc = self._doc_with_node_id(nid)
            assert list(validator.iter_errors(doc)) == [], f"Debió aceptar {nid}"

    def test_rejects_uppercase(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_node_id("Titulo-1")
        assert list(validator.iter_errors(doc))

    def test_rejects_node_id_with_space(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_node_id("titulo 1")
        assert list(validator.iter_errors(doc))

    def test_rejects_trailing_dot(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_node_id("titulo-1.")
        assert list(validator.iter_errors(doc))


class TestOrdinalPatterns:
    def _doc_with_content(self, elements: list[dict]) -> dict:
        doc = _minimal_doc()
        doc["structure"] = [{
            "type": "articulo", "id": "art-1",
            "content": elements, "children": [],
        }]
        return doc

    def test_fraccion_accepts_roman_numeral(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_content([
            {"type": "fraccion", "ordinal": "XXIX", "text": "x"},
        ])
        assert list(validator.iter_errors(doc)) == []

    def test_fraccion_accepts_roman_with_suffix(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_content([
            {"type": "fraccion", "ordinal": "XXIX-A", "text": "x"},
        ])
        assert list(validator.iter_errors(doc)) == []

    def test_fraccion_rejects_arabic_numeral(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_content([
            {"type": "fraccion", "ordinal": "29", "text": "x"},
        ])
        assert list(validator.iter_errors(doc))

    def test_inciso_accepts_single_lowercase(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_content([
            {"type": "inciso", "ordinal": "a", "text": "x"},
        ])
        assert list(validator.iter_errors(doc)) == []

    def test_inciso_rejects_uppercase(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_content([
            {"type": "inciso", "ordinal": "A", "text": "x"},
        ])
        assert list(validator.iter_errors(doc))

    def test_apartado_accepts_single_uppercase(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_content([
            {"type": "apartado", "ordinal": "A", "text": "x"},
        ])
        assert list(validator.iter_errors(doc)) == []

    def test_apartado_rejects_lowercase(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_content([
            {"type": "apartado", "ordinal": "a", "text": "x"},
        ])
        assert list(validator.iter_errors(doc))


class TestReformNoteConstraints:
    def _doc_with_reform_note(self, note: dict) -> dict:
        doc = _minimal_doc()
        doc["structure"] = [{
            "type": "articulo", "id": "art-1",
            "content": [note], "children": [],
        }]
        return doc

    def test_accepts_valid_dof_date_dash(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_reform_note({
            "type": "reform_note", "text": "x",
            "action": "reformado", "dof_date": "10-06-2011",
        })
        assert list(validator.iter_errors(doc)) == []

    def test_accepts_valid_dof_date_slash(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_reform_note({
            "type": "reform_note", "text": "x",
            "action": "reformado", "dof_date": "30/09/2024",
        })
        assert list(validator.iter_errors(doc)) == []

    def test_rejects_malformed_dof_date(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_reform_note({
            "type": "reform_note", "text": "x",
            "action": "reformado", "dof_date": "2024-09-30",
        })
        assert list(validator.iter_errors(doc))

    def test_dof_date_null_is_allowed(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_reform_note({
            "type": "reform_note", "text": "x", "dof_date": None,
        })
        assert list(validator.iter_errors(doc)) == []

    def test_rejects_unknown_action(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = self._doc_with_reform_note({
            "type": "reform_note", "text": "x", "action": "invented",
        })
        assert list(validator.iter_errors(doc))


class TestPreambleMinItems:
    def test_present_preamble_must_have_items(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = _minimal_doc()
        doc["preamble"] = []
        errs = list(validator.iter_errors(doc))
        # Algún error apunta a preamble (minItems lo viola)
        assert any("preamble" in list(e.absolute_path) for e in errs)

    def test_preamble_can_be_omitted(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        # Si la clave no está, no se valida minItems (preamble es opcional).
        doc = _minimal_doc()
        assert "preamble" not in doc
        assert list(validator.iter_errors(doc)) == []


class TestRegressionAgainstRealCanonicals:
    """Validar que un subset representativo de los 315 JSONs reales sigue
    pasando contra el schema endurecido. Red de seguridad contra cambios
    sutiles al schema. La validación completa de los 315 se hace en el
    smoke test fuera del test suite (corre en ~2 min)."""

    SAMPLE_SIZE = 20

    def test_sample_of_canonical_files_validates(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        canonical_dir = ROOT / "canonical"
        files = sorted(canonical_dir.glob("*.json"))
        if not files:
            pytest.skip("No hay canonical/*.json para validar")

        # Muestreo determinista: paso uniforme sobre la lista ordenada
        step = max(1, len(files) // self.SAMPLE_SIZE)
        sample = files[::step][: self.SAMPLE_SIZE]

        fails = []
        for f in sample:
            doc = json.loads(f.read_text(encoding="utf-8"))
            errs = list(validator.iter_errors(doc))
            if errs:
                fails.append((f.name, [e.message[:120] for e in errs[:2]]))
        assert not fails, f"Archivos que fallan: {fails[:5]}"


def _without_field(doc: dict, *path: str) -> dict:
    """Devuelve copia del doc sin el campo en `path` (para tests de required)."""
    new = copy.deepcopy(doc)
    cursor: object = new
    for key in path[:-1]:
        cursor = cursor[key]  # type: ignore[index]
    del cursor[path[-1]]  # type: ignore[index]
    return new


class TestRequiredFields:
    def test_missing_schema_version_fails(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = _without_field(_minimal_doc(), "schema_version")
        assert any(
            "required" in e.message or "schema_version" in e.message
            for e in validator.iter_errors(doc)
        )

    def test_wrong_schema_version_fails(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = _minimal_doc()
        doc["schema_version"] = "0.9.0"
        assert any(
            "const" in e.message or "1.0.0" in e.message
            for e in validator.iter_errors(doc)
        )

    def test_source_requires_captured_at(
        self, validator: jsonschema.Draft7Validator
    ) -> None:
        doc = _without_field(_minimal_doc(), "source", "captured_at")
        assert any(
            "captured_at" in e.message for e in validator.iter_errors(doc)
        )
