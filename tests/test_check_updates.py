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
    monkeypatch.setattr(dl, "ORIGEN_DIR", tmp_path / "origen-docs")
    monkeypatch.setattr(dl, "MARKDOWN_DIR", tmp_path / "markdown")
    monkeypatch.setattr(dl, "CANONICAL_DIR", tmp_path / "canonical")
    monkeypatch.setattr(dl, "ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    monkeypatch.setattr(dl.time, "sleep", lambda _s: None)
    for d in ("origen-docs", "markdown", "canonical"):
        (tmp_path / d).mkdir()
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

    def test_main_rejects_multiple_modes(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["download_leyes.py", "--check", "--apply"])
        with pytest.raises(SystemExit) as exc:
            dl.main()
        assert exc.value.code == 2


def _ok_download(url: str, dest: object, *a: object, **k: object) -> str:
    Path(dest).write_bytes(b"%PDF-fake")  # type: ignore[arg-type]
    return "b" * 64


def _seed_catalog(laws: list[dict]) -> None:
    """Escribe catalogo.json (lista de leyes) en la ruta aislada por el fixture."""
    dl.CATALOG_PATH.write_text(
        json.dumps(laws, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _snapshot_then_change_first(
    monkeypatch: pytest.MonkeyPatch, reforma: str = "DOF 31/12/2025"
) -> list[dict]:
    """Graba snapshot + catálogo con _enough_laws() y devuelve una copia con la
    1ª ley (key 'l0') reformada — para que run_apply vea exactamente 1 CAMBIADA."""
    laws = _enough_laws()
    monkeypatch.setattr(dl, "fetch_index", lambda: laws)
    dl.init_snapshot()
    _seed_catalog(laws)
    changed = [dict(law) for law in laws]
    changed[0]["ultima_reforma"] = reforma
    monkeypatch.setattr(dl, "fetch_index", lambda: changed)
    return changed


class TestRunApply:
    def test_missing_state_returns_2(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            dl, "fetch_index", lambda: pytest.fail("no debe fetchear sin estado")
        )
        assert dl.run_apply() == 2

    def test_no_deltas_returns_0(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        _seed_catalog(laws)
        assert dl.run_apply() == 0

    def test_missing_catalog_returns_2(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()  # hay estado pero NO catálogo
        assert dl.run_apply() == 2

    def test_upserts_catalog_for_changed_law(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _snapshot_then_change_first(monkeypatch)
        monkeypatch.setattr(dl, "download_pdf", _ok_download)
        dl.run_apply()
        catalog = json.loads(
            (isolate_state / "catalogo.json").read_text(encoding="utf-8")
        )
        entry = next(c for c in catalog if c["md_slug"] == "L0")
        # B1: el catálogo (fuente de verdad de gen_indice/pdf_to_md) se refrescó.
        assert entry["ultima_reforma"] == "DOF 31/12/2025"
        assert entry["sha256"] == "b" * 64
        assert len(catalog) == len(_enough_laws())  # sin duplicar

    def test_md_slug_rename_archives_old_and_dedups_catalog(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 1ª ley cambia su md_slug (reforma de nombre): los artefactos viejos existen.
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        _seed_catalog(laws)
        (isolate_state / "origen-docs" / "L0.pdf").write_bytes(b"%PDF-viejo")
        (isolate_state / "markdown" / "L0.md").write_text("viejo", encoding="utf-8")
        (isolate_state / "canonical" / "L0.json").write_text("{}", encoding="utf-8")

        changed = [dict(law) for law in laws]
        changed[0] = {**changed[0], "md_slug": "L0_renombrada",
                      "pdf_filename": "L0_renombrada.pdf",
                      "ultima_reforma": "DOF 31/12/2025"}
        monkeypatch.setattr(dl, "fetch_index", lambda: changed)
        monkeypatch.setattr(dl, "download_pdf", _ok_download)

        dl.run_apply()
        # los artefactos viejos se ARCHIVARON (F4); el nuevo PDF se descargó
        assert (isolate_state / "archive" / "origen-docs" / "L0.pdf").exists()
        assert (isolate_state / "archive" / "markdown" / "L0.md").exists()
        assert (isolate_state / "origen-docs" / "L0_renombrada.pdf").exists()
        # catálogo: sin la entrada vieja, con la nueva, sin duplicar el total
        catalog = json.loads((isolate_state / "catalogo.json").read_text(encoding="utf-8"))
        md_slugs = [c["md_slug"] for c in catalog]
        assert "L0" not in md_slugs
        assert "L0_renombrada" in md_slugs
        assert len(catalog) == len(laws)

    def test_delta_out_creates_missing_parent_dir(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _snapshot_then_change_first(monkeypatch)
        monkeypatch.setattr(dl, "download_pdf", _ok_download)
        nested = isolate_state / "sub" / "dir" / "delta.txt"
        assert dl.run_apply(delta_path=nested) == 10
        assert nested.exists()  # B4: no revienta tras avanzar estado


class TestLedgerRobustness:
    def test_load_state_aborts_on_corrupt_json(
        self, isolate_state: Path
    ) -> None:
        (isolate_state / "estado.json").write_text("{no es json", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            dl.load_state()
        assert exc.value.code == 2  # B2: error claro, no stacktrace

    def test_save_state_is_atomic_and_roundtrips(
        self, isolate_state: Path
    ) -> None:
        entries = [{"key": "a", "ultima_reforma_raw": "x"}]
        dl.save_state(entries)
        assert dl.load_state() == entries
        # sin temporal residual
        assert not (isolate_state / "estado.json.tmp").exists()


class TestArchival:
    def test_archive_law_moves_artifacts(self, isolate_state: Path) -> None:
        (isolate_state / "markdown" / "X.md").write_text("md", encoding="utf-8")
        (isolate_state / "canonical" / "X.json").write_text("{}", encoding="utf-8")
        (isolate_state / "origen-docs" / "X.pdf").write_bytes(b"%PDF")
        moved = dl._archive_law("X")
        assert (isolate_state / "archive" / "markdown" / "X.md").exists()
        assert (isolate_state / "archive" / "canonical" / "X.json").exists()
        assert (isolate_state / "archive" / "origen-docs" / "X.pdf").exists()
        assert not (isolate_state / "markdown" / "X.md").exists()
        assert len(moved) == 3

    def test_apply_archives_abrogated_law(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        _seed_catalog(laws)
        (isolate_state / "markdown" / "L0.md").write_text("c", encoding="utf-8")
        (isolate_state / "canonical" / "L0.json").write_text("{}", encoding="utf-8")
        # upstream marca L0 abrogada (numero 'A' + flag)
        fresh = [dict(law) for law in laws]
        fresh[0] = {**fresh[0], "abrogated": True, "numero": "A",
                    "ultima_reforma": "DOF 22/05/2026"}
        monkeypatch.setattr(dl, "fetch_index", lambda: fresh)
        monkeypatch.setattr(
            dl, "download_pdf", lambda *a, **k: pytest.fail("no descarga abrogada")
        )

        assert dl.run_apply() == 10
        assert (isolate_state / "archive" / "markdown" / "L0.md").exists()
        assert not (isolate_state / "markdown" / "L0.md").exists()
        catalog = json.loads((isolate_state / "catalogo.json").read_text(encoding="utf-8"))
        assert "L0" not in [c["md_slug"] for c in catalog]
        state = json.loads((isolate_state / "estado.json").read_text(encoding="utf-8"))
        assert "l0" not in [e["key"] for e in state]
        assert "L0" not in (isolate_state / "delta.txt").read_text(encoding="utf-8").split()

    def test_apply_archives_baja(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = _enough_laws(281)  # tras quitar 1 quedan 280 (>= MIN_SANE)
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        _seed_catalog(laws)
        (isolate_state / "markdown" / "L0.md").write_text("c", encoding="utf-8")
        (isolate_state / "canonical" / "L0.json").write_text("{}", encoding="utf-8")
        fresh = [dict(law) for law in laws if law["md_slug"] != "L0"]
        monkeypatch.setattr(dl, "fetch_index", lambda: fresh)
        monkeypatch.setattr(
            dl, "download_pdf", lambda *a, **k: pytest.fail("no descarga baja")
        )

        assert dl.run_apply() == 10
        assert (isolate_state / "archive" / "markdown" / "L0.md").exists()
        catalog = json.loads((isolate_state / "catalogo.json").read_text(encoding="utf-8"))
        assert "L0" not in [c["md_slug"] for c in catalog]

    def test_apply_skips_abrogated_alta(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        _seed_catalog(laws)
        fresh = [dict(law) for law in laws]
        fresh.append({**_law("NUEVA.pdf", "NUEVA", "Sin reforma"),
                      "abrogated": True, "numero": "A"})
        monkeypatch.setattr(dl, "fetch_index", lambda: fresh)
        monkeypatch.setattr(dl, "download_pdf", _ok_download)

        dl.run_apply()
        catalog = json.loads((isolate_state / "catalogo.json").read_text(encoding="utf-8"))
        assert "NUEVA" not in [c["md_slug"] for c in catalog]

    def test_all_downloads_failed_returns_2_even_with_archival(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # #1: si TODAS las descargas fallan, el archivado no debe enmascarar el
        # fallo de red devolviendo 10; debe señalizar inconcluso (2).
        laws = _enough_laws()
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        dl.init_snapshot()
        _seed_catalog(laws)
        fresh = [dict(law) for law in laws]
        fresh[1]["ultima_reforma"] = "DOF 31/12/2025"          # cambiada (descarga falla)
        fresh[0] = {**fresh[0], "abrogated": True}             # abrogada (se archiva)
        monkeypatch.setattr(dl, "fetch_index", lambda: fresh)
        monkeypatch.setattr(dl, "download_pdf", lambda *a, **k: None)  # toda descarga falla

        assert dl.run_apply() == 2

    def test_archive_law_versions_instead_of_overwriting(
        self, isolate_state: Path
    ) -> None:
        # #4: ya hay una versión archivada del mismo slug → no se pisa, se versiona.
        (isolate_state / "markdown" / "Y.md").write_text("nuevo", encoding="utf-8")
        (isolate_state / "archive" / "markdown").mkdir(parents=True)
        (isolate_state / "archive" / "markdown" / "Y.md").write_text(
            "viejo archivado", encoding="utf-8"
        )
        dl._archive_law("Y")
        # el archivado previo se conserva intacto; el nuevo entra como Y.1.md
        assert (isolate_state / "archive" / "markdown" / "Y.md").read_text(
            encoding="utf-8"
        ) == "viejo archivado"
        assert (isolate_state / "archive" / "markdown" / "Y.1.md").read_text(
            encoding="utf-8"
        ) == "nuevo"

    def test_archive_law_falls_back_to_move_on_exdev(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # #5: si os.replace falla (EXDEV cross-FS), cae a shutil.move.
        (isolate_state / "markdown" / "Z.md").write_text("z", encoding="utf-8")

        def fake_replace(src: object, dst: object) -> None:
            raise OSError("simulando EXDEV cross-device")

        monkeypatch.setattr(dl.os, "replace", fake_replace)
        dl._archive_law("Z")
        assert (isolate_state / "archive" / "markdown" / "Z.md").exists()
        assert not (isolate_state / "markdown" / "Z.md").exists()

    def test_dry_run_does_not_download(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _snapshot_then_change_first(monkeypatch)
        monkeypatch.setattr(
            dl, "download_pdf", lambda *a, **k: pytest.fail("dry-run no descarga")
        )
        assert dl.run_apply(dry_run=True) == 10

    def test_downloads_changed_and_writes_delta_and_drift(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _snapshot_then_change_first(monkeypatch)
        monkeypatch.setattr(dl, "download_pdf", _ok_download)

        assert dl.run_apply() == 10

        delta = (isolate_state / "delta.txt").read_text(encoding="utf-8").split()
        assert delta == ["L0"]
        drift = (isolate_state / "expected_drift.txt").read_text(encoding="utf-8")
        assert "L0" in drift and "DOF 31/12/2025" in drift
        # estado avanzó solo la ley descargada
        state = json.loads((isolate_state / "estado.json").read_text(encoding="utf-8"))
        l0 = next(e for e in state if e["key"] == "l0")
        assert l0["ultima_reforma_raw"] == "DOF 31/12/2025"
        assert l0["pdf_sha256"] == "b" * 64
        # el PDF se descargó a origen-docs con nombre {md_slug}.pdf
        assert (isolate_state / "origen-docs" / "L0.pdf").exists()

    def test_advances_only_on_download_success(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _snapshot_then_change_first(monkeypatch)
        monkeypatch.setattr(dl, "download_pdf", lambda *a, **k: None)  # falla

        dl.run_apply()
        state = json.loads((isolate_state / "estado.json").read_text(encoding="utf-8"))
        l0 = next(e for e in state if e["key"] == "l0")
        assert l0["ultima_reforma_raw"] == "DOF 01/01/2025"  # NO avanzó
        assert (isolate_state / "delta.txt").read_text(encoding="utf-8").strip() == ""

    def test_resumable_second_run_sees_no_change(
        self, isolate_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _snapshot_then_change_first(monkeypatch)
        monkeypatch.setattr(dl, "download_pdf", _ok_download)
        assert dl.run_apply() == 10
        # el estado ya avanzó → una segunda corrida no ve deltas
        assert dl.run_apply() == 0
