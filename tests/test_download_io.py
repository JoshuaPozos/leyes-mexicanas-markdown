"""Tests para las partes I/O de download_leyes (parser HTML, fetch, descarga, CLI).

Las funciones puras (slugify, derive_acronym, parse_law_name, compute_md_slug)
están cubiertas en tests/test_download_helpers.py."""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
from pathlib import Path

import download_leyes as dl
import pytest

# ---------------------------------------------------------------------------
# LeyesTableParser
# ---------------------------------------------------------------------------


SAMPLE_HTML = """
<html><body>
<table>
  <tr>
    <td>No.</td><td>Nombre</td><td>Última Reforma</td><td>PDF</td>
  </tr>
  <tr>
    <td>1</td>
    <td>Constitución Política de los Estados Unidos Mexicanos DOF 11/03/2024</td>
    <td>11/03/2024</td>
    <td>
      <a href="pdf/CPEUM.pdf">PDF</a>
      <a href="pdf_mov/CPEUM_mov.pdf">PDF móvil</a>
    </td>
  </tr>
  <tr>
    <td>2</td>
    <td>Ley del ISR DOF 12/11/2021</td>
    <td>12/11/2021</td>
    <td><a href="pdf/LISR.pdf">PDF</a></td>
  </tr>
</table>
</body></html>
"""


class TestLeyesTableParser:
    def test_parses_two_rows(self) -> None:
        parser = dl.LeyesTableParser()
        parser.feed(SAMPLE_HTML)
        # 3 filas con `numero` y `links` (la primera de cabecera y las 2 leyes)
        assert len(parser.rows) == 3

    def test_extracts_law_columns(self) -> None:
        parser = dl.LeyesTableParser()
        parser.feed(SAMPLE_HTML)
        ley1 = parser.rows[1]
        assert ley1["numero"] == "1"
        assert "Constitución Política" in ley1["nombre_raw"]
        assert ley1["ultima_reforma"] == "11/03/2024"
        assert "pdf/CPEUM.pdf" in ley1["links"]
        assert "pdf_mov/CPEUM_mov.pdf" in ley1["links"]

    def test_collapses_whitespace_in_text(self) -> None:
        html = """
        <table><tr>
          <td>1</td>
          <td>Ley   con\nespacios\t múltiples</td>
          <td>01/01/2024</td>
          <td><a href="pdf/L.pdf">x</a></td>
        </tr></table>
        """
        parser = dl.LeyesTableParser()
        parser.feed(html)
        assert parser.rows[0]["nombre_raw"] == "Ley con espacios múltiples"

    def test_ignores_anchors_outside_td(self) -> None:
        # Un anchor antes del primer td no debe quedar registrado
        html = """
        <a href="ignorar.pdf">link huérfano</a>
        <table><tr>
          <td>1</td><td>Ley</td><td>01/01/2024</td>
          <td><a href="pdf/L.pdf">PDF</a></td>
        </tr></table>
        """
        parser = dl.LeyesTableParser()
        parser.feed(html)
        # Solo el anchor de dentro del td debería estar
        assert parser.rows[0]["links"] == ["pdf/L.pdf"]

    def test_skips_rows_without_links(self) -> None:
        html = """
        <table>
          <tr><td>solo</td><td>celda</td></tr>
        </table>
        """
        parser = dl.LeyesTableParser()
        parser.feed(html)
        # No tiene "links" → no se agrega
        assert parser.rows == []

    def test_anchor_without_href_is_skipped(self) -> None:
        html = """
        <table><tr>
          <td>1</td><td>Ley</td><td>01/01/2024</td>
          <td><a>texto sin href</a><a href="pdf/L.pdf">ok</a></td>
        </tr></table>
        """
        parser = dl.LeyesTableParser()
        parser.feed(html)
        assert parser.rows[0]["links"] == ["pdf/L.pdf"]


# ---------------------------------------------------------------------------
# fetch_index
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body


