"""Tests para scripts/batch_convert.py — orquestador de conversiones."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import batch_convert as bc
import pytest

# ---------------------------------------------------------------------------
# load_catalog
# ---------------------------------------------------------------------------


class TestLoadCatalog:
    def test_returns_empty_dict_when_catalog_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bc, "CATALOG_PATH", tmp_path / "no_existe.json")
        assert bc.load_catalog() == {}

    def test_parses_catalog_keyed_by_pdf_filename(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        catalog_data = [
            {"pdf_filename": "ley_a.pdf", "nombre": "Ley A", "md_slug": "LA_a"},
            {"pdf_filename": "ley_b.pdf", "nombre": "Ley B", "md_slug": "LB_b"},
        ]
        catalog = tmp_path / "catalogo.json"
        catalog.write_text(json.dumps(catalog_data), encoding="utf-8")
        monkeypatch.setattr(bc, "CATALOG_PATH", catalog)

        result = bc.load_catalog()
        assert set(result.keys()) == {"ley_a.pdf", "ley_b.pdf"}
        assert result["ley_a.pdf"]["nombre"] == "Ley A"
        assert result["ley_b.pdf"]["md_slug"] == "LB_b"

    def test_handles_empty_catalog(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        catalog = tmp_path / "catalogo.json"
        catalog.write_text("[]", encoding="utf-8")
        monkeypatch.setattr(bc, "CATALOG_PATH", catalog)

        assert bc.load_catalog() == {}


# ---------------------------------------------------------------------------
# convert_pdf — comando construido + manejo de éxito/fallo
# ---------------------------------------------------------------------------


class TestConvertPdf:
    def test_returns_true_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            called["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        ok = bc.convert_pdf(
            tmp_path / "input.pdf",
            tmp_path / "out.md",
            "Mi Ley",
            verbose=False,
        )
        assert ok is True
        assert sys.executable in called["cmd"]
        assert str(bc.PDF_TO_MD) in called["cmd"]
        assert "Mi Ley" in called["cmd"]
        assert "--format" in called["cmd"]

    def test_returns_false_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        ok = bc.convert_pdf(
            tmp_path / "input.pdf",
            tmp_path / "out.md",
            "Mi Ley",
            verbose=False,
        )
        assert ok is False

    def test_failure_with_empty_stderr_does_not_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Cubre la rama `if stderr:` (false branch)
        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="   ")

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        ok = bc.convert_pdf(
            tmp_path / "x.pdf", tmp_path / "y.md", "X", verbose=False
        )
        assert ok is False

    def test_includes_canonical_dir_when_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        canonical = tmp_path / "canonical"
        bc.convert_pdf(
            tmp_path / "x.pdf",
            tmp_path / "y.md",
            "X",
            verbose=False,
            canonical_dir=canonical,
        )
        assert "--canonical-dir" in captured["cmd"]
        assert str(canonical) in captured["cmd"]

    def test_includes_validate_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        bc.convert_pdf(
            tmp_path / "x.pdf",
            tmp_path / "y.md",
            "X",
            verbose=False,
            validate=True,
        )
        assert "--validate" in captured["cmd"]

    def test_includes_verbose_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        bc.convert_pdf(
            tmp_path / "x.pdf",
            tmp_path / "y.md",
            "X",
            verbose=True,
        )
        assert "--verbose" in captured["cmd"]

    def test_uses_format_argument(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        bc.convert_pdf(
            tmp_path / "x.pdf",
            tmp_path / "y.md",
            "X",
            verbose=False,
            fmt="json",
        )
        assert captured["cmd"][captured["cmd"].index("--format") + 1] == "json"


# ---------------------------------------------------------------------------
# parse_args — banderas y defaults
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py"])
        args = bc.parse_args()
        assert args.skip_existing is False
        assert args.limit == 0
        assert args.verbose is False
        assert args.format == "both"
        assert args.validate is False

    def test_skip_existing_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--skip-existing"])
        args = bc.parse_args()
        assert args.skip_existing is True

    def test_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--limit", "7"])
        args = bc.parse_args()
        assert args.limit == 7

    def test_verbose_short_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "-v"])
        args = bc.parse_args()
        assert args.verbose is True

    @pytest.mark.parametrize("fmt", ["json", "md", "both"])
    def test_format_choices(
        self, fmt: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--format", fmt])
        args = bc.parse_args()
        assert args.format == fmt

    def test_invalid_format_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--format", "xml"])
        with pytest.raises(SystemExit):
            bc.parse_args()

    def test_validate_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--validate"])
        args = bc.parse_args()
        assert args.validate is True


# ---------------------------------------------------------------------------
# main — fixture común que arma un repo falso completo
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    origen = tmp_path / "origen-docs"
    markdown = tmp_path / "markdown"
    canonical = tmp_path / "canonical"
    catalog = tmp_path / "catalogo.json"
    scripts_dir = tmp_path / "scripts"

    origen.mkdir()
    scripts_dir.mkdir()

    monkeypatch.setattr(bc, "ROOT", tmp_path)
    monkeypatch.setattr(bc, "ORIGEN_DIR", origen)
    monkeypatch.setattr(bc, "MARKDOWN_DIR", markdown)
    monkeypatch.setattr(bc, "CANONICAL_DIR", canonical)
    monkeypatch.setattr(bc, "CATALOG_PATH", catalog)
    monkeypatch.setattr(bc, "SCRIPTS_DIR", scripts_dir)
    monkeypatch.setattr(bc, "PDF_TO_MD", scripts_dir / "pdf_to_md.py")

    return tmp_path


def _make_pdf(root: Path, name: str) -> Path:
    pdf = root / "origen-docs" / name
    pdf.write_bytes(b"%PDF-1.4 fake")
    return pdf


class TestMain:
    def test_exits_when_no_pdfs(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py"])

        with pytest.raises(SystemExit) as exc:
            bc.main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "No se encontraron PDFs" in captured.out

    def test_happy_path_converts_all(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_pdf(fake_repo, "ley_a.pdf")
        _make_pdf(fake_repo, "ley_b.pdf")
        (fake_repo / "catalogo.json").write_text(
            json.dumps([
                {"pdf_filename": "ley_a.pdf", "nombre": "Ley A", "md_slug": "LA_a"},
                {"pdf_filename": "ley_b.pdf", "nombre": "Ley B", "md_slug": "LB_b"},
            ]),
            encoding="utf-8",
        )

        run_calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            run_calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["batch_convert.py"])

        bc.main()

        captured = capsys.readouterr()
        # Cada PDF disparó un run(); además el run() final de gen_indice si existiera
        # (no creamos gen_indice.py → omitido).
        assert len(run_calls) == 2
        assert "2 convertidos" in captured.out
        assert "gen_indice.py no encontrado" in captured.out

    def test_skip_existing_skips_when_both_outputs_present(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_pdf(fake_repo, "ley.pdf")
        (fake_repo / "catalogo.json").write_text(
            json.dumps([
                {"pdf_filename": "ley.pdf", "nombre": "Ley", "md_slug": "L_ley"}
            ]),
            encoding="utf-8",
        )
        # Pre-crear los outputs
        (fake_repo / "markdown").mkdir(exist_ok=True)
        (fake_repo / "canonical").mkdir(exist_ok=True)
        (fake_repo / "markdown" / "L_ley.md").write_text("x", encoding="utf-8")
        (fake_repo / "canonical" / "L_ley.json").write_text("{}", encoding="utf-8")

        run_calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            run_calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--skip-existing"])

        bc.main()

        captured = capsys.readouterr()
        assert "ya existe" in captured.out
        assert "1 omitidos" in captured.out
        # Ningún run() de pdf_to_md (solo el de gen_indice si existiera, pero
        # no existe en el fake repo)
        assert run_calls == []

    def test_limit_truncates_list(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        for i in range(5):
            _make_pdf(fake_repo, f"ley_{i}.pdf")
        (fake_repo / "catalogo.json").write_text("[]", encoding="utf-8")

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--limit", "2"])

        bc.main()
        captured = capsys.readouterr()
        assert "2 convertidos" in captured.out
        assert len(calls) == 2

    def test_uses_pdf_stem_when_no_catalog_match(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_pdf(fake_repo, "huerfano.pdf")
        # Sin catalogo.json → load_catalog devuelve {} y cae al fallback
        captured_titles: list[str] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            # El argumento que sigue a "--title" es el título efectivo
            i = cmd.index("--title")
            captured_titles.append(cmd[i + 1])
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["batch_convert.py"])

        bc.main()
        # El título por defecto es el stem con _ y - reemplazados por espacio
        assert captured_titles == ["huerfano"]

    def test_failed_conversion_increments_failed_counter(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_pdf(fake_repo, "rota.pdf")
        (fake_repo / "catalogo.json").write_text("[]", encoding="utf-8")

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(cmd, 1, stderr="boom")

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["batch_convert.py"])

        bc.main()
        captured = capsys.readouterr()
        assert "1 errores" in captured.out
        assert "❌ Error" in captured.out

    def test_runs_gen_indice_when_present(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_pdf(fake_repo, "ley.pdf")
        (fake_repo / "catalogo.json").write_text("[]", encoding="utf-8")
        # Crear el script gen_indice.py para activar la rama true
        gen_indice_path = fake_repo / "scripts" / "gen_indice.py"
        gen_indice_path.write_text("# stub\n", encoding="utf-8")

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["batch_convert.py"])

        bc.main()
        # 1 conversión + 1 gen_indice
        assert len(calls) == 2
        assert any(str(gen_indice_path) in cmd for cmd in calls)
