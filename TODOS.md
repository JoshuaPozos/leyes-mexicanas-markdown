# TODOS — Pipeline mx-md

---

## Sprint 2 — Confianza y velocidad ✅ (cerrado 2026-05-10)

### 2.1 — Constantes y regex pre-compilados ✅

- [x] `scripts/constants.py` con 22 constantes documentadas (umbrales OCR, timeouts, slug limits, magic bytes, allowlist).
- [x] Regex de loops calientes movidos a nivel módulo en `pdf_to_md.py` (4) y `download_leyes.py` (6).
- [x] Literales mágicos reemplazados por constantes nombradas en ambos scripts.

### 2.2 — Paralelización de `batch_convert.py` ✅

- [x] `ProcessPoolExecutor` con `--workers` configurable (default `os.cpu_count()`).
- [x] `--timeout` por PDF (default 300 s) vía `subprocess.TimeoutExpired`.
- [x] `_run_tasks` helper: paralelo si `workers>1`, inline secuencial si `workers<=1` (útil para tests con monkeypatch).
- [x] Speedup medido: **2.37x** con 8 workers vs serial (5 PDFs).

### 2.3 — Robustez en `download_leyes.py` ✅

- [x] Retry con backoff exponencial (default 3 reintentos: 1 s, 2 s, 4 s).
- [x] Validación de bytes mágicos `%PDF-` antes de escribir al disco.
- [x] Allowlist de hosts (`diputados.gob.mx`), esquemas `http`/`https` exclusivos.
- [x] SHA-256 por PDF anotado en `catalogo.json` (detección de reformas upstream).
- [x] `download_pdf` retorna `str | None` (hash hex o `None`).

### 2.4 — Schema endurecido ✅

- [x] Patrones regex para `id`, `abbreviation`, `catalog_number`, `node.id`, ordinales de fracción/inciso/apartado/numeral, `dof_date`.
- [x] `preamble: minItems: 1`, `source_page: minimum: 1`, `minLength: 1` en strings críticos.
- [x] `"abrogado"` añadido al enum de `reform_note.action`.
- [x] `examples` en campos clave para documentación inline.
- [x] `tests/test_schema.py` (28 tests): validator, patterns, sample de 20 canonicals reales.
- [x] 315/315 canonicals validan contra el schema endurecido.

### Resultado Sprint 2

- Suite: 250 → **307 tests** (+57).
- ruff + mypy: clean.
- `check_regression.sh`: 315/315 byte-a-byte idénticos.
- Branch larga `perf/regex-y-paralelizacion` (4 commits sobre `infra/dx-baseline`).

---

## Sprint 1 — Fundamentos / Red de seguridad ✅ (cerrado 2026-04-26)

### 1.1 — `pyproject.toml` ✅

- [x] Reemplazar `requirements.txt` por `pyproject.toml`.
- [x] `[project.scripts]`: `mx-md-convert`, `mx-md-batch`, `mx-md-download`, `mx-md-indice`.
- [x] Dependencias pineadas con rangos de mayor (`pdfplumber>=0.11,<1.0`, etc.).
- [x] `requirements.lock` con versiones exactas.
- [x] Extras `[dev]`: pytest, pytest-cov, ruff, mypy.

### 1.2 — Logging estructurado ✅

- [x] `scripts/_log.py` con `getLogger(__name__)`.
- [x] Variable `MX_MD_LOG_LEVEL` controla el nivel (default WARNING).
- [x] `print()` de estado interno migrados a `logger.info/debug`.

### 1.3 — Excepciones específicas ✅

- [x] `except Exception: pass` reemplazado por capturas específicas con `logger.exception()`.

### 1.4 — CI mínimo ✅

- [x] `.github/workflows/ci.yml` corre `ruff check` y `mypy` sobre Python 3.10/3.11/3.12.

### 1.5 — Tests de helpers puros ✅

- [x] 111 tests sobre `_slugify_ordinal`, `is_article_heading`, `_is_roman_numeral`, `_detect_running_header`, `build_page_marker_re`.

### 1.6 — Type hints completos ✅

- [x] Helpers privados anotados.
- [x] `disallow_untyped_defs = true` activado en mypy.

### 1.7 — Cobertura `gen_indice.py` ✅ (0 → 98 %)

- [x] 17 tests.

### 1.8 — Cobertura `batch_convert.py` ✅ (0 → 99 %)

- [x] 26 tests con repo falso vía `monkeypatch`.

### 1.9 — Cobertura I/O `download_leyes.py` ✅ (32 → 99 %)

- [x] Tests de `LeyesTableParser`, `fetch_index`, `download_pdf`, `parse_args`, `main`.

### 1.10 — Cobertura `pdf_to_md.py` helpers ✅ (13 → 29 %)

- [x] Tests adicionales sobre helpers puros del AST builder y renderer.

### Resultado Sprint 1

- 250 tests, suite verde en ~2-3 s.
- Cobertura global: 16 % → **48 %**.
- 315/315 leyes idénticas al baseline.
- Branch larga `infra/dx-baseline` (10 commits, no mergeada a `main`).

---

