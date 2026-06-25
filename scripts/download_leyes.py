#!/usr/bin/env python3
"""
download_leyes.py — Descarga los PDFs de todas las leyes federales vigentes
desde la Cámara de Diputados (diputados.gob.mx).

Uso:
    python scripts/download_leyes.py                  # Descarga todo
    python scripts/download_leyes.py --list           # Solo muestra el catálogo
    python scripts/download_leyes.py --limit 5        # Solo las primeras 5
    python scripts/download_leyes.py --skip-existing   # No re-descarga
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from _log import get_logger
from constants import (
    ACRONYM_MAX_LENGTH,
    ALLOWED_DOWNLOAD_HOSTS,
    BETWEEN_DOWNLOADS_SLEEP_SECS,
    DOWNLOAD_BACKOFF_BASE_SECS,
    DOWNLOAD_MAX_RETRIES,
    INDEX_FETCH_TIMEOUT_SECS,
    MIN_SANE_LAW_COUNT,
    PDF_DOWNLOAD_TIMEOUT_SECS,
    PDF_MAGIC_BYTES,
    SLUG_MAX_LENGTH,
)

logger = get_logger(__name__)

BASE_URL = "https://www.diputados.gob.mx/LeyesBiblio/"
INDEX_URL = BASE_URL + "index.htm"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) mx-md/1.0"

ROOT = Path(__file__).parent.parent
ORIGEN_DIR = ROOT / "origen-docs"
CATALOG_PATH = ROOT / "catalogo.json"
STATE_PATH = ROOT / "estado.json"
MARKDOWN_DIR = ROOT / "markdown"
CANONICAL_DIR = ROOT / "canonical"
ARCHIVE_DIR = ROOT / "archive"  # leyes abrogadas / bajas (fuera del set vigente)


# ---------------------------------------------------------------------------
# Regex pre-compilados (usados dentro de loops sobre filas / leyes / palabras)
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r'\s+')
_LAW_NAME_TRAILING_RE = re.compile(
    r'\s*(Nueva reforma|Ley en vigor.*|Ley Abrogada.*)$',
    re.IGNORECASE,
)
_SLUG_NON_ALNUM_RE = re.compile(r'[^a-z0-9]+')
_PDF_STEM_NUMERIC_SUFFIX_RE = re.compile(r'_\d+$')
_ACRONYM_CLAUSE_BREAK_RE = re.compile(r'[,(]')
_ACRONYM_WORD_BREAK_RE = re.compile(r'[\s\-/]+')


# ---------------------------------------------------------------------------
# Análisis HTML
# ---------------------------------------------------------------------------

class LeyesTableParser(HTMLParser):
    """Analiza la tabla de leyes de diputados.gob.mx/LeyesBiblio/index.htm"""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self._in_tr = False
        self._in_td = False
        self._td_index = 0
        self._current_row: dict = {}
        self._current_text = ""
        self._current_links: list[str] = []
        self._row_links: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "tr":
            self._in_tr = True
            self._td_index = 0
            self._current_row = {}
            self._row_links = []
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._current_text = ""
            self._current_links = []
        elif tag == "a" and self._in_td:
            href = attrs_dict.get("href", "")
            if href:
                self._current_links.append(href)
                # Acumular links de TODAS las celdas: el link ref/<abrev>.htm
                # vive en la celda del título (td 1), no en la de descargas (td 3).
                self._row_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_td:
            self._in_td = False
            text = _WHITESPACE_RE.sub(' ', self._current_text).strip()

            if self._td_index == 0:
                self._current_row["numero"] = text
            elif self._td_index == 1:
                self._current_row["nombre_raw"] = text
            elif self._td_index == 2:
                self._current_row["ultima_reforma"] = text
            elif self._td_index == 3:
                self._current_row["links"] = self._current_links[:]

            self._td_index += 1
        elif tag == "tr" and self._in_tr:
            self._in_tr = False
            self._current_row["all_links"] = self._row_links[:]
            if "numero" in self._current_row and "links" in self._current_row:
                self.rows.append(self._current_row)

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._current_text += data


def parse_law_name(raw: str) -> tuple[str, str]:
    """
    Extrae nombre limpio y fecha DOF del texto raw de la celda.
    Devuelve (nombre, dof_date).
    """
    # Eliminar notas "(Abrogado...)" y "(Antes ...)" del nombre,
    # pero conservarlas como referencia
    lines = raw.split("DOF")
    nombre = lines[0].strip().rstrip()
    # Limpiar espacios sobrantes, 'Nueva reforma', etc.
    nombre = _LAW_NAME_TRAILING_RE.sub('', nombre).strip()

    dof_date = ""
    if len(lines) > 1:
        dof_date = "DOF" + lines[1].strip().split("(")[0].strip()
        dof_date = _WHITESPACE_RE.sub(' ', dof_date).strip()

    return nombre, dof_date


def slugify(text: str, max_len: int = SLUG_MAX_LENGTH) -> str:
    """Convierte texto a slug snake_case ASCII."""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower()
    text = _SLUG_NON_ALNUM_RE.sub('_', text)
    text = text.strip('_')
    if len(text) > max_len:
        text = text[:max_len].rstrip('_')
    return text


_STOP_WORDS = {
    'de', 'del', 'la', 'las', 'los', 'el', 'en', 'y', 'e', 'o', 'u', 'a',
    'al', 'con', 'por', 'para', 'que', 'se', 'su', 'sus', 'un', 'una',
    'sobre', 'entre', 'ante', 'sin', 'si', 'no', 'lo',
}

def derive_acronym(nombre: str, max_len: int = ACRONYM_MAX_LENGTH) -> str:
    """
    Deriva un acrónimo del nombre de la ley tomando la primera letra de cada
    palabra significativa en la cláusula principal (antes de la primera coma
    o paréntesis), ignorando las palabras vacías. Máximo max_len caracteres.
    Ej. 'ESTATUTO de Gobierno del Distrito Federal' -> 'EGDF'
        'IMPUESTO sobre Servicios Expresamente Declarados...' -> 'ISEDIP'
    """
    # Tomar solo la cláusula principal (antes de la primera coma o paréntesis)
    main = _ACRONYM_CLAUSE_BREAK_RE.split(nombre)[0].strip()
    words = _ACRONYM_WORD_BREAK_RE.split(main)
    letters = [
        w[0].upper()
        for w in words
        if w and w.lower() not in _STOP_WORDS and w[0].isalpha()
    ]
    return ''.join(letters[:max_len]) or 'LEY'


def compute_md_slug(pdf_stem: str, nombre: str, numero: str) -> str:
    """
    Construye el slug de nombre de archivo: {ABREV}_{nombre_snake}.
    Usa el stem del PDF como abreviatura si parece un acrónimo (empieza con letra),
    eliminando cualquier sufijo numérico al final (ej. LCEC_120419 → LCEC).
    Si no, deriva un acrónimo del nombre de la ley.
    """
    name_slug = slugify(nombre)
    if len(pdf_stem) > 0 and not pdf_stem[0].isdigit():
        # Eliminar sufijo numérico al final (ej. _120419, _270614)
        abbrev = _PDF_STEM_NUMERIC_SUFFIX_RE.sub('', pdf_stem)
    else:
        abbrev = derive_acronym(nombre)
    return f"{abbrev}_{name_slug}"


def fetch_index() -> list[dict]:
    """Obtiene y analiza la página del índice de leyes. Devuelve lista de dicts."""
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": USER_AGENT})
    html = urllib.request.urlopen(req, timeout=INDEX_FETCH_TIMEOUT_SECS).read().decode("latin-1")

    parser = LeyesTableParser()
    parser.feed(html)

    laws = []
    for row in parser.rows:
        numero = row.get("numero", "").strip()
        # Saltar la fila de encabezado
        if not numero or numero.lower() == "no.":
            continue

        nombre, dof = parse_law_name(row.get("nombre_raw", ""))
        ultima_reforma = row.get("ultima_reforma", "").strip()

        # Buscar el enlace al PDF (no pdf_mov)
        pdf_href = ""
        for link in row.get("links", []):
            if link.startswith("pdf/") and link.endswith(".pdf"):
                pdf_href = link
                break

        if not pdf_href:
            continue

        pdf_filename_origen = pdf_href.split("/")[-1]
        pdf_stem = Path(pdf_filename_origen).stem
        pdf_url = BASE_URL + pdf_href
        md_slug = compute_md_slug(pdf_stem, nombre, numero)
        pdf_filename = f"{md_slug}.pdf"

        # ref/<abrev>.htm: id canónico del historial de reformas, estable ante
        # renombrados del PDF (p.ej. el PDF pasa de 28_*.pdf a LCE.pdf pero el
        # ref sigue siendo lce.htm). Llave de join semántica preferida.
        ref_abbrev = ""
        for link in row.get("all_links", []):
            if link.startswith("ref/") and link.endswith(".htm"):
                ref_abbrev = Path(link.split("/")[-1]).stem.lower()
                break

        # Abrogación: diputados marca la ley con "Ley Abrogada" en la celda del
        # nombre y/o numero == 'A' (p.ej. LFC, reemplazada por LFCA). No es una
        # reforma: la ley deja de estar vigente → se archiva, no se actualiza, y su
        # 'A' nunca debe escribirse como catalog_number. Señal EXPLÍCITA (no
        # "not isdigit", que falsamente marcaría una ley vigente con numero glitcheado).
        # Case-insensitive: el HTML de diputados es inconsistente y el limpiador de
        # nombres (`_LAW_NAME_TRAILING_RE`) ya usa IGNORECASE — deben coincidir.
        abrogated = ("ley abrogada" in row.get("nombre_raw", "").lower()) or (numero == "A")

        laws.append({
            "numero": numero,
            "nombre": nombre,
            "dof": dof,
            "ultima_reforma": ultima_reforma,
            "pdf_url": pdf_url,
            "pdf_filename": pdf_filename,
            "pdf_filename_origen": pdf_filename_origen,
            "md_slug": md_slug,
            "ref_abbrev": ref_abbrev,
            "abrogated": abrogated,
        })

    return laws


# ---------------------------------------------------------------------------
# Detección de deltas upstream (estado.json / --check / --init-snapshot)
# ---------------------------------------------------------------------------

def _state_key(law: dict) -> str:
    """Llave de join semántica: el `ref_abbrev` (id del historial ref/<abrev>.htm,
    estable aun cuando el PDF se renombra de código numérico a acrónimo) cuando
    existe; si no, fallback al stem del filename de origen. En ambos caminos se
    quita el sufijo numérico de fecha/año (`ref lif_2026`→`lif`, `LIGIE_2022`→
    `ligie`, `LCEC_120419`→`lcec`) para que las leyes anuales colapsen como
    CAMBIADA y no como BAJA+ALTA. En minúsculas. Verificado único 317/317."""
    ref = (law.get("ref_abbrev") or "").strip().lower()
    if ref:
        return _PDF_STEM_NUMERIC_SUFFIX_RE.sub('', ref)
    stem = _PDF_STEM_NUMERIC_SUFFIX_RE.sub('', Path(law["pdf_filename_origen"]).stem)
    return stem.lower()


def _normalize_reforma(value: str) -> str:
    """Normaliza 'última reforma' para comparar: colapsa espacios, trim, casefold.
    Comparación de string CRUDO (nunca fecha parseada), robusta para los casos
    no-DOF ('Sin reforma', 'Notificación … Sentencia SCJN')."""
    return _WHITESPACE_RE.sub(' ', value or '').strip().casefold()


def _law_to_state_entry(law: dict) -> dict:
    """Proyecta una ley de fetch_index() a una entrada de estado (sin la fecha
    de snapshot, que añade el persistidor)."""
    return {
        "key": _state_key(law),
        "ref_abbrev": (law.get("ref_abbrev") or "").strip().lower() or None,
        "pdf_filename_origen": law["pdf_filename_origen"],
        "md_slug": law["md_slug"],
        "pdf_url": law["pdf_url"],
        "ultima_reforma_raw": law.get("ultima_reforma", ""),
        "pdf_sha256": law.get("sha256"),
    }


def diff_catalog(old_entries: list[dict], new_entries: list[dict]) -> dict:
    """Diff puro entre dos listas de entradas de estado (con 'key' y
    'ultima_reforma_raw'). Devuelve {'changed', 'added', 'removed'}.

    - CAMBIADA: misma llave, 'ultima_reforma_raw' normalizado difiere.
    - ALTA:     llave en new, ausente de old.
    - BAJA:     llave en old, ausente de new.
    """
    old_by = {e["key"]: e for e in old_entries}
    new_by = {e["key"]: e for e in new_entries}
    old_keys, new_keys = set(old_by), set(new_by)

    added = sorted((new_by[k] for k in new_keys - old_keys), key=lambda e: e["key"])
    removed = sorted((old_by[k] for k in old_keys - new_keys), key=lambda e: e["key"])
    changed = []
    for k in sorted(old_keys & new_keys):
        old_e, new_e = old_by[k], new_by[k]
        if _normalize_reforma(old_e.get("ultima_reforma_raw", "")) != \
                _normalize_reforma(new_e.get("ultima_reforma_raw", "")):
            changed.append({
                "key": k,
                "md_slug": new_e.get("md_slug"),
                "from": old_e.get("ultima_reforma_raw", ""),
                "to": new_e.get("ultima_reforma_raw", ""),
                "pdf_url": new_e.get("pdf_url"),
            })
    return {"changed": changed, "added": added, "removed": removed}


def _atomic_write_json(path: Path, data: object) -> None:
    """Escribe JSON de forma atómica: archivo temporal + os.replace (atómico en
    el mismo FS). Evita dejar el ledger truncado si el proceso muere a media
    escritura (estado.json/catalogo.json no están en git → no hay rollback)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_state() -> list[dict] | None:
    """Lee estado.json (lista de entradas) o None si no existe. Aborta con un
    mensaje claro (no un stacktrace) si el archivo está corrupto."""
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"❌ {STATE_PATH.name} está ilegible/corrupto ({e}). "
            f"Regenera con --init-snapshot.",
            file=sys.stderr,
        )
        raise SystemExit(2) from e


