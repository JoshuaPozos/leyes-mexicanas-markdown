"""Tests para scripts/batch_convert.py — orquestador de conversiones."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import batch_convert as bc
import pytest
from constants import BATCH_CONVERT_TIMEOUT_SECS

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
        assert args.workers is None
        assert args.timeout == BATCH_CONVERT_TIMEOUT_SECS

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
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--workers", "1"])

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
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--skip-existing", "--workers", "1"])

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
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--limit", "2", "--workers", "1"])

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
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--workers", "1"])

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
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--workers", "1"])

        bc.main()
        captured = capsys.readouterr()
        assert "1 errores" in captured.out
        # El check del símbolo de fallo ahora puede aparecer como "❌ [1/1] rota.pdf → rota.md"
        assert "❌" in captured.out

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
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--workers", "1"])

        bc.main()
        # 1 conversión + 1 gen_indice
        assert len(calls) == 2
        assert any(str(gen_indice_path) in cmd for cmd in calls)


# ---------------------------------------------------------------------------
# Timeout en convert_pdf
# ---------------------------------------------------------------------------


class TestConvertPdfTimeout:
    def test_passes_timeout_to_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            captured["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        bc.convert_pdf(
            tmp_path / "x.pdf", tmp_path / "y.md", "X",
            verbose=False, timeout_secs=42,
        )
        assert captured["timeout"] == 42

    def test_uses_default_timeout_when_not_specified(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            captured["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        bc.convert_pdf(tmp_path / "x.pdf", tmp_path / "y.md", "X", verbose=False)
        assert captured["timeout"] == BATCH_CONVERT_TIMEOUT_SECS

    def test_returns_false_on_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        ok = bc.convert_pdf(
            tmp_path / "x.pdf", tmp_path / "y.md", "X",
            verbose=False, timeout_secs=1,
        )
        assert ok is False


# ---------------------------------------------------------------------------
# parse_args — flags nuevos --workers / --timeout
# ---------------------------------------------------------------------------


class TestParseArgsWorkersTimeout:
    def test_workers_explicit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--workers", "4"])
        assert bc.parse_args().workers == 4

    def test_workers_short_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "-w", "2"])
        assert bc.parse_args().workers == 2

    def test_timeout_explicit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--timeout", "120"])
        assert bc.parse_args().timeout == 120


# ---------------------------------------------------------------------------
# _resolve_workers
# ---------------------------------------------------------------------------


class TestResolveWorkers:
    def test_positive_value_returned_as_is(self) -> None:
        assert bc._resolve_workers(4) == 4

    def test_none_falls_back_to_cpu_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bc.os, "cpu_count", lambda: 6)
        assert bc._resolve_workers(None) == 6

    def test_zero_or_negative_falls_back_to_cpu_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bc.os, "cpu_count", lambda: 3)
        assert bc._resolve_workers(0) == 3
        assert bc._resolve_workers(-1) == 3

    def test_cpu_count_none_yields_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bc.os, "cpu_count", lambda: None)
        assert bc._resolve_workers(None) == 1


# ---------------------------------------------------------------------------
# _run_tasks
# ---------------------------------------------------------------------------


class TestRunTasksSequential:
    def test_sequential_preserves_input_order(self, tmp_path: Path) -> None:
        tasks = [
            (tmp_path / f"in_{i}.pdf", tmp_path / f"out_{i}.md", f"T{i}")
            for i in range(3)
        ]
        called: list[Path] = []

        def fake_convert(pdf: Path, md: Path, title: str) -> bool:
            called.append(pdf)
            return True

        results = list(bc._run_tasks(tasks, fake_convert, max_workers=1))
        assert [pdf for pdf, _md, _ok in results] == [t[0] for t in tasks]
        assert all(ok for _pdf, _md, ok in results)
        assert called == [t[0] for t in tasks]

    def test_sequential_with_zero_workers(self, tmp_path: Path) -> None:
        tasks = [(tmp_path / "a.pdf", tmp_path / "a.md", "A")]
        results = list(bc._run_tasks(tasks, lambda *_a: True, max_workers=0))
        assert len(results) == 1

    def test_sequential_propagates_convert_result(self, tmp_path: Path) -> None:
        tasks = [
            (tmp_path / "ok.pdf", tmp_path / "ok.md", "OK"),
            (tmp_path / "fail.pdf", tmp_path / "fail.md", "FAIL"),
        ]

        def fake_convert(pdf: Path, md: Path, title: str) -> bool:
            return "fail" not in pdf.name

        results = {pdf.name: ok for pdf, _md, ok in bc._run_tasks(tasks, fake_convert, 1)}
        assert results == {"ok.pdf": True, "fail.pdf": False}


# ---------------------------------------------------------------------------
# Path paralelo: invoca ProcessPoolExecutor con max_workers correcto
# ---------------------------------------------------------------------------


class _FakePoolExecutor:
    """Reemplaza ProcessPoolExecutor en tests: ejecuta inline en el proceso
    principal pero respeta la interfaz (submit/as_completed/context manager).
    Permite monkeypatchear `subprocess.run` y validar que el path paralelo
    se invoca con los argumentos correctos."""

    instances: list[_FakePoolExecutor] = []

    def __init__(self, max_workers: int | None = None) -> None:
        self.max_workers = max_workers
        self.submitted: list[tuple] = []
        _FakePoolExecutor.instances.append(self)

    def __enter__(self) -> _FakePoolExecutor:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def submit(self, fn: Callable[..., Any], *args: Any) -> _FakeFuture:
        self.submitted.append((fn, args))
        return _FakeFuture(fn, args)


class _FakeFuture:
    def __init__(self, fn: Callable[..., Any], args: tuple) -> None:
        self._fn = fn
        self._args = args
        self._result: Any = None
        self._done = False

    def result(self) -> Any:
        if not self._done:
            self._result = self._fn(*self._args)
            self._done = True
        return self._result


def _fake_as_completed(futures: dict[_FakeFuture, Any]) -> Any:
    yield from futures


class TestParallelPath:
    def test_main_with_workers_2_uses_process_pool(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _FakePoolExecutor.instances.clear()
        _make_pdf(fake_repo, "ley_a.pdf")
        _make_pdf(fake_repo, "ley_b.pdf")
        (fake_repo / "catalogo.json").write_text(
            json.dumps([
                {"pdf_filename": "ley_a.pdf", "nombre": "Ley A", "md_slug": "LA_a"},
                {"pdf_filename": "ley_b.pdf", "nombre": "Ley B", "md_slug": "LB_b"},
            ]),
            encoding="utf-8",
        )

        def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(bc, "ProcessPoolExecutor", _FakePoolExecutor)
        monkeypatch.setattr(bc, "as_completed", _fake_as_completed)
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--workers", "2"])

        bc.main()

        # Se creó exactamente un pool con max_workers=2 y se enviaron 2 tareas.
        assert len(_FakePoolExecutor.instances) == 1
        pool = _FakePoolExecutor.instances[0]
        assert pool.max_workers == 2
        assert len(pool.submitted) == 2
        captured = capsys.readouterr()
        assert "paralelo (workers=2)" in captured.out
        assert "2 convertidos" in captured.out

    def test_main_parallel_handles_future_exception(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _FakePoolExecutor.instances.clear()
        _make_pdf(fake_repo, "ley.pdf")
        (fake_repo / "catalogo.json").write_text("[]", encoding="utf-8")

        class _ExplodingFuture(_FakeFuture):
            def result(self) -> Any:
                raise RuntimeError("worker crashed")

        class _ExplodingPool(_FakePoolExecutor):
            def submit(self, fn: Callable[..., Any], *args: Any) -> _FakeFuture:
                self.submitted.append((fn, args))
                return _ExplodingFuture(fn, args)

        monkeypatch.setattr(bc, "ProcessPoolExecutor", _ExplodingPool)
        monkeypatch.setattr(bc, "as_completed", _fake_as_completed)
        monkeypatch.setattr(sys, "argv", ["batch_convert.py", "--workers", "2"])

        bc.main()

        captured = capsys.readouterr()
        assert "1 errores" in captured.out


def test_load_slug_filter_ignores_blanks_and_comments(tmp_path: Path) -> None:
    f = tmp_path / "delta.txt"
    f.write_text("# comentario\nLA_a\n\n  LB_b  \n", encoding="utf-8")
    assert bc.load_slug_filter(f) == {"LA_a", "LB_b"}


class TestOnlySlugs:
    def _catalog_two(self, fake_repo: Path) -> None:
        _make_pdf(fake_repo, "LA_a.pdf")
        _make_pdf(fake_repo, "LB_b.pdf")
        (fake_repo / "catalogo.json").write_text(
            json.dumps([
                {"pdf_filename": "LA_a.pdf", "nombre": "Ley A", "md_slug": "LA_a"},
                {"pdf_filename": "LB_b.pdf", "nombre": "Ley B", "md_slug": "LB_b"},
            ]),
            encoding="utf-8",
        )

    def test_converts_only_listed_slugs(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._catalog_two(fake_repo)
        delta = fake_repo / "delta.txt"
        delta.write_text("LA_a\n", encoding="utf-8")

        run_calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            run_calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(
            sys, "argv",
            ["batch_convert.py", "--workers", "1", "--only-slugs", str(delta)],
        )
        bc.main()

        # Solo LA_a se convirtió (1 run; sin gen_indice.py en el repo falso)
        assert len(run_calls) == 1
        assert "LA_a.pdf" in " ".join(run_calls[0])

    def test_reconverts_even_when_output_exists(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # --only-slugs nunca aplica skip-by-existence: aunque la salida ya
        # exista, vuelve a convertir (pdf_to_md sobreescribe). Y NO pre-borra,
        # así que si la conversión fallara la salida vieja sobrevive.
        self._catalog_two(fake_repo)
        (fake_repo / "markdown").mkdir()
        (fake_repo / "canonical").mkdir()
        old_md = fake_repo / "markdown" / "LA_a.md"
        old_md.write_text("VIEJO", encoding="utf-8")
        delta = fake_repo / "delta.txt"
        delta.write_text("LA_a\n", encoding="utf-8")

        run_calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            run_calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(
            sys, "argv",
            ["batch_convert.py", "--workers", "1", "--only-slugs", str(delta)],
        )
        bc.main()

        # Se reconvirtió pese a existir la salida (no se saltó)…
        assert len(run_calls) == 1
        assert "LA_a.pdf" in " ".join(run_calls[0])
        # …y la salida vieja sigue ahí (no se pre-borró; el fake no la sobreescribe).
        assert old_md.exists()

    def test_warns_on_slug_without_pdf(
        self,
        fake_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._catalog_two(fake_repo)
        delta = fake_repo / "delta.txt"
        delta.write_text("LA_a\nNO_EXISTE\n", encoding="utf-8")

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(bc.subprocess, "run", fake_run)
        monkeypatch.setattr(
            sys, "argv",
            ["batch_convert.py", "--workers", "1", "--only-slugs", str(delta)],
        )
        bc.main()

        captured = capsys.readouterr()
        assert "NO_EXISTE" in captured.out
        assert "sin PDF" in captured.out