class TestFetchIndex:
    def test_returns_laws_with_pdf_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # latin-1 es lo que decodifica fetch_index
        body = SAMPLE_HTML.encode("latin-1")

        def fake_urlopen(req: object, timeout: int = 30) -> _FakeResponse:
            return _FakeResponse(body)

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)

        laws = dl.fetch_index()
        assert len(laws) == 2
        # Solo se eligió el PDF normal, no el _mov
        assert laws[0]["pdf_url"].endswith("/CPEUM.pdf")
        # Cada ley tiene los campos esperados
        expected_keys = {
            "numero", "nombre", "dof", "ultima_reforma", "pdf_url",
            "pdf_filename", "pdf_filename_origen", "md_slug",
        }
        for law in laws:
            assert expected_keys.issubset(law.keys())

    def test_skips_header_row(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # La primera fila es "No. | Nombre | ..." y se filtra explícitamente
        html = """
        <table>
          <tr><td>no.</td><td>Nombre</td><td>R</td><td><a href="pdf/X.pdf">x</a></td></tr>
          <tr><td>1</td><td>Ley A</td><td>01/01/2024</td><td><a href="pdf/A.pdf">x</a></td></tr>
        </table>
        """

        def fake_urlopen(req: object, timeout: int = 30) -> _FakeResponse:
            return _FakeResponse(html.encode("latin-1"))

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        laws = dl.fetch_index()
        assert len(laws) == 1
        assert laws[0]["numero"] == "1"

    def test_skips_rows_without_pdf_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        html = """
        <table>
          <tr><td>1</td><td>Ley solo móvil</td><td>r</td>
              <td><a href="pdf_mov/X.pdf">solo mov</a></td></tr>
          <tr><td>2</td><td>Ley con pdf</td><td>r</td>
              <td><a href="pdf/Y.pdf">ok</a></td></tr>
        </table>
        """

        def fake_urlopen(req: object, timeout: int = 30) -> _FakeResponse:
            return _FakeResponse(html.encode("latin-1"))

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        laws = dl.fetch_index()
        assert len(laws) == 1
        assert laws[0]["numero"] == "2"


# ---------------------------------------------------------------------------
# download_pdf
# ---------------------------------------------------------------------------


class TestDownloadPdf:
    def test_writes_file_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = b"%PDF-1.4 contenido falso"

        def fake_urlopen(req: object, timeout: int = 60) -> _FakeResponse:
            return _FakeResponse(body)

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)

        dest = tmp_path / "leyes" / "x.pdf"
        sha = dl.download_pdf("https://www.diputados.gob.mx/x.pdf", dest)
        # SHA-256 hex tiene 64 chars
        assert isinstance(sha, str) and len(sha) == 64
        assert dest.read_bytes() == body

    def test_creates_parent_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_urlopen(req: object, timeout: int = 60) -> _FakeResponse:
            return _FakeResponse(b"%PDF-1.4 x")

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        dest = tmp_path / "a" / "b" / "c.pdf"
        assert not dest.parent.exists()
        sha = dl.download_pdf("https://www.diputados.gob.mx/c.pdf", dest)
        assert sha is not None
        assert dest.parent.exists()

    def test_verbose_prints_size_and_sha_prefix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def fake_urlopen(req: object, timeout: int = 60) -> _FakeResponse:
            return _FakeResponse(b"%PDF-" + b"a" * 2048)  # ~2 KB

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        dest = tmp_path / "verbose.pdf"
        sha = dl.download_pdf("https://www.diputados.gob.mx/v.pdf", dest, verbose=True)
        assert sha is not None
        out = capsys.readouterr().out
        assert "verbose.pdf" in out
        assert "MB" in out
        # El prefijo del SHA aparece en la salida verbose
        assert sha[:12] in out

    def test_returns_none_on_url_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def fake_urlopen(req: object, timeout: int = 60) -> object:
            raise urllib.error.URLError("dns failure")

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(dl.time, "sleep", lambda _s: None)
        dest = tmp_path / "broken.pdf"
        sha = dl.download_pdf(
            "https://www.diputados.gob.mx/b.pdf", dest, max_retries=0,
        )
        assert sha is None
        assert not dest.exists()
        err = capsys.readouterr().err
        assert "Error descargando" in err

    def test_returns_none_on_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_urlopen(req: object, timeout: int = 60) -> object:
            raise TimeoutError("se tardó")

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(dl.time, "sleep", lambda _s: None)
        sha = dl.download_pdf(
            "https://www.diputados.gob.mx/x.pdf",
            tmp_path / "t.pdf",
            max_retries=0,
        )
        assert sha is None


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