## Modelo canónico JSON/AST ✅

**Meta:** Pipeline PDF → AST (JSON) → Markdown, con el JSON como fuente de verdad.

### Schema del AST ✅

- [x] Diseñar JSON Schema para el AST (`schema/law_ast.schema.json`)
- [x] Crear ejemplo concreto con fragmento de la CPEUM (`schema/example_cpeum_fragment.json`)

**Nodos estructurales:** `libro`, `titulo`, `capitulo`, `seccion`, `articulo`, `transitorios`, `transitorio_articulo`
**Nodos de contenido:** `paragraph`, `fraccion`, `inciso`, `numeral`, `apartado`, `table`, `reform_note`
**IDs estables:** paths jerárquicos tipo `titulo-1.capitulo-2.art-15`

### `build_ast()` + `render_markdown()` ✅

- [x] `build_ast(lines) → dict` — construye el árbol canónico desde líneas extraídas del PDF
- [x] `render_markdown(ast) → list[str]` — renderiza el AST a Markdown (reemplaza `build_markdown`)
- [x] Pipeline: `extract_lines() → build_ast() → JSON + render_markdown() → MD`
- [x] Enriquecer el AST con metadatos del catálogo (`source`, `abbreviation`, `catalog_number`, etc.)
- [x] Generar IDs estables para cada nodo: `{parent_id}.{type}-{ordinal}`
- [x] Parsear notas de reforma inline como nodos `reform_note` separados del texto
- [x] Detectar y estructurar fracciones (`I.`, `II.`) e incisos (`a)`, `b)`) como nodos propios
- [x] Estructurar tablas como nodos `table` con `headers[]`, `rows[][]`, `source_method`

### Doble output: JSON + Markdown ✅

- [x] `pdf_to_md.py` genera ambos: `{slug}.json` en `canonical/` + `{slug}.md` en `markdown/`
- [x] Crear directorio `canonical/` con 315 JSON, uno por ley
- [x] `batch_convert.py` ejecuta ambos outputs
- [x] Flag `--format json|md|both` (default: `both`)
- [x] Flag `--validate` valida cada JSON contra el schema

### Actualizar gen_indice.py ✅

- [x] Incluir conteo de artículos por ley (extraído del JSON)
- [x] Agregar columna de link al JSON canónico en el índice
- [x] Regenerar INDICE.md
- [x] Corregir bug de escritura duplicada

### Documentación ✅

- [x] Actualizar README.md con la nueva arquitectura (`canonical/`, schema, doble output, AST)
- [x] Documentar el schema en README
- [x] Actualizar sección "Cómo funciona" con el pipeline: PDF → AST → JSON + MD
- [x] Actualizar CHANGELOG.md
- [x] Actualizar TODOS.md

### Dataset stats

| Métrica | Cantidad |
|---------|----------|
| Leyes | 315 |
| Artículos | 37,939 |
| Fracciones | 58,310 |
| Incisos | 12,370 |
| Notas de reforma | 35,176 |
| Tablas OCR | 42 |
| JSON (canonical/) | 93 MB |
| Markdown (markdown/) | 52 MB |

---

## Decisiones de diseño

### ¿Por qué JSON y no base de datos?
- Este es el repo público, open-source. Los JSON son accesibles sin infra.
- Se versionan con git: cualquiera puede clonar y tener las 315 leyes estructuradas.

### ¿Por qué el JSON es la fuente de verdad?
- `build_ast()` construye el árbol canónico directamente desde las líneas del PDF.
- `render_markdown(ast)` recorre el AST y produce Markdown. Si cambia el formato, solo cambia el render.
- El Markdown era la fuente antes; ahora es una vista del JSON.

### IDs estables
- Formato: `titulo-primero.capitulo-i.art-1`
- Paths jerárquicos, legibles y predecibles.
- Permiten referencia directa: "dame el artículo 96 de la LISR" → `titulo-iv.capitulo-i.art-96`

### Notas de reforma como nodos separados
- Hoy están mezcladas inline con el texto del párrafo.
- En el AST se separan como `reform_note` con `action` y `dof_date` parseados.
- El Markdown sigue renderizándolas inline (compatibilidad), pero el JSON las tiene limpias.

---

## Historial de fixes (referencia)

Los siguientes issues ya fueron resueltos en la etapa de pipeline:

| # | Issue | Resultado |
|---|-------|-----------|
| 1 | Falso `##` en "título de..." | 17 → 0 |
| 2 | Running header embebido en texto | 80/84 corregidos |
| 3 | "Transitorios" sin heading | 74 archivos |
| 4 | Ordinales de decreto sin heading | 58 archivos |
| 5 | Ordinales sin negritas | 77 archivos |
| 6 | Nombres descriptivos de sección | Todos |
| 7 | Fracciones romanas pegadas | Todos |
| 8 | Incisos inline | Todos |
| 9 | Tablas-imagen sin OCR | 8 leyes |
| 10 | 1,762 falsos positivos en headings | 1,762 → 0 |
| 11 | Headers de tablas OCR genéricos | Reconstruidos |
| 12 | Tablas OCR desplazadas | Posición correcta |
