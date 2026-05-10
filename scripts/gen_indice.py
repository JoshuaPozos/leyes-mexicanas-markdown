#!/usr/bin/env python3
"""
gen_indice.py — Genera INDICE.md con la lista de todas las leyes disponibles.

Lee el catálogo (catalogo.json) y verifica qué archivos .md y .json existen.
Incluye conteo de artículos extraído de los JSON canónicos.

Uso:
    python scripts/gen_indice.py
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
CATALOG_PATH = ROOT / "catalogo.json"
MARKDOWN_DIR = ROOT / "markdown"
CANONICAL_DIR = ROOT / "canonical"
INDEX_PATH = ROOT / "INDICE.md"


def _count_articles(nodes: list) -> int:
    """Cuenta artículos recursivamente en la estructura del AST."""
    count = 0
    for n in nodes:
        if n.get("type") == "articulo":
            count += 1
        count += _count_articles(n.get("children", []))
    return count


def main() -> None:
    if not CATALOG_PATH.exists():
        print("❌ No se encontró catalogo.json. Ejecuta primero: python scripts/download_leyes.py")
        sys.exit(1)

    with open(CATALOG_PATH, encoding="utf-8") as f:
        laws = json.load(f)

    # Verificar qué markdowns y JSONs existen
    existing_mds = {p.stem for p in MARKDOWN_DIR.glob("*.md")}
    existing_jsons = {p.stem for p in CANONICAL_DIR.glob("*.json")} if CANONICAL_DIR.exists() else set()

    # Leer conteo de artículos de cada JSON canónico
    article_counts: dict[str, int] = {}
    for stem in existing_jsons:
        json_path = CANONICAL_DIR / f"{stem}.json"
        try:
            with open(json_path, encoding="utf-8") as f:
                ast = json.load(f)
            article_counts[stem] = _count_articles(ast.get("structure", []))
        except (json.JSONDecodeError, OSError):
            article_counts[stem] = 0

    total = len(laws)
    done_md = len(existing_mds)
    done_json = len(existing_jsons)
    total_arts = sum(article_counts.values())

    today = date.today().strftime("%d/%m/%Y")

    lines = [
        "# 📇 Índice de Leyes Federales Vigentes",
        "",
        "> Generado automáticamente desde el catálogo de [diputados.gob.mx](https://www.diputados.gob.mx/LeyesBiblio/index.htm).  ",
        f"> Última actualización: **{today}** — **{done_md}/{total}** Markdown, **{done_json}/{total}** JSON canónico — **{total_arts:,}** artículos.",
        "",
        "---",
        "",
        "| No. | Ley | Última Reforma | Arts. | Markdown | JSON |",
        "|----:|-----|---------------|------:|:--------:|:----:|",
    ]

    for law in laws:
        num = law["numero"]
        nombre = law["nombre"]
        reforma = law["ultima_reforma"]
        md_slug = law.get("md_slug", law.get("slug", ""))

        has_md = md_slug in existing_mds
        has_json = md_slug in existing_jsons
        art_count = article_counts.get(md_slug, 0)

        md_link = f"[`.md`](markdown/{md_slug}.md)" if has_md else "—"
        json_link = f"[`.json`](canonical/{md_slug}.json)" if has_json else "—"

        lines.append(f"| {num} | {nombre} | {reforma} | {art_count:,} | {md_link} | {json_link} |")

    lines.extend([
        "",
        "---",
        "",
        "## Cómo generar los archivos",
        "",
        "```bash",
        "# 1. Descargar los PDFs",
        "python scripts/download_leyes.py --skip-existing",
        "",
        "# 2. Convertir a Markdown + JSON canónico",
        "python scripts/batch_convert.py --skip-existing",
        "",
        "# 3. Solo Markdown",
        "python scripts/batch_convert.py --format md",
        "",
        "# 4. Solo JSON",
        "python scripts/batch_convert.py --format json",
        "```",
        "",
        "El índice se regenera automáticamente al correr `batch_convert.py`, o manualmente con:",
        "",
        "```bash",
        "python scripts/gen_indice.py",
        "```",
    ])

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"✅ Índice generado → {INDEX_PATH}")
    print(f"   {done_md}/{total} Markdown, {done_json}/{total} JSON — {total_arts:,} artículos")


if __name__ == "__main__":
    main()