def save_state(entries: list[dict]) -> None:
    """Escribe estado.json atómicamente, mismo formato que catalogo.json."""
    _atomic_write_json(STATE_PATH, entries)


def _format_delta_report(diff: dict) -> str:
    """Reporte markdown legible del diff de deltas."""
    changed, added, removed = diff["changed"], diff["added"], diff["removed"]
    total = len(changed) + len(added) + len(removed)
    lines = ["# Deltas upstream (index.htm vs estado.json)", ""]
    if not total:
        lines.append("✅ Sin cambios: el corpus está al día con la fuente.")
        return "\n".join(lines)
    lines.append(
        f"**{total} deltas**: {len(changed)} cambiadas · "
        f"{len(added)} altas · {len(removed)} bajas."
    )
    if changed:
        lines += ["", f"## Cambiadas ({len(changed)})"]
        lines += [f"- `{c['key']}` ({c['md_slug']}): «{c['from']}» → «{c['to']}»" for c in changed]
    if added:
        lines += ["", f"## Altas ({len(added)})"]
        lines += [f"- `{a['key']}` ({a['md_slug']})" for a in added]
    if removed:
        lines += ["", f"## Bajas ({len(removed)})"]
        lines += [f"- `{r['key']}` ({r['md_slug']})" for r in removed]
    return "\n".join(lines)


