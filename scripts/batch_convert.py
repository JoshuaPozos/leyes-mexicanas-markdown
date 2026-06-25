#!/usr/bin/env python3
"""
batch_convert.py — Convierte todos los PDFs de origen-docs/ a Markdown.

Usa pdf_to_md.py internamente para cada archivo. Por defecto paraleliza
las conversiones con `ProcessPoolExecutor(max_workers=os.cpu_count())`;
con `--workers 1` cae a ejecución secuencial inline (útil para tests y
para depurar fallos individuales).

Uso:
    python scripts/batch_convert.py                    # Convierte todo
    python scripts/batch_convert.py --skip-existing    # Solo los nuevos
    python scripts/batch_convert.py --limit 5          # Solo 5
    python scripts/batch_convert.py --workers 4        # Pool de 4 procesos
    python scripts/batch_convert.py --timeout 600      # 10 min por PDF
"""

import argparse
import functools
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from _log import get_logger
from constants import BATCH_CONVERT_TIMEOUT_SECS

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


def load_slug_filter(path: Path) -> set[str]:
    """Lee un archivo de md_slugs (uno por línea; ignora vacíos y comentarios `#`).
    Usado por --only-slugs para reconversión incremental tras download_leyes --apply."""
    slugs: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            slugs.add(stripped)
    return slugs


def convert_pdf(pdf_path: Path, output_path: Path, title: str, verbose: bool,
                canonical_dir: Path | None = None, fmt: str = "both",
                validate: bool = False,
                timeout_secs: int = BATCH_CONVERT_TIMEOUT_SECS) -> bool:
    """Runs pdf_to_md.py on a single PDF. Returns True on success.
    Aplica `timeout_secs` al subprocess: si se excede, el PDF se reporta
    como fallido (no cuelga el pool indefinidamente)."""
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

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_secs)
    except subprocess.TimeoutExpired:
        logger.error("subprocess pdf_to_md.py excedió timeout (%ds) para %s",
                     timeout_secs, pdf_path.name)
        return False
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            logger.error("subprocess pdf_to_md.py falló para %s\n%s", pdf_path.name, stderr)
    return result.returncode == 0


def _convert_task(
    pdf_path: Path, md_path: Path, title: str, *,
    verbose: bool, canonical_dir: Path, fmt: str, validate: bool, timeout_secs: int,
) -> bool:
    """Wrapper picklable de `convert_pdf` para enviar al ProcessPoolExecutor.
    Las funciones nested no son picklables con `spawn` (default en macOS/Win),
    por eso vive a nivel módulo y los flags fijos se inyectan con partial."""
    return convert_pdf(
        pdf_path, md_path, title, verbose, canonical_dir,
        fmt=fmt, validate=validate, timeout_secs=timeout_secs,
    )


def _resolve_workers(requested: int | None) -> int:
    """Resuelve max_workers: None/<=0 → os.cpu_count() (mínimo 1)."""
    if requested is not None and requested > 0:
        return requested
    return os.cpu_count() or 1


def _run_tasks(
    tasks: list[tuple[Path, Path, str]],
    convert_fn: Callable[[Path, Path, str], bool],
    max_workers: int,
) -> Iterator[tuple[Path, Path, bool]]:
    """Ejecuta `tasks` y emite `(pdf_path, md_path, ok)` por cada uno.
    Si `max_workers <= 1` ejecuta secuencial inline (útil en tests con
    monkeypatch de `subprocess.run`, que no se propaga a workers spawneados).
    Si `max_workers > 1` usa `ProcessPoolExecutor`; los resultados pueden
    llegar fuera del orden de entrada."""
    if max_workers <= 1:
        for pdf_path, md_path, title in tasks:
            yield pdf_path, md_path, convert_fn(pdf_path, md_path, title)
        return

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(convert_fn, pdf_path, md_path, title): (pdf_path, md_path)
            for (pdf_path, md_path, title) in tasks
        }
        for future in as_completed(futures):
            pdf_path, md_path = futures[future]
            try:
                ok = future.result()
            except Exception:
                logger.exception("Excepción inesperada convirtiendo %s", pdf_path.name)
                ok = False
            yield pdf_path, md_path, ok


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
    parser.add_argument(
        "--workers", "-w", type=int, default=None,
        help=("Procesos en paralelo (default: os.cpu_count()). "
              "Usa 1 para ejecución secuencial inline."),
    )
    parser.add_argument(
        "--timeout", type=int, default=BATCH_CONVERT_TIMEOUT_SECS,
        help=(f"Timeout (s) por PDF en el subprocess pdf_to_md.py "
              f"(default: {BATCH_CONVERT_TIMEOUT_SECS})."),
    )
    parser.add_argument(
        "--only-slugs", type=Path, default=None,
        help=("Reconvierte SOLO los md_slugs listados en este archivo (uno por "
              "línea), sin saltar por existencia (pdf_to_md sobreescribe en "
              "éxito). Para regen incremental tras `download_leyes.py --apply`."),
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

    only_slugs = load_slug_filter(args.only_slugs) if args.only_slugs else None
    seen_slugs: set[str] = set()

    # Fase 1 (serial): resolver metadatos y filtrar.
    tasks: list[tuple[Path, Path, str]] = []
    for pdf_path in subset:
        info = catalog.get(pdf_path.name, {})
        md_slug = info.get("md_slug", pdf_path.stem)
        md_path = MARKDOWN_DIR / f"{md_slug}.md"
        json_path = CANONICAL_DIR / f"{md_slug}.json"
        title = info.get("nombre", pdf_path.stem.replace("_", " ").replace("-", " "))

        if only_slugs is not None:
            # Modo incremental: solo los slugs del delta. Nunca aplica
            # skip-by-existence → siempre reconvierte. NO pre-borra la salida:
            # pdf_to_md sobreescribe en éxito y, si la conversión falla (p.ej.
            # timeout de LIGIE), la salida vieja queda intacta (no se pierde dato).
            if md_slug not in only_slugs:
                continue
            seen_slugs.add(md_slug)
        elif args.skip_existing and md_path.exists() and json_path.exists():
            print(f"  ⏭️  {pdf_path.name} → ya existe")
            skipped += 1
            continue

        tasks.append((pdf_path, md_path, title))

    if only_slugs is not None:
        missing = only_slugs - seen_slugs
        if missing:
            print(f"  ⚠️  {len(missing)} slug(s) sin PDF en origen-docs "
                  f"(no se reconvierten): {sorted(missing)}")

    # Fase 2 (paralela si workers>1): conversiones.
    max_workers = _resolve_workers(args.workers)
    if tasks:
        mode = "secuencial" if max_workers == 1 else f"paralelo (workers={max_workers})"
        print(f"\n🚀 Procesando {len(tasks)} PDFs en modo {mode}...\n", flush=True)

        convert_fn = functools.partial(
            _convert_task,
            verbose=args.verbose,
            canonical_dir=CANONICAL_DIR,
            fmt=args.format,
            validate=args.validate,
            timeout_secs=args.timeout,
        )

        total = len(tasks)
        for i, (pdf_path, md_path, ok) in enumerate(
            _run_tasks(tasks, convert_fn, max_workers), 1
        ):
            label = f"[{i}/{total}] {pdf_path.name} → {md_path.name}"
            if ok:
                print(f"  ✅ {label}")
                converted += 1
            else:
                print(f"  ❌ {label}")
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
