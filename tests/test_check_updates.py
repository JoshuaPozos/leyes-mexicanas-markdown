"""Tests de la detección de deltas upstream (F1).

Cubre la llave de join (_state_key), el diff puro (diff_catalog) con sus casos
no-DOF, y los subcomandos init_snapshot / run_check — todo sin red (fetch_index
mockeado) y con STATE_PATH/CATALOG_PATH aislados en tmp."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import download_leyes as dl
import pytest


def _law(origen: str, slug: str, reforma: str, sha: str | None = None) -> dict:
    """Construye una ley con la forma que devuelve fetch_index()."""
    law = {
        "numero": "1",
        "nombre": f"Ley {slug}",
        "dof": "DOF 01/01/2000",
        "ultima_reforma": reforma,
        "pdf_url": f"https://www.diputados.gob.mx/LeyesBiblio/pdf/{origen}",
        "pdf_filename": f"{slug}.pdf",
        "pdf_filename_origen": origen,
        "md_slug": slug,
    }
    if sha is not None:
        law["sha256"] = sha
    return law


def _entry(key: str, reforma: str) -> dict:
    """Entrada de estado mínima para diff_catalog."""
    return {
        "key": key,
        "md_slug": key.upper(),
        "pdf_url": "u",
        "ultima_reforma_raw": reforma,
    }


# ---------------------------------------------------------------------------
# _state_key
# ---------------------------------------------------------------------------


class TestStateKey:
    def test_plain_acronym(self) -> None:
        assert dl._state_key(_law("CPEUM.pdf", "X", "")) == "cpeum"

    def test_strips_year_suffix(self) -> None:
        assert dl._state_key(_law("LIF_2026.pdf", "X", "")) == "lif"

    def test_strips_dof_date_suffix(self) -> None:
        assert dl._state_key(_law("LCEC_120419.pdf", "X", "")) == "lcec"

    def test_numeric_stem_with_date(self) -> None:
        assert dl._state_key(_law("10_270614.pdf", "X", "")) == "10"

    def test_prefers_ref_abbrev_over_numeric_stem(self) -> None:
        # PDF renombrado de código numérico a acrónimo: ref_abbrev gana.
        law = _law("28.pdf", "X", "")
        law["ref_abbrev"] = "lce"
        assert dl._state_key(law) == "lce"

    def test_strips_year_from_ref_abbrev(self) -> None:
        # Anuales: el ref conserva el año (lif_2026) pero la llave lo colapsa.
        law = _law("LIF_2026.pdf", "X", "")
        law["ref_abbrev"] = "lif_2026"
        assert dl._state_key(law) == "lif"

    def test_falls_back_to_stem_without_ref(self) -> None:
        law = _law("CPEUM.pdf", "X", "")
        law["ref_abbrev"] = ""
        assert dl._state_key(law) == "cpeum"


# ---------------------------------------------------------------------------
# diff_catalog
# ---------------------------------------------------------------------------


class TestDiffCatalog:
    def test_identical_is_empty(self) -> None:
        old = [_entry("a", "DOF 01/01/2025")]
        new = [_entry("a", "DOF 01/01/2025")]
        assert dl.diff_catalog(old, new) == {"changed": [], "added": [], "removed": []}

    def test_changed_dof_date(self) -> None:
        old = [_entry("a", "DOF 01/01/2025")]
        new = [_entry("a", "DOF 14/11/2025")]
        diff = dl.diff_catalog(old, new)
        assert [c["key"] for c in diff["changed"]] == ["a"]
        assert diff["changed"][0]["from"] == "DOF 01/01/2025"
        assert diff["changed"][0]["to"] == "DOF 14/11/2025"

    def test_added(self) -> None:
        diff = dl.diff_catalog([], [_entry("b", "DOF 01/01/2025")])
        assert [a["key"] for a in diff["added"]] == ["b"]

    def test_removed(self) -> None:
        diff = dl.diff_catalog([_entry("c", "DOF 01/01/2025")], [])
        assert [r["key"] for r in diff["removed"]] == ["c"]

    def test_scjn_string_change(self) -> None:
        old = [_entry("a", "Notificación 17/06/2025 Sentencia SCJN")]
        new = [_entry("a", "Notificación 20/08/2025 Sentencia SCJN")]
        assert [c["key"] for c in dl.diff_catalog(old, new)["changed"]] == ["a"]

    def test_sin_reforma_to_dof(self) -> None:
        old = [_entry("a", "Sin reforma")]
        new = [_entry("a", "DOF 14/11/2025")]
        assert [c["key"] for c in dl.diff_catalog(old, new)["changed"]] == ["a"]

    def test_whitespace_only_diff_is_not_change(self) -> None:
        old = [_entry("a", "DOF  14/11/2025")]
        new = [_entry("a", "DOF 14/11/2025 ")]
        assert dl.diff_catalog(old, new)["changed"] == []

    def test_results_sorted_by_key(self) -> None:
        old = [_entry("z", "x"), _entry("m", "x")]
        new = [_entry("b", "x"), _entry("a", "x")]
        diff = dl.diff_catalog(old, new)
        assert [a["key"] for a in diff["added"]] == ["a", "b"]
        assert [r["key"] for r in diff["removed"]] == ["m", "z"]


# ---------------------------------------------------------------------------
# init_snapshot / run_check (sin red)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(dl, "STATE_PATH", tmp_path / "estado.json")
    monkeypatch.setattr(dl, "CATALOG_PATH", tmp_path / "catalogo.json")
    return tmp_path


def _enough_laws(n: int = dl.MIN_SANE_LAW_COUNT) -> list[dict]:
    return [_law(f"L{i}.pdf", f"L{i}", "DOF 01/01/2025") for i in range(n)]


class TestInitSnapshot:
    def test_writes_state_with_keys_and_date(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = [_law("CPEUM.pdf", "CPEUM_x", "DOF 03/03/2026", "a" * 64)]
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        data = json.loads((isolate_state / "estado.json").read_text(encoding="utf-8"))
        assert len(data) == 1
        entry = data[0]
        assert entry["key"] == "cpeum"
        assert entry["ultima_reforma_raw"] == "DOF 03/03/2026"
        assert entry["pdf_sha256"] == "a" * 64
        assert "snapshot_date" in entry


class TestRunCheck:
    def test_missing_state_returns_2(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # fetch_index ni siquiera debe llamarse si no hay estado
        monkeypatch.setattr(
            dl, "fetch_index", lambda: pytest.fail("no debe fetchear sin estado")
        )
        assert dl.run_check() == 2

    def test_clean_returns_0(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        assert dl.run_check() == 0

    def test_deltas_returns_10(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        changed = [dict(law) for law in laws]
        changed[0]["ultima_reforma"] = "DOF 31/12/2025"
        monkeypatch.setattr(dl, "fetch_index", lambda: changed)
        assert dl.run_check() == 10

    def test_low_count_returns_2(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dl, "fetch_index", lambda: _enough_laws())
        dl.init_snapshot()
        monkeypatch.setattr(dl, "fetch_index", lambda: _enough_laws(3))
        assert dl.run_check() == 2

    def test_does_not_mutate_state_or_create_catalog(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        state_before = (isolate_state / "estado.json").read_bytes()
        changed = [dict(law) for law in laws]
        changed[0]["ultima_reforma"] = "DOF 31/12/2025"
        monkeypatch.setattr(dl, "fetch_index", lambda: changed)
        dl.run_check()
        assert (isolate_state / "estado.json").read_bytes() == state_before
        assert not (isolate_state / "catalogo.json").exists()

    def test_writes_report_file(
        self,
        isolate_state: Path,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        changed = [dict(law) for law in laws]
        changed[0]["ultima_reforma"] = "DOF 31/12/2025"
        monkeypatch.setattr(dl, "fetch_index", lambda: changed)
        report = tmp_path / "reporte.md"
        dl.run_check(report)
        assert "Cambiadas" in report.read_text(encoding="utf-8")


class TestMainCheckExit:
    def test_main_check_raises_systemexit_clean(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        monkeypatch.setattr(sys, "argv", ["download_leyes.py", "--check"])
        with pytest.raises(SystemExit) as exc:
            dl.main()
        assert exc.value.code == 0

    def test_main_init_snapshot_writes_and_returns(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dl, "fetch_index", lambda: _enough_laws(5))
        monkeypatch.setattr(sys, "argv", ["download_leyes.py", "--init-snapshot"])
        dl.main()  # no debe lanzar ni descargar
        assert (isolate_state / "estado.json").exists()