class TestDownloadParseArgs:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["download_leyes.py"])
        args = dl.parse_args()
        assert args.list is False
        assert args.limit == 0
        assert args.skip_existing is False
        assert args.verbose is False
        assert args.output_dir == dl.ORIGEN_DIR

    def test_list_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["download_leyes.py", "--list"])
        assert dl.parse_args().list is True

    def test_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["download_leyes.py", "--limit", "3"])
        assert dl.parse_args().limit == 3

    def test_skip_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sys, "argv", ["download_leyes.py", "--skip-existing"]
        )
        assert dl.parse_args().skip_existing is True

    def test_output_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            sys, "argv", ["download_leyes.py", "-o", str(tmp_path)]
        )
        args = dl.parse_args()
        assert args.output_dir == tmp_path

    def test_verbose(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["download_leyes.py", "-v"])
        assert dl.parse_args().verbose is True


# ---------------------------------------------------------------------------
# main — mockear fetch_index, download_pdf, time.sleep
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_main_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Aísla main() en un tmp dir."""
    catalog = tmp_path / "catalogo.json"
    origen = tmp_path / "origen-docs"
    monkeypatch.setattr(dl, "CATALOG_PATH", catalog)
    monkeypatch.setattr(dl, "ORIGEN_DIR", origen)
    # No queremos que main duerma 0.3s entre descargas en los tests
    monkeypatch.setattr(dl.time, "sleep", lambda _s: None)
    return tmp_path


def _stub_law(num: str, slug: str) -> dict:
    return {
        "numero": num,
        "nombre": f"Ley {num}",
        "dof": "DOF 01/01/2024",
        "ultima_reforma": "01/01/2024",
        "pdf_url": f"https://www.diputados.gob.mx/pdf/{slug}.pdf",
        "pdf_filename": f"{slug}.pdf",
        "pdf_filename_origen": f"{slug}.pdf",
        "md_slug": slug,
    }


_FAKE_SHA = "a" * 64  # SHA-256 hex de 64 chars, valor irrelevante en tests


class TestMain:
    def test_writes_catalog_and_downloads(
        self,
        fake_main_env: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        laws = [_stub_law("1", "LA"), _stub_law("2", "LB")]
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)

        downloaded_urls: list[str] = []

        def fake_download(url: str, dest: Path, verbose: bool = False, **_kw: object) -> str:
            downloaded_urls.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"x" * 1024)
            return _FAKE_SHA

        monkeypatch.setattr(dl, "download_pdf", fake_download)
        monkeypatch.setattr(
            sys,
            "argv",
            ["download_leyes.py", "-o", str(fake_main_env / "origen-docs")],
        )

        dl.main()

        # Catálogo escrito
        catalog_data = json.loads(
            (fake_main_env / "catalogo.json").read_text(encoding="utf-8")
        )
        assert len(catalog_data) == 2

        # Descargó las dos leyes
        assert len(downloaded_urls) == 2

        out = capsys.readouterr().out
        assert "2 descargados" in out

    def test_list_mode_does_not_download(
        self,
        fake_main_env: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        laws = [_stub_law("1", "LA")]
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        called: list[str] = []
        monkeypatch.setattr(
            dl,
            "download_pdf",
            lambda *a, **k: called.append("called") or _FAKE_SHA,
        )
        monkeypatch.setattr(sys, "argv", ["download_leyes.py", "--list"])

        dl.main()
        out = capsys.readouterr().out
        assert "Ley 1" in out
        assert called == []  # no descarga

    def test_skip_existing_skips_downloaded_files(
        self,
        fake_main_env: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        laws = [_stub_law("1", "LA")]
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)

        # Pre-crear el archivo de salida
        out_dir = fake_main_env / "origen-docs"
        out_dir.mkdir()
        (out_dir / "LA.pdf").write_bytes(b"x")

        called: list[str] = []
        monkeypatch.setattr(
            dl,
            "download_pdf",
            lambda *a, **k: called.append("download") or _FAKE_SHA,
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "download_leyes.py",
                "--skip-existing",
                "-o",
                str(out_dir),
                "-v",
            ],
        )

        dl.main()
        captured = capsys.readouterr().out
        assert "1 omitidos" in captured
        assert "ya existe" in captured
        assert called == []

    def test_sha256_file_matches_hashlib(self, tmp_path: Path) -> None:
        p = tmp_path / "f.bin"
        data = b"abc123" * 1000  # > tamaño de bloque para ejercer el chunking
        p.write_bytes(data)
        assert dl._sha256_file(p) == hashlib.sha256(data).hexdigest()

    def test_skip_existing_populates_sha256_from_local_file(
        self,
        fake_main_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fix: --skip-existing ahora hashea el PDF local en vez de dejar el
        catálogo sin sha256."""
        laws = [_stub_law("1", "LA")]
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)

        out_dir = fake_main_env / "origen-docs"
        out_dir.mkdir()
        content = b"%PDF-1.4 contenido local de prueba"
        (out_dir / "LA.pdf").write_bytes(content)

        monkeypatch.setattr(
            dl,
            "download_pdf",
            lambda *a, **k: pytest.fail("no debe descargar con --skip-existing"),
        )
        monkeypatch.setattr(
            sys,
            "argv",
            ["download_leyes.py", "--skip-existing", "-o", str(out_dir)],
        )

        dl.main()

        catalog_data = json.loads(
            (fake_main_env / "catalogo.json").read_text(encoding="utf-8")
        )
        assert catalog_data[0]["sha256"] == hashlib.sha256(content).hexdigest()

    def test_limit_truncates(
        self,
        fake_main_env: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        laws = [_stub_law(str(i), f"L{i}") for i in range(5)]
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)

        downloaded: list[str] = []

        def fake_download(url: str, dest: Path, verbose: bool = False, **_kw: object) -> str:
            downloaded.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"x")
            return _FAKE_SHA

        monkeypatch.setattr(dl, "download_pdf", fake_download)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "download_leyes.py",
                "--limit",
                "2",
                "-o",
                str(fake_main_env / "origen-docs"),
            ],
        )

        dl.main()
        assert len(downloaded) == 2
        assert "2 descargados" in capsys.readouterr().out

    def test_failed_download_increments_failed(
        self,
        fake_main_env: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        laws = [_stub_law("1", "LA")]
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        monkeypatch.setattr(dl, "download_pdf", lambda *a, **k: None)
        monkeypatch.setattr(
            sys,
            "argv",
            ["download_leyes.py", "-o", str(fake_main_env / "origen-docs")],
        )

        dl.main()
        assert "1 errores" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Allowlist de hosts
# ---------------------------------------------------------------------------


class TestUrlAllowlist:
    def test_accepts_diputados_host(self) -> None:
        assert dl._is_url_allowed(
            "https://www.diputados.gob.mx/x.pdf",
            ("diputados.gob.mx", "www.diputados.gob.mx"),
        )

    def test_accepts_diputados_without_www(self) -> None:
        assert dl._is_url_allowed(
            "https://diputados.gob.mx/x.pdf",
            ("diputados.gob.mx", "www.diputados.gob.mx"),
        )

    def test_rejects_other_host(self) -> None:
        assert not dl._is_url_allowed(
            "https://example.com/x.pdf",
            ("diputados.gob.mx", "www.diputados.gob.mx"),
        )

    def test_rejects_non_http_scheme(self) -> None:
        assert not dl._is_url_allowed(
            "file:///etc/passwd",
            ("diputados.gob.mx",),
        )
        assert not dl._is_url_allowed(
            "ftp://diputados.gob.mx/x.pdf",
            ("diputados.gob.mx",),
        )

    def test_empty_allowlist_disables_check(self) -> None:
        # tupla vacía = sin restricción (útil para tests aislados)
        assert dl._is_url_allowed("https://anywhere.example/x.pdf", ())


class TestDownloadPdfAllowlist:
    def test_rejects_url_outside_allowlist(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # urlopen NO debe llamarse si el host falla la validación
        called: list[str] = []

        def fake_urlopen(*a: object, **k: object) -> object:
            called.append("urlopen")
            raise AssertionError("no debe llamarse")

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        sha = dl.download_pdf(
            "https://malicious.example.com/payload.pdf",
            tmp_path / "x.pdf",
        )
        assert sha is None
        assert called == []
        err = capsys.readouterr().err
        assert "URL no permitida" in err


# ---------------------------------------------------------------------------
# Validación de magic bytes (PDF)
# ---------------------------------------------------------------------------


class TestDownloadPdfMagicBytes:
    def test_rejects_non_pdf_body(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = b"<html>Error 404</html>"

        def fake_urlopen(req: object, timeout: int = 60) -> _FakeResponse:
            return _FakeResponse(body)

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        dest = tmp_path / "fake.pdf"
        sha = dl.download_pdf("https://www.diputados.gob.mx/x.pdf", dest)
        assert sha is None
        assert not dest.exists()
        err = capsys.readouterr().err
        assert "no es un PDF válido" in err

    def test_accepts_minimal_pdf_header(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Exactamente los bytes mágicos; sigue siendo "PDF" para la validación
        def fake_urlopen(req: object, timeout: int = 60) -> _FakeResponse:
            return _FakeResponse(b"%PDF-")

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        sha = dl.download_pdf(
            "https://www.diputados.gob.mx/min.pdf", tmp_path / "m.pdf",
        )
        assert isinstance(sha, str) and len(sha) == 64


# ---------------------------------------------------------------------------
# Retry con backoff exponencial
# ---------------------------------------------------------------------------


class TestDownloadPdfRetry:
    def test_succeeds_after_transient_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = {"n": 0}

        def fake_urlopen(req: object, timeout: int = 60) -> _FakeResponse:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise urllib.error.URLError("transient")
            return _FakeResponse(b"%PDF-1.4 ok")

        sleeps: list[float] = []
        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(dl.time, "sleep", lambda s: sleeps.append(s))

        sha = dl.download_pdf(
            "https://www.diputados.gob.mx/x.pdf", tmp_path / "x.pdf",
            max_retries=3,
        )
        assert sha is not None
        assert attempts["n"] == 3
        # Backoff: 1s, 2s entre los intentos 1→2 y 2→3
        assert sleeps == [1.0, 2.0]

    def test_exhausts_retries_then_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = {"n": 0}

        def fake_urlopen(req: object, timeout: int = 60) -> object:
            attempts["n"] += 1
            raise urllib.error.URLError("perma")

        sleeps: list[float] = []
        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(dl.time, "sleep", lambda s: sleeps.append(s))

        sha = dl.download_pdf(
            "https://www.diputados.gob.mx/x.pdf",
            tmp_path / "x.pdf",
            max_retries=2,
        )
        assert sha is None
        # 1 intento inicial + 2 reintentos = 3 calls
        assert attempts["n"] == 3
        # 2 backoffs (1s, 2s) entre los 3 intentos
        assert sleeps == [1.0, 2.0]

    def test_no_retries_when_max_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = {"n": 0}

        def fake_urlopen(req: object, timeout: int = 60) -> object:
            attempts["n"] += 1
            raise urllib.error.URLError("nope")

        sleeps: list[float] = []
        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(dl.time, "sleep", lambda s: sleeps.append(s))

        sha = dl.download_pdf(
            "https://www.diputados.gob.mx/x.pdf",
            tmp_path / "x.pdf",
            max_retries=0,
        )
        assert sha is None
        assert attempts["n"] == 1
        assert sleeps == []


# ---------------------------------------------------------------------------
# SHA-256: cálculo correcto + persistencia en catálogo
# ---------------------------------------------------------------------------


class TestDownloadPdfSha256:
    def test_returns_correct_sha256_hex(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import hashlib as _hashlib

        body = b"%PDF-1.4\n%alguna\n" + b"x" * 100
        expected = _hashlib.sha256(body).hexdigest()

        def fake_urlopen(req: object, timeout: int = 60) -> _FakeResponse:
            return _FakeResponse(body)

        monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
        sha = dl.download_pdf(
            "https://www.diputados.gob.mx/x.pdf", tmp_path / "x.pdf",
        )
        assert sha == expected


class TestMainAnnotatesSha:
    def test_catalog_gains_sha256_after_download(
        self,
        fake_main_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        laws = [_stub_law("1", "LA"), _stub_law("2", "LB")]
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)

        def fake_download(url: str, dest: Path, verbose: bool = False, **_kw: object) -> str:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"x")
            return _FAKE_SHA

        monkeypatch.setattr(dl, "download_pdf", fake_download)
        monkeypatch.setattr(
            sys, "argv",
            ["download_leyes.py", "-o", str(fake_main_env / "origen-docs")],
        )

        dl.main()
        catalog = json.loads(
            (fake_main_env / "catalogo.json").read_text(encoding="utf-8")
        )
        # Las dos leyes ahora tienen sha256
        assert all(law.get("sha256") == _FAKE_SHA for law in catalog)

    def test_catalog_unchanged_when_no_downloads(
        self,
        fake_main_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Si todas las descargas fallan, el catálogo NO se re-escribe con sha256
        laws = [_stub_law("1", "LA")]
        monkeypatch.setattr(dl, "fetch_index", lambda: laws)
        monkeypatch.setattr(dl, "download_pdf", lambda *a, **k: None)
        monkeypatch.setattr(
            sys, "argv",
            ["download_leyes.py", "-o", str(fake_main_env / "origen-docs")],
        )

        dl.main()
        catalog = json.loads(
            (fake_main_env / "catalogo.json").read_text(encoding="utf-8")
        )
        assert "sha256" not in catalog[0]
