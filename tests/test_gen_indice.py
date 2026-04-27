"""Tests para scripts/gen_indice.py — generación de INDICE.md."""

from __future__ import annotations

import json
from pathlib import Path

import gen_indice as gi
import pytest

# ---------------------------------------------------------------------------
# _count_articles (helper puro recursivo)
# ---------------------------------------------------------------------------


class TestCountArticles:
    def test_empty_list(self) -> None:
        assert gi._count_articles([]) == 0

    def test_flat_list_of_articles(self) -> None:
        nodes = [
            {"type": "articulo"},
            {"type": "articulo"},
            {"type": "articulo"},
        ]
        assert gi._count_articles(nodes) == 3

    def test_ignores_non_article_nodes(self) -> None:
        nodes = [
            {"type": "titulo"},
            {"type": "capitulo"},
            {"type": "seccion"},
        ]
        assert gi._count_articles(nodes) == 0

    def test_counts_articles_inside_children(self) -> None:
        nodes = [
            {
                "type": "titulo",
                "children": [
                    {"type": "articulo"},
                    {"type": "articulo"},
                ],
            }
        ]
        assert gi._count_articles(nodes) == 2

    def test_deeply_nested_structure(self) -> None:
        nodes = [
            {
                "type": "titulo",
                "children": [
                    {
                        "type": "capitulo",
                        "children": [
                            {
                                "type": "seccion",
                                "children": [
                                    {"type": "articulo"},
                                    {"type": "articulo"},
                                ],
                            },
                            {"type": "articulo"},
                        ],
                    },
                    {"type": "articulo"},
                ],
            },
            {"type": "articulo"},
        ]
        assert gi._count_articles(nodes) == 5

    def test_node_without_children_key(self) -> None:
        # `n.get("children", [])` cubre el caso sin la clave
        nodes = [{"type": "articulo"}, {"type": "titulo"}]
        assert gi._count_articles(nodes) == 1


# ---------------------------------------------------------------------------
# main() — fixture común que redirige todas las rutas a tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige los paths de gen_indice a un repo temporal y lo devuelve."""
    catalog = tmp_path / "catalogo.json"
    markdown_dir = tmp_path / "markdown"
    canonical_dir = tmp_path / "canonical"
    index = tmp_path / "INDICE.md"

    markdown_dir.mkdir()
    canonical_dir.mkdir()

    monkeypatch.setattr(gi, "ROOT", tmp_path)
    monkeypatch.setattr(gi, "CATALOG_PATH", catalog)
    monkeypatch.setattr(gi, "MARKDOWN_DIR", markdown_dir)
    monkeypatch.setattr(gi, "CANONICAL_DIR", canonical_dir)
    monkeypatch.setattr(gi, "INDEX_PATH", index)

    return tmp_path


def _write_catalog(root: Path, laws: list[dict]) -> None:
    (root / "catalogo.json").write_text(json.dumps(laws), encoding="utf-8")


def _write_markdown(root: Path, slug: str) -> None:
    (root / "markdown" / f"{slug}.md").write_text(f"# {slug}\n", encoding="utf-8")


def _write_canonical(root: Path, slug: str, structure: list) -> None:
    (root / "canonical" / f"{slug}.json").write_text(
        json.dumps({"structure": structure}), encoding="utf-8"
    )