def init_snapshot() -> None:
    """Bootstrap: graba estado.json desde el índice vivo, sin descargar PDFs."""
    print("📡 Obteniendo índice para snapshot...", flush=True)
    laws = fetch_index()
    today = datetime.date.today().isoformat()
    entries = [{**_law_to_state_entry(law), "snapshot_date": today} for law in laws]
    save_state(entries)
    print(f"💾 estado.json escrito con {len(entries)} leyes ({STATE_PATH}).")


def run_check(report_path: Path | None = None) -> int:
    """Diff read-only del índice vivo vs estado.json. NO escribe catálogo ni
    estado. Exit code: 0 limpio, 10 hay deltas, 2 inconcluso."""
    state = load_state()
    if state is None:
        print(
            f"❌ No existe {STATE_PATH.name}. Corre primero: "
            f"python scripts/download_leyes.py --init-snapshot",
            file=sys.stderr,
        )
        return 2
    try:
        laws = fetch_index()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        print(f"❌ Fetch del índice falló ({e}); inconcluso.", file=sys.stderr)
        return 2
    if len(laws) < MIN_SANE_LAW_COUNT:
        print(
            f"❌ El índice devolvió {len(laws)} leyes (< {MIN_SANE_LAW_COUNT}); "
            f"parseo sospechoso. Inconcluso — no se interpretan bajas.",
            file=sys.stderr,
        )
        return 2
    diff = diff_catalog(state, [_law_to_state_entry(law) for law in laws])
    report = _format_delta_report(diff)
    print(report)
    if report_path is not None:
        report_path.write_text(report + "\n", encoding="utf-8")
        print(f"\n📝 Reporte escrito en {report_path}.")
    total = len(diff["changed"]) + len(diff["added"]) + len(diff["removed"])
    return 10 if total else 0


