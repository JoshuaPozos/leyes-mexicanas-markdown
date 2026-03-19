#!/usr/bin/env python3
"""
gen_indice.py — Genera INDICE.md con la lista de todas las leyes disponibles.

Lee el catálogo (catalogo.json) y verifica qué archivos .md existen en markdown/.

Uso:
    python scripts/gen_indice.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CATALOG_PATH = ROOT / "catalogo.json"
MARKDOWN_DIR = ROOT / "markdown"
INDEX_PATH = ROOT / "INDICE.md"


def main() -> None:
    if not CATALOG_PATH.exists():
        print("❌ No se encontró catalogo.json. Ejecuta primero: python scripts/download_leyes.py")
        sys.exit(1)

    with open(CATALOG_PATH, encoding="utf-8") as f:
        laws = json.load(f)

    # Check which markdowns exist
    existing_mds = {p.stem for p in MARKDOWN_DIR.glob("*.md")}

    lines = [
        "# 📇 Índice de Leyes Federales Vigentes",
        "",
        f"> Generado automáticamente desde el catálogo de [diputados.gob.mx](https://www.diputados.gob.mx/LeyesBiblio/index.htm).",
        f"> Total: **{len(laws)}** leyes catalogadas — **{len(existing_mds)}** disponibles en Markdown.",
        "",
        "---",
        "",
        "| No. | Ley | Última Reforma | Markdown |",
        "|----:|-----|---------------|:--------:|",
    ]

    for law in laws:
        num = law["numero"]
        nombre = law["nombre"]
        reforma = law["ultima_reforma"]
        slug = law["slug"]
        has_md = slug in existing_mds

        if has_md:
            md_link = f"[`{slug}.md`](markdown/{slug}.md)"
        else:
            md_link = "—"

        lines.append(f"| {num} | {nombre} | {reforma} | {md_link} |")

    lines.extend([
        "",
        "---",
        "",
        "## Cómo generar los Markdowns faltantes",
        "",
        "```bash",
        "# 1. Descargar los PDFs",
        "python scripts/download_leyes.py --skip-existing",
        "",
        "# 2. Convertir a Markdown",
        "python scripts/batch_convert.py --skip-existing",
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
    print(f"   {len(existing_mds)}/{len(laws)} leyes con Markdown disponible")


if __name__ == "__main__":
    main()
