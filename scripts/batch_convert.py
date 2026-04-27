#!/usr/bin/env python3
"""
batch_convert.py — Convierte todos los PDFs de origen-docs/ a Markdown.

Usa pdf_to_md.py internamente para cada archivo.

Uso:
    python scripts/batch_convert.py                    # Convierte todo
    python scripts/batch_convert.py --skip-existing    # Solo los nuevos
    python scripts/batch_convert.py --limit 5          # Solo 5
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _log import get_logger

logger = get_logger(__name__)

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "scripts"
PDF_TO_MD = SCRIPTS_DIR / "pdf_to_md.py"
ORIGEN_DIR = ROOT / "origen-docs"
MARKDOWN_DIR = ROOT / "markdown"
CANONICAL_DIR = ROOT / "canonical"
CATALOG_PATH = ROOT / "catalogo.json"


def load_catalog() -> dict[str, dict]:
    """Loads the catalog and returns a dict keyed by pdf_filename."""
    if not CATALOG_PATH.exists():
        return {}
    with open(CATALOG_PATH, encoding="utf-8") as f:
        laws = json.load(f)
    return {law["pdf_filename"]: law for law in laws}


def convert_pdf(pdf_path: Path, output_path: Path, title: str, verbose: bool,
                canonical_dir: Path | None = None, fmt: str = "both",
                validate: bool = False) -> bool:
    """Runs pdf_to_md.py on a single PDF. Returns True on success."""
    cmd = [
        sys.executable, str(PDF_TO_MD),
        str(pdf_path),
        "--output", str(output_path),
        "--title", title,
        "--format", fmt,
    ]
    if canonical_dir:
        cmd.extend(["--canonical-dir", str(canonical_dir)])
    if validate:
        cmd.append("--validate")
    if verbose:
        cmd.append("--verbose")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            logger.error("subprocess pdf_to_md.py falló para %s\n%s", pdf_path.name, stderr)
    return result.returncode == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convierte todos los PDFs en origen-docs/ a Markdown.",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="No re-convierte Markdowns que ya existen.",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limita la conversión a N archivos (0 = todos).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Muestra progreso detallado por página.",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "md", "both"],
        default="both",
        help="Formato de salida: json, md, o both (default: both).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Valida cada JSON contra el schema.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_catalog()

    pdfs = sorted(ORIGEN_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No se encontraron PDFs en {ORIGEN_DIR}/")
        print("Ejecuta primero: python scripts/download_leyes.py")
        sys.exit(1)

    subset = pdfs[:args.limit] if args.limit > 0 else pdfs
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    CANONICAL_DIR.mkdir(parents=True, exist_ok=True)

    converted = 0
    skipped = 0
    failed = 0

    for i, pdf_path in enumerate(subset, 1):
        # Obtener metadatos del catálogo
        info = catalog.get(pdf_path.name, {})
        md_slug = info.get("md_slug", pdf_path.stem)
        md_path = MARKDOWN_DIR / f"{md_slug}.md"
        title = info.get("nombre", pdf_path.stem.replace("_", " ").replace("-", " "))

        label = f"[{i}/{len(subset)}] {pdf_path.name}"

        json_path = CANONICAL_DIR / f"{md_slug}.json"

        if args.skip_existing and md_path.exists() and json_path.exists():
            print(f"  ⏭️  {label} → ya existe")
            skipped += 1
            continue

        print(f"  📄 {label} → {md_path.name}...", flush=True)
        if convert_pdf(pdf_path, md_path, title, args.verbose, CANONICAL_DIR,
                       fmt=args.format, validate=args.validate):
            print(f"     ✅ Listo")
            converted += 1
        else:
            print(f"     ❌ Error")
            failed += 1

    print(f"\n📊 Resultado: {converted} convertidos, {skipped} omitidos, {failed} errores")
    print(f"📁 Markdowns en: {MARKDOWN_DIR}")
    print(f"📁 JSON en:      {CANONICAL_DIR}")

    # Generar índice tras la conversión
    print("\n📇 Generando índice...")
    gen_index = SCRIPTS_DIR / "gen_indice.py"
    if gen_index.exists():
        subprocess.run([sys.executable, str(gen_index)])
    else:
        print("   ⚠️  gen_indice.py no encontrado, omitiendo índice.")


if __name__ == "__main__":
    main()