def _archive_law(md_slug: str) -> list[str]:
    """Mueve los artefactos de una ley (markdown + canonical + su PDF) a archive/,
    sacándola del set vigente SIN borrar (git history aparte). Devuelve las rutas
    archivadas, relativas a la raíz."""
    moved: list[str] = []
    for src, dst in [
        (MARKDOWN_DIR / f"{md_slug}.md", ARCHIVE_DIR / "markdown" / f"{md_slug}.md"),
        (CANONICAL_DIR / f"{md_slug}.json", ARCHIVE_DIR / "canonical" / f"{md_slug}.json"),
        (ORIGEN_DIR / f"{md_slug}.pdf", ARCHIVE_DIR / "origen-docs" / f"{md_slug}.pdf"),
    ]:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
            moved.append(str(dst.relative_to(ROOT)))
    return moved


def run_apply(dry_run: bool = False, delta_path: Path | None = None) -> int:
    """Aplica el delta upstream al corpus: descarga las cambiadas+altas (avanza
    estado Y catálogo por ley), y ARCHIVA las abrogadas/bajas (las saca del set
    vigente a archive/, las quita del catálogo+estado). Escribe `delta.txt`
    (md_slugs a reconvertir) + `expected_drift.txt`. NO reconvierte — eso lo hace
    `batch_convert.py --only-slugs delta.txt`. Refrescar el catálogo es clave:
    gen_indice y pdf_to_md lo leen como fuente de verdad. Exit 0/2/10."""
    state = load_state()
    if state is None:
        print(
            f"❌ No existe {STATE_PATH.name}. Corre primero: "
            f"python scripts/download_leyes.py --init-snapshot",
            file=sys.stderr,
        )
        return 2
    if not CATALOG_PATH.exists():
        print(f"❌ No existe {CATALOG_PATH.name}; --apply requiere el catálogo.", file=sys.stderr)
        return 2
    try:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"❌ {CATALOG_PATH.name} ilegible/corrupto ({e}).", file=sys.stderr)
        return 2
    try:
        laws = fetch_index()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        print(f"❌ Fetch del índice falló ({e}); inconcluso.", file=sys.stderr)
        return 2
    if len(laws) < MIN_SANE_LAW_COUNT:
        print(
            f"❌ El índice devolvió {len(laws)} leyes (< {MIN_SANE_LAW_COUNT}); "
            f"parseo sospechoso. Inconcluso.",
            file=sys.stderr,
        )
        return 2

    law_by_key = {_state_key(law): law for law in laws}
    new_entries = [_law_to_state_entry(law) for law in laws]
    new_by_key = {e["key"]: e for e in new_entries}
    diff = diff_catalog(state, new_entries)
    state_by_key = {e["key"]: e for e in state}

    # Archivar: leyes nuestras que upstream marca ABROGADA, + BAJAS (quitadas del
    # índice). Salen del set vigente a archive/, no se actualizan.
    to_archive: list[tuple[str | None, str, str]] = [
        (key, entry["md_slug"], "abrogada")
        for key, entry in state_by_key.items()
        if (law_by_key.get(key) or {}).get("abrogated")
    ] + [(r["key"], r["md_slug"], "baja") for r in diff["removed"]]
    archived_keys = {k for k, _, _ in to_archive}

    # targets = cambiadas + altas, EXCLUYENDO abrogadas y altas-abrogadas.
    targets: list[tuple[str, str, str]] = [
        (c["key"], c.get("from", ""), c.get("to", ""))
        for c in diff["changed"] if c["key"] not in archived_keys
    ] + [
        (a["key"], "(alta)", a.get("ultima_reforma_raw", ""))
        for a in diff["added"] if not law_by_key[a["key"]].get("abrogated")
    ]

    if to_archive:
        print(
            f"🗄️  {len(to_archive)} ley(es) a archivar (abrogadas/bajas): "
            f"{[(m, why) for _, m, why in to_archive]}"
        )
    n_altas = sum(1 for a in diff["added"] if not law_by_key[a["key"]].get("abrogated"))
    if n_altas:
        print(
            f"⚠️  {n_altas} alta(s) — se descargan, pero su golden requiere tu "
            f"revisión visual antes de entrar al baseline."
        )
    if not targets and not to_archive:
        print("✅ Sin deltas que aplicar; el corpus está al día con la fuente.")
        return 0

    if targets:
        print(f"📥 {len(targets)} leyes a actualizar (cambiadas + altas).")
        if any("ligie" in new_by_key[k]["md_slug"].lower() for k, _, _ in targets):
            print(
                "⚠️  LIGIE está en el delta: al reconvertir usa "
                "`batch_convert.py --only-slugs … --timeout 1200` o conviértela aparte."
            )
    if dry_run:
        for key, frm, to in targets:
            print(f"   [dry-run] actualizar {new_by_key[key]['md_slug']}: {frm} → {to}")
        for _, md, why in to_archive:
            print(f"   [dry-run] archivar {md} ({why})")
        return 10

    # Resolver salida y fallar-rápido sobre el dir ANTES de tocar red/estado (B4):
    # un --delta-out a un dir inexistente no debe reventar tras avanzar el estado.
    out = delta_path or (ROOT / "delta.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.read_text(encoding="utf-8").strip():
        print(f"⚠️  {out.name} tenía un delta previo sin convertir; se sobreescribe.")

    cat_by_md = {c["md_slug"]: c for c in catalog}
    today = datetime.date.today().isoformat()
    delta_slugs: list[str] = []
    drift_lines: list[str] = []
    renamed: list[tuple[str, str]] = []
    failed = 0
    for key, frm, to in targets:
        law = law_by_key[key]
        new_md = law["md_slug"]
        dest = ORIGEN_DIR / f"{new_md}.pdf"
        print(f"  ⬇️  {new_md}...", end="", flush=True)
        sha = download_pdf(law["pdf_url"], dest)
        if not sha:
            print(" ❌ (no avanza estado)")
            failed += 1
            time.sleep(BETWEEN_DOWNLOADS_SLEEP_SECS)
            continue
        print(" ✅")
        # B3: misma ley (mismo key) pero cambió su md_slug (renombrado de stem o
        # reforma del nombre). Quitar la entrada vieja del catálogo y archivar sus
        # artefactos viejos (.md/.json/.pdf) para que no queden huérfanos ni un
        # batch_convert full los resucite.
        old_md = state_by_key.get(key, {}).get("md_slug")
        if old_md and old_md != new_md:
            renamed.append((old_md, new_md))
            cat_by_md.pop(old_md, None)
            _archive_law(old_md)
        # Avanzar estado (proyección con ref_abbrev) + upsert del catálogo (B1)
        # con la entrada completa fresca (gen_indice/pdf_to_md la leen).
        state_by_key[key] = {**new_by_key[key], "pdf_sha256": sha, "snapshot_date": today}
        cat_by_md[new_md] = {
            "numero": law["numero"], "nombre": law["nombre"], "dof": law["dof"],
            "ultima_reforma": law["ultima_reforma"], "pdf_url": law["pdf_url"],
            "pdf_filename": law["pdf_filename"],
            "pdf_filename_origen": law["pdf_filename_origen"],
            "md_slug": new_md, "sha256": sha,
        }
        delta_slugs.append(new_md)
        drift_lines.append(f"{new_md}: {frm} -> {to}")
        time.sleep(BETWEEN_DOWNLOADS_SLEEP_SECS)

    # Archivar abrogadas/bajas: mover artefactos + quitar de catálogo y estado.
    archived: list[tuple[str, str]] = []
    for akey, amd, why in to_archive:
        _archive_law(amd)
        cat_by_md.pop(amd, None)
        if akey is not None:
            state_by_key.pop(akey, None)
        archived.append((amd, why))

    # Persistencia ATÓMICA de ambos ledgers (B2): si algo muere a media escritura
    # no quedan estado.json/catalogo.json truncados (no están en git).
    save_state(sorted(state_by_key.values(), key=lambda e: e["key"]))
    _atomic_write_json(CATALOG_PATH, list(cat_by_md.values()))

    out.write_text(("\n".join(delta_slugs) + "\n") if delta_slugs else "", encoding="utf-8")
    drift = out.parent / "expected_drift.txt"
    header = (
        f"# Drift esperado tras --apply ({today})\n"
        f"# {len(delta_slugs)} actualizadas (espera que SOLO su markdown/canonical\n"
        f"# cambie vs baseline) + {len(archived)} archivadas (salen del corpus).\n"
    )
    archive_block = ""
    if archived:
        archive_block = (
            "# ARCHIVADAS (abrogadas/bajas → archive/, fuera del baseline):\n"
            + "".join(f"#   {m} ({why})\n" for m, why in archived)
        )
    rename_block = ""
    if renamed:
        rename_block = (
            "# RENOMBRADOS (md_slug cambió; artefactos viejos archivados):\n"
            + "".join(f"#   {o} -> {n}\n" for o, n in renamed)
        )
    drift.write_text(
        header + archive_block + rename_block + "\n".join(drift_lines)
        + ("\n" if drift_lines else ""),
        encoding="utf-8",
    )

    if archived:
        print(f"🗄️  {len(archived)} ley(es) archivadas a archive/: {archived}")
    if renamed:
        print(
            f"⚠️  {len(renamed)} ley(es) cambiaron de md_slug "
            f"(artefactos viejos archivados): {renamed}"
        )
    print(f"\n📊 {len(delta_slugs)} actualizadas, {len(archived)} archivadas, {failed} fallidas.")
    print(f"📝 delta: {out}  |  manifest: {drift}")
    print(f"➡️  Ahora: python scripts/batch_convert.py --only-slugs {out} --timeout 1200")
    # Si TODAS las descargas fallaron (nada actualizado), señaliza inconcluso (2)
    # aunque algo se haya archivado — el archivado no compensa el fallo de red.
    return 2 if (failed and not delta_slugs) else (10 if (delta_slugs or archived) else 0)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _is_url_allowed(url: str, allowed_hosts: tuple[str, ...]) -> bool:
    """True si el host de `url` está en la allowlist. Lista vacía = sin
    restricción (útil para tests). Acepta solo http/https."""
    if not allowed_hosts:
        return True
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    return parsed.hostname in allowed_hosts


def _sha256_file(path: Path) -> str:
    """SHA-256 hex de un archivo local, leído en bloques (no carga todo a RAM)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_pdf(
    url: str,
    dest: Path,
    verbose: bool = False,
    *,
    max_retries: int = DOWNLOAD_MAX_RETRIES,
    allowed_hosts: tuple[str, ...] = ALLOWED_DOWNLOAD_HOSTS,
) -> str | None:
    """Descarga un PDF con retry + validación. Retorna el SHA-256 hex en
    éxito, `None` en cualquier fallo (URL fuera de allowlist, bytes mágicos
    inválidos, error de red tras agotar reintentos)."""
    if not _is_url_allowed(url, allowed_hosts):
        logger.error("URL fuera de allowlist (rechazada): %s", url)
        print(f"  ❌ URL no permitida: {url}", file=sys.stderr)
        return None

    last_err: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            resp = urllib.request.urlopen(req, timeout=PDF_DOWNLOAD_TIMEOUT_SECS)
            data = resp.read()

            if not data.startswith(PDF_MAGIC_BYTES):
                logger.error("Bytes mágicos inválidos (no es PDF) para %s", url)
                print(f"  ❌ Respuesta no es un PDF válido: {url}", file=sys.stderr)
                return None

            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)

            sha = hashlib.sha256(data).hexdigest()
            if verbose:
                size_mb = len(data) / (1024 * 1024)
                print(f"  ✅ {dest.name} ({size_mb:.1f} MB, sha256={sha[:12]}…)")
            return sha

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            if attempt < max_retries:
                backoff = DOWNLOAD_BACKOFF_BASE_SECS * (2 ** attempt)
                logger.warning(
                    "Descarga falló (intento %d/%d) %s: %s. Reintento en %.1fs",
                    attempt + 1, max_retries + 1, url, e, backoff,
                )
                time.sleep(backoff)
                continue
            break

    logger.error(
        "Falló descarga tras %d intentos: %s — último error: %s",
        max_retries + 1, url, last_err,
    )
    print(f"  ❌ Error descargando {url}: {last_err}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga PDFs de leyes federales vigentes desde diputados.gob.mx",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Solo muestra el catálogo sin descargar.",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limita la descarga a N leyes (0 = todas).",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="No re-descarga PDFs que ya existen en origen-docs/.",
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=ORIGEN_DIR,
        help=f"Directorio de salida para los PDFs (default: {ORIGEN_DIR}).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Muestra progreso detallado.",
    )
    parser.add_argument(
        "--init-snapshot", action="store_true",
        help="Graba estado.json desde el índice vivo (sin descargar). "
             "Bootstrap del detector de deltas upstream.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Diff read-only del índice vivo vs estado.json. "
             "Exit 0=limpio, 10=hay deltas, 2=inconcluso. No escribe nada.",
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help="Con --check: escribe el reporte markdown de deltas a este archivo.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Descarga SOLO las leyes cambiadas+altas (diff vs estado.json), "
             "avanza estado y escribe delta.txt + expected_drift.txt. No reconvierte.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Con --apply: muestra qué se descargaría sin descargar ni tocar estado.",
    )
    parser.add_argument(
        "--delta-out", type=Path, default=None,
        help="Con --apply: ruta del archivo delta.txt (default: delta.txt en la raíz).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Subcomandos de detección. --check es read-only; --init-snapshot solo graba
    # estado.json; --apply descarga + actualiza estado y catálogo.
    if sum([args.init_snapshot, args.check, args.apply]) > 1:
        print(
            "❌ --init-snapshot, --check y --apply son mutuamente excluyentes.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if args.init_snapshot:
        init_snapshot()
        return
    if args.check:
        raise SystemExit(run_check(args.report))
    if args.apply:
        raise SystemExit(run_apply(dry_run=args.dry_run, delta_path=args.delta_out))

    print("📡 Obteniendo catálogo de leyes desde diputados.gob.mx...", flush=True)
    laws = fetch_index()
    print(f"📋 {len(laws)} leyes encontradas.\n", flush=True)

    # Guardar catálogo
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(laws, f, ensure_ascii=False, indent=2)
    print(f"💾 Catálogo guardado en {CATALOG_PATH}\n")

    if args.list:
        for law in laws:
            print(f"  {law['numero']:>3}  {law['nombre'][:80]}")
            print(f"       PDF: {law['pdf_filename']}  |  Reforma: {law['ultima_reforma']}")
        return

    # Descargar
    subset = laws[:args.limit] if args.limit > 0 else laws
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    catalog_dirty = False
    for i, law in enumerate(subset, 1):
        dest = output_dir / law["pdf_filename"]
        label = f"[{i}/{len(subset)}] {law['pdf_filename']}"

        if args.skip_existing and dest.exists():
            # Aun saltando la descarga, registramos el sha256 del PDF local para
            # preservar la procedencia (fix: antes el catálogo quedaba sin sha256
            # al re-correr con --skip-existing).
            law["sha256"] = _sha256_file(dest)
            catalog_dirty = True
            if args.verbose:
                print(f"  ⏭️  {label} (ya existe)")
            skipped += 1
            continue

        print(f"  ⬇️  {label}...", end="", flush=True)
        sha = download_pdf(law["pdf_url"], dest, verbose=False)
        if sha:
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f" ✅ ({size_mb:.1f} MB, sha256={sha[:12]}…)")
            law["sha256"] = sha
            catalog_dirty = True
            downloaded += 1
        else:
            failed += 1

        # Ser amable con el servidor
        time.sleep(BETWEEN_DOWNLOADS_SLEEP_SECS)

    # Si se descargó al menos un PDF, re-escribir el catálogo con los SHAs
    # anotados. Detecta reformas upstream comparando contra corridas previas.
    if catalog_dirty:
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(laws, f, ensure_ascii=False, indent=2)

    print(f"\n📊 Resultado: {downloaded} descargados, {skipped} omitidos, {failed} errores")
    print(f"📁 PDFs en: {output_dir}")


if __name__ == "__main__":
    main()