class TestMainExit:
    def test_exits_when_catalog_missing(
        self, fake_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # No escribimos catalogo.json → debe salir con sys.exit(1)
        with pytest.raises(SystemExit) as exc:
            gi.main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "catalogo.json" in captured.out


class TestMainHappyPath:
    def test_index_is_generated(self, fake_repo: Path) -> None:
        _write_catalog(
            fake_repo,
            [
                {
                    "numero": 1,
                    "nombre": "Constitución Política",
                    "ultima_reforma": "01/01/2024",
                    "md_slug": "CPEUM_constitucion",
                }
            ],
        )
        _write_markdown(fake_repo, "CPEUM_constitucion")
        _write_canonical(
            fake_repo,
            "CPEUM_constitucion",
            [{"type": "articulo"}, {"type": "articulo"}],
        )

        gi.main()

        index = (fake_repo / "INDICE.md").read_text(encoding="utf-8")
        assert "Índice de Leyes Federales Vigentes" in index
        assert "Constitución Política" in index
        assert "CPEUM_constitucion" in index
        assert "1/1" in index  # done_md/total y done_json/total

    def test_includes_md_and_json_links_when_present(self, fake_repo: Path) -> None:
        _write_catalog(
            fake_repo,
            [
                {
                    "numero": 1,
                    "nombre": "Ley X",
                    "ultima_reforma": "01/01/2024",
                    "md_slug": "LX_ley_x",
                }
            ],
        )
        _write_markdown(fake_repo, "LX_ley_x")
        _write_canonical(fake_repo, "LX_ley_x", [{"type": "articulo"}])

        gi.main()

        index = (fake_repo / "INDICE.md").read_text(encoding="utf-8")
        assert "[`.md`](markdown/LX_ley_x.md)" in index
        assert "[`.json`](canonical/LX_ley_x.json)" in index

    def test_dash_when_files_missing(self, fake_repo: Path) -> None:
        _write_catalog(
            fake_repo,
            [
                {
                    "numero": 1,
                    "nombre": "Ley Inexistente",
                    "ultima_reforma": "01/01/2024",
                    "md_slug": "LI_ley",
                }
            ],
        )
        # No creamos ni .md ni .json para este slug

        gi.main()

        index = (fake_repo / "INDICE.md").read_text(encoding="utf-8")
        # Debe haber dos guiones de placeholder en la fila (md y json)
        row = next(ln for ln in index.splitlines() if "Ley Inexistente" in ln)
        assert row.count(" — ") >= 2

    def test_falls_back_to_slug_when_md_slug_missing(self, fake_repo: Path) -> None:
        _write_catalog(
            fake_repo,
            [
                {
                    "numero": 1,
                    "nombre": "Ley Vieja",
                    "ultima_reforma": "01/01/2024",
                    "slug": "LV_ley_vieja",
                }
            ],
        )
        _write_markdown(fake_repo, "LV_ley_vieja")

        gi.main()

        index = (fake_repo / "INDICE.md").read_text(encoding="utf-8")
        assert "LV_ley_vieja" in index

    def test_handles_broken_canonical_json(self, fake_repo: Path) -> None:
        _write_catalog(
            fake_repo,
            [
                {
                    "numero": 1,
                    "nombre": "Ley Rota",
                    "ultima_reforma": "01/01/2024",
                    "md_slug": "LR_rota",
                }
            ],
        )
        _write_markdown(fake_repo, "LR_rota")
        # JSON inválido → debe atrapar JSONDecodeError y poner 0 artículos
        (fake_repo / "canonical" / "LR_rota.json").write_text(
            "{ no soy json valido", encoding="utf-8"
        )

        gi.main()  # no debe explotar

        index = (fake_repo / "INDICE.md").read_text(encoding="utf-8")
        assert "Ley Rota" in index

    def test_works_when_canonical_dir_does_not_exist(
        self, fake_repo: Path
    ) -> None:
        # Borrar el dir canonical para activar la rama `if CANONICAL_DIR.exists()`
        canonical_dir = fake_repo / "canonical"
        canonical_dir.rmdir()

        _write_catalog(
            fake_repo,
            [
                {
                    "numero": 1,
                    "nombre": "Solo MD",
                    "ultima_reforma": "01/01/2024",
                    "md_slug": "SM_solo",
                }
            ],
        )
        _write_markdown(fake_repo, "SM_solo")

        gi.main()

        index = (fake_repo / "INDICE.md").read_text(encoding="utf-8")
        assert "Solo MD" in index
        # 0 JSON en el header
        assert "0/1** JSON" in index

    def test_total_articles_is_sum_across_laws(self, fake_repo: Path) -> None:
        _write_catalog(
            fake_repo,
            [
                {
                    "numero": 1,
                    "nombre": "Ley A",
                    "ultima_reforma": "01/01/2024",
                    "md_slug": "LA_a",
                },
                {
                    "numero": 2,
                    "nombre": "Ley B",
                    "ultima_reforma": "02/02/2024",
                    "md_slug": "LB_b",
                },
            ],
        )
        _write_markdown(fake_repo, "LA_a")
        _write_markdown(fake_repo, "LB_b")
        _write_canonical(
            fake_repo,
            "LA_a",
            [{"type": "articulo"}, {"type": "articulo"}, {"type": "articulo"}],
        )
        _write_canonical(
            fake_repo,
            "LB_b",
            [
                {
                    "type": "titulo",
                    "children": [{"type": "articulo"}, {"type": "articulo"}],
                }
            ],
        )

        gi.main()

        index = (fake_repo / "INDICE.md").read_text(encoding="utf-8")
        # 3 + 2 = 5 artículos
        assert "**5** artículos" in index

    def test_includes_usage_section(self, fake_repo: Path) -> None:
        _write_catalog(fake_repo, [])

        gi.main()

        index = (fake_repo / "INDICE.md").read_text(encoding="utf-8")
        assert "## Cómo generar los archivos" in index
        assert "python scripts/download_leyes.py" in index
        assert "python scripts/batch_convert.py" in index
        assert "python scripts/gen_indice.py" in index

    def test_index_ends_with_newline(self, fake_repo: Path) -> None:
        _write_catalog(fake_repo, [])
        gi.main()
        content = (fake_repo / "INDICE.md").read_text(encoding="utf-8")
        assert content.endswith("\n")

    def test_prints_summary_on_stdout(
        self, fake_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_catalog(
            fake_repo,
            [
                {
                    "numero": 1,
                    "nombre": "Ley X",
                    "ultima_reforma": "01/01/2024",
                    "md_slug": "LX_x",
                }
            ],
        )
        _write_markdown(fake_repo, "LX_x")
        _write_canonical(fake_repo, "LX_x", [{"type": "articulo"}])

        gi.main()
        captured = capsys.readouterr()
        assert "Índice generado" in captured.out
        assert "1/1 Markdown" in captured.out
        assert "1/1 JSON" in captured.out
