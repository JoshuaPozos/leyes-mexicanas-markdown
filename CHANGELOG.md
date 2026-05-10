# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.

## [Sprint 2 — Confianza y velocidad] — 2026-05-10

Cuatro mejoras de robustez y performance sobre el pipeline existente. Suite
sube de 250 a 307 tests. Baseline de regresión (315/315 leyes idénticas)
preservado en cada item.

### 2.1 — Constantes operativas centralizadas y regex pre-compilados

- Nuevo `scripts/constants.py` con 22 constantes documentadas (umbrales OCR,
  timeouts, slug limits, etc.). Cada una con docstring explicando *por qué*
  ese valor (cambiar requiere revalidar baseline).
- Regex pre-compilados a nivel módulo en loops calientes:
  - `pdf_to_md.py`: `_OCR_NUM_RE`, `_OCR_UNIT_RE`, `_INCISO_INLINE_SPLIT_RE`,
    `_RUNNING_HEADER_LETTERS_RE`.
  - `download_leyes.py`: `_WHITESPACE_RE`, `_LAW_NAME_TRAILING_RE`,
    `_SLUG_NON_ALNUM_RE`, `_PDF_STEM_NUMERIC_SUFFIX_RE`,
    `_ACRONYM_CLAUSE_BREAK_RE`, `_ACRONYM_WORD_BREAK_RE`.
- Reemplazo de literales mágicos por constantes nombradas en ambos scripts.
- Valor principal: **mantenibilidad** (constantes con razón documentada).
  Beneficio de performance en este contexto es marginal (la conversión está
  dominada por pdfplumber + OCR, no por compilación de regex).

### 2.2 — Paralelización de `batch_convert.py`

- `ProcessPoolExecutor` con `--workers` configurable (default `os.cpu_count()`).
  `--workers 1` cae a ejecución secuencial inline (útil para depurar y para
  tests con `monkeypatch` de `subprocess.run`).
- `--timeout` por PDF (default 300 s) vía `subprocess.TimeoutExpired`:
  evita que un PDF que se cuelga bloquee al pool indefinidamente.
- `_convert_task` a nivel módulo + `functools.partial` para que sea picklable
  bajo el start method `spawn` (default en macOS / Windows).
- `_run_tasks` helper: paralelo con `as_completed` si `workers>1`,
  secuencial inline si `workers<=1`.

**Speedup medido** (5 PDFs representativos: CCF, CCom, CFF, CFPC, CJM):

| Workers | Tiempo real | CPU avg | Speedup |
|---|---|---|---|
| 1 (serial) | 6:33 min | 94% | 1.0x |
| 4 | 4:12 min | 252% | 1.56x |
| 8 | 2:46 min | 331% | **2.37x** |

Sub-lineal porque el bottleneck son OCR + I/O, no CPU puro.

### 2.3 — Robustez en `download_leyes.py`

- **Retry con backoff exponencial** (default 3 reintentos: 1 s, 2 s, 4 s).
  Cubre fallos transitorios sin amplificar carga si el sitio cae.
- **Validación de bytes mágicos** `%PDF-` antes de escribir al disco:
  rechaza páginas de error HTML, redirects o archivos corruptos.
- **Allowlist de hosts**: solo `diputados.gob.mx` / `www.diputados.gob.mx`,
  esquemas `http` / `https` exclusivamente.
- **SHA-256 por PDF** anotado en `catalogo.json` (detección de reformas
  upstream comparando contra corridas previas).
- `download_pdf` cambia firma a `-> str | None` (hash hex en éxito, `None`
  en cualquier fallo).

### 2.4 — Schema endurecido

Patrones agregados (validados empíricamente contra 315/315 canonicals):

- `id` (root): `^[A-Za-z][A-Za-z0-9_]+$`
- `abbreviation`: `^[A-Za-z][A-Za-z0-9]*$`
- `catalog_number`: `^\d+$`
- `node.id`: `^[a-z0-9_-]+(\.[a-z0-9_-]+)*$`
- `fraccion.ordinal`: `^[IVXLCDM]+(?:[- ][A-Za-z]+)?$`
- `inciso.ordinal`: `^[a-z]$`
- `apartado.ordinal`: `^[A-Z]$`
- `numeral.ordinal`: `^\d+$`
- `reform_note.dof_date`: `^\d{2}[-/]\d{2}[-/]\d{4}$`

Constraints adicionales:

- `preamble`: `minItems: 1` (cuando presente).
- `source_page`: `minimum: 1` (1-indexed).
- `name`, `paragraph.text`, `reform_note.text`: `minLength: 1`.
- `reform_note.action`: enum cierra con `"abrogado"` añadido (ya estaba
  en código).

Ejemplos (`examples`) añadidos en campos clave para servir de documentación
inline.

### Tests

Suite total: **307/307** (250 antes del sprint, +57 nuevos):

- `test_batch_convert.py`: +15 (timeout, workers, `_resolve_workers`,
  `_run_tasks`, path paralelo con `ProcessPoolExecutor` fakeado).
- `test_download_io.py`: +14 (allowlist, magic bytes, retry exponencial,
  sha256, anotación de catálogo).
- `test_schema.py` (nuevo): +28 (validator carga el schema, ejemplo CPEUM,
  patterns por tipo, dof_date dual-separator, action enum cerrado, sample
  de 20 canonicals reales).

---

## [Sprint 1 — Fundamentos / Red de seguridad] — 2026-04-26

Diez items que instalan logging estructurado, packaging moderno, CI, y
una suite de tests sobre helpers puros (cobertura global 16 % → 48 %).
Ningún cambio altera la salida JSON/Markdown: `check_regression.sh`
reportó 315/315 idénticos al baseline en cada commit.

### 1.1 — Migrar a `pyproject.toml`

- `requirements.txt` reemplazado por `pyproject.toml`.
- `[project.scripts]`: `mx-md-convert`, `mx-md-batch`, `mx-md-download`,
  `mx-md-indice` como entry points instalables.
- Dependencias pineadas con rangos de mayor (`pdfplumber>=0.11,<1.0`,
  `pytesseract>=0.3.10,<1.0`, `Pillow>=10,<12`, `jsonschema>=4,<5`).
- `requirements.lock` generado con versiones exactas para reproducibilidad.
- Extras `[dev]`: `pytest`, `pytest-cov`, `ruff`, `mypy`.

### 1.2 — Logging estructurado

- Nuevo `scripts/_log.py` con `getLogger(__name__)`.
- Variable de entorno `MX_MD_LOG_LEVEL` controla el nivel (default `WARNING`).
- `print()` que reportaban estado interno migrados a `logger.info/debug`.
- Los `print` con emojis ✅/❌ se mantienen como UX (output al usuario).

### 1.3 — Excepciones específicas

- `except Exception: pass` reemplazado por capturas específicas
  (`ValueError`, `OSError`, `pytesseract.TesseractNotFoundError`, etc.)
  con `logger.exception()` cuando aplica.

### 1.4 — CI mínimo (lint + typecheck)

- `.github/workflows/ci.yml` corre `ruff check scripts/` y `mypy scripts/`
  sobre Python 3.10, 3.11 y 3.12 en cada push.

### 1.5 — Tests de helpers puros

- `tests/` con pytest: 111 tests sobre helpers sin I/O (`_slugify_ordinal`,
  `is_article_heading`, `_is_roman_numeral`, `_detect_running_header`,
  `build_page_marker_re`).
- Cobertura global pasa de 0 % a 16 %.

### 1.6 — Type hints completos en helpers internos

- Helpers privados (`_helper`) anotados.
- `disallow_untyped_defs = true` activado en `mypy`.

### 1.7 — Cobertura `gen_indice.py` (0 → 98 %)

- 17 tests sobre el generador de índice.

### 1.8 — Cobertura `batch_convert.py` (0 → 99 %)

- 26 tests con repo falso (`monkeypatch` de paths) cubriendo `convert_pdf`,
  `parse_args`, `main`, branches de error.

### 1.9 — Cobertura I/O de `download_leyes.py` (32 → 99 %)

- Tests de `LeyesTableParser`, `fetch_index`, `download_pdf`, `parse_args`,
  `main` con `monkeypatch` de `urllib.request`.

### 1.10 — Cobertura `pdf_to_md.py` helpers (13 → 29 %)

- Tests adicionales sobre helpers puros del AST builder y renderer.
- Cobertura global del proyecto: **48 %**.

### Resultado global Sprint 1

- 250 tests, suite verde en ~2-3 s.
- Cobertura: 16 % → 48 %.
- CI funcional sobre 3 versiones de Python.
- `mypy --disallow-untyped-defs` clean.
- 315/315 leyes idénticas al baseline.

---

## [Modelo canónico JSON/AST] — 2026-04-09

El JSON es ahora la fuente de verdad. El Markdown se renderiza desde el AST.

### Pipeline nuevo
- `extract_lines()` → `build_ast()` → **AST canónico (JSON)** → `render_markdown()` → **Markdown**
- El antiguo `build_markdown()` se conserva como legacy pero ya no es invocado por el pipeline principal

### Nuevas funciones en `pdf_to_md.py`
- `build_ast(lines, metadata) → dict` — construye árbol canónico con IDs estables jerárquicos
- `render_markdown(ast) → list[str]` — renderiza AST a Markdown limpio
- Notas de reforma separadas correctamente del texto siguiente (antes se unían en una misma línea)
- `--format json|md|both` — controla qué formatos generar (default: `both`)
- `--validate` — valida el JSON contra `schema/law_ast.schema.json`

### JSON canónico (`canonical/`)
- 315 leyes en JSON estructurado (93 MB total)
- JSON Schema: `schema/law_ast.schema.json`
- Nodos estructurales: `libro`, `titulo`, `capitulo`, `seccion`, `articulo`, `transitorios`, `transitorio_articulo`
- Nodos de contenido: `paragraph`, `fraccion`, `inciso`, `numeral`, `apartado`, `table`, `reform_note`
- IDs estables: `titulo-i.capitulo-ii.articulo-15`
- Metadatos: fuente PDF, fecha DOF, catálogo de diputados
- 315/315 válidos contra schema

### Dataset
- 37,939 artículos · 58,310 fracciones · 12,370 incisos · 35,176 notas de reforma · 42 tablas OCR

### Otros cambios
- `batch_convert.py`: flags `--format` y `--validate` propagados
- `gen_indice.py`: reescrito — columna de artículos por ley, link a JSON, corregido bug de escritura duplicada
- `INDICE.md`: regenerado con 6 columnas (No., Ley, Reforma, Arts., Markdown, JSON)
- `README.md`: reescrito para reflejar la nueva arquitectura
- `TODOS.md`: actualizado con estado completado

### Fix: Schema preamble
- `preamble.items` cambiado de `text_block` a `content_element` — el preámbulo puede contener fracciones, incisos y notas de reforma, no solo párrafos

## [Fix 12 — Tablas OCR en posición correcta] — 2026-03-21

- `extract_lines()`: para páginas con tablas-imagen, divide la extracción en regiones verticales (texto arriba + OCR tabla + texto abajo) en vez de extraer todo el texto y agregar la tabla al final
- Las tablas ahora aparecen en su posición natural dentro del artículo, no desplazadas varios párrafos abajo
- Párrafos que antes se cortaban por la tabla ("aplicar la tasa [tabla] máxima para...") ahora fluyen correctamente
- 8 MDs con tablas-imagen regenerados

## [Fix 11 — Headers de tablas OCR reconstruidos] — 2026-03-21

- `_build_table_from_spatial()` reescrito: separación título/headers/datos usando gap vertical
- `assign_to_columns()`: cambiado de closest-center a column boundaries (punto medio entre centros)
- `_assign_header_row()`: filas de header con texto en 1-2 columnas adyacentes se fusionan correctamente
- Detección de filas de unidades (`$ $ $ %`) e incorporación al nombre de columna
- Filtro de ruido OCR en filas de header (requiere al menos una palabra de ≥4 letras)
- **Resultado:** Headers genéricos `| $ | $ | $ | % |` → `| Limite inferior ($) | Limite superior ($) | Cuota fija ($) | Por ciento para... (%) |`
- Todos los 315 `.md` regenerados

## [Fix 10 — Falsos positivos en headings de artículos] — 2026-03-21

- `is_article_heading()`: eliminado `re.IGNORECASE` — solo reconoce "Artículo" con A mayúscula
- `ARTICLE_ORDINAL_RE`: cambiado a match explícito "ARTÍCULO|Artículo" sin IGNORECASE
- `split_article_heading()`: eliminado `re.IGNORECASE` para consistencia
- Guardia de contexto en `build_markdown()`: si el buffer termina con preposición ("el", "del", "al", etc.), el "Artículo N" se une como texto, no como heading
- **Resultado:** 1 762 falsos positivos → 0 en los 315 archivos
- Todos los 315 `.md` regenerados

## [Lote 14 — Leyes 295-315] — 2026-03-21

### Leyes publicadas (21) — Catálogo completo 315/315 🎉
| No. | Clave | Ley |
|-----|-------|-----|
| 295 | LRFVACGR | Ley Reglamentaria de la Fracción V del Artículo 76 de la Constitución |
| 296 | LRArt76 | Ley Reglamentaria de la fracción VI del artículo 76 de la Constitución |
| 297 | LRFXIIIB | Ley Reglamentaria de la Fracción XIII Bis del Apartado B, del Artículo 123 |
| 298 | LRFXAC | Ley Reglamentaria de la Fracción XVIII del Artículo 73 Constitucional |
| 299 | LRFIyII | Ley Reglamentaria de las Fracciones I y II del Artículo 105 |
| 300 | LRACMN | Ley Reglamentaria del Artículo 27 Constitucional en Materia Nuclear |
| 301 | LRArt3 | Ley Reglamentaria del Artículo 3o. de la Constitución |
| 302 | LRAC | Ley Reglamentaria del Artículo 5o. Constitucional |
| 303 | LRArt6 | Ley Reglamentaria del artículo 6o. de la Constitución |
| 304 | LRSF | Ley Reglamentaria del Servicio Ferroviario |
| 305 | LCA | Ley sobre Cámaras Agrícolas |
| 306 | LCS | Ley Sobre el Contrato de Seguro |
| 307 | LEBHN | Ley sobre el Escudo, la Bandera y el Himno Nacionales |
| 308 | LATIME | Ley Sobre la Aprobación de Tratados Internacionales en Materia Económica |
| 309 | LSCT | Ley sobre la Celebración de Tratados |
| 310 | LRPCAP | Ley sobre Refugiados, Protección Complementaria y Asilo Político |
| 311 | OGA | Ordenanza General de la Armada |
| 312 | PEF | Presupuesto de Egresos de la Federación para el Ejercicio Fiscal 2026 |
| 313 | Reg_Diputados | Reglamento de la Cámara de Diputados |
| 314 | Reg_Senado | Reglamento del Senado de la República |
| 315 | RGICGEUM | Reglamento para el Gobierno Interior del Congreso General |

---

## [Lote 13 — Leyes 250-294] — 2026-03-21

### Leyes publicadas (45)
Leyes orgánicas (LOAM, LOPDC, LOPGJDF, LOUAAAN, LOUAM, LOUNAM, LOTA, LONF, LOSHF, LOBB, LOBNCE, LOBNOSP, LOBNE, LOCFCRL, LOCGEUM, LOEFAM, LOINAH, LOIPN, LOPJF, LOSCM, LOTFJA), leyes para conservar/determinar/impulsar (LCNP, LDVUMA, LDCMPME, LD, LUPDECR, LIISPCEN, LC, LCACSEFAM, LPPDDHP, LTPCPIMCP, LTOSF), leyes para regular (LRASCAP, LRAF, LRITF, LRSIC), leyes que aprueban/crean/declaran/establecen (LAAMCCBD, LCFGFA, LCINBAL, LAEM, LCUAC, LCUEFA, LDRMNYU, LCCAIF, LEBEM).

---

## [Lotes 10-12 — Leyes 115-249] — 2026-03-21

### Leyes publicadas (135)
Incluye: leyes del instituto (LISSFAM, LISSSTE, LIFNVT, LIFNCT, LIMJ, LINPI), leyes del mercado/sector (LMV, LSE, LSH, LSS, LSM, LSPM), leyes del servicio (LSAT, LSEM, LSPCAPF), leyes del sistema (LSNIEG, LSNIIMSP, LSPREM), ley en materia de telecomunicaciones (LMTR), leyes federales contra/de/del/para (LFCDO…LFMZAAH — 48 leyes), leyes generales (LGAMVLV…LGPSDMS — 58 leyes), leyes nacionales (LMEUM…LNUF — 8 leyes), ley orgánica APF (LOAPF).

---

## [Fix Issues 6-9 — OCR y mejoras] — 2026-03-19

### Correcciones aplicadas
| # | Issue | Resultado |
|---|-------|-----------|
| 6 | Nombres descriptivos de sección sin formato | Ahora se añaden como `— NOMBRE` al heading |
| 7 | Fracciones romanas (I., II., XVI.) pegadas sin separar | Ahora en párrafos separados |
| 8 | Sub-incisos a), b), c) pegados inline | Ahora en párrafos separados |
| 9 | Tablas-imagen sin contenido (placeholder) | OCR con Tesseract: extracción real de tablas |

---

## [Lote 9 — Leyes 084-113] — 2026-03-19

### Leyes publicadas (30)
| No. | Clave | Ley |
|-----|-------|-----|
| 084 | LNCM | Ley de Navegación y Comercio Marítimos |
| 085 | LOPSRM | Ley de Obras Públicas y Servicios Relacionados con las Mismas |
| 086 | LOG | Ley de Organizaciones Ganaderas |
| 087 | LPlan | Ley de Planeación |
| 088 | LPTE | Ley de Planeación y Transición Energética |
| 089 | LPERC | Ley de Premios, Estímulos y Recompensas Civiles |
| 090 | LPO | Ley de Productos Orgánicos |
| 091 | LPAB | Ley de Protección al Ahorro Bancario |
| 092 | LPCINECD | Ley de Protección al Comercio y la Inversión de Normas Extranjeras |
| 093 | LPEAM | Ley de Protección del Espacio Aéreo Mexicano |
| 094 | LPDUSF | Ley de Protección y Defensa al Usuario de Servicios Financieros |
| 095 | LP | Ley de Puertos |
| 096 | LRAM | Ley de Recompensas de la Armada de México |
| 097 | LRCDN | Ley de Responsabilidad Civil por Daños Nucleares |
| 098 | LSInt | Ley de Seguridad Interior |
| 099 | LSN | Ley de Seguridad Nacional |
| 100 | LSP | Ley de Sistemas de Pagos |
| 101 | LSRLIP | Ley de Sociedades de Responsabilidad Limitada de Interés Público |
| 102 | LSSS | Ley de Sociedades de Solidaridad Social |
| 103 | LTF | Ley de Tesorería de la Federación |
| 104 | LTFCCG | Ley de Transparencia y de Fomento a la Competencia en el Crédito Garantizado |
| 105 | LUC | Ley de Uniones de Crédito |
| 106 | LVZMM | Ley de Vertimientos en las Zonas Marinas Mexicanas |
| 107 | LVGC | Ley de Vías Generales de Comunicación |
| 108 | LViv | Ley de Vivienda |
| 109 | LBM | Ley del Banco de México |
| 110 | LDOFGG | Ley del Diario Oficial de la Federación y Gacetas Gubernamentales |
| 111 | LFMPED | Ley del Fondo Mexicano del Petróleo para la Estabilización y el Desarrollo |
| 112 | LIVA | Ley del Impuesto al Valor Agregado |
| 113 | LIEPS | Ley del Impuesto Especial sobre Producción y Servicios |

A partir del lote 9 los lotes son de 30 leyes.

## [Fix TODOS — Mejoras pdf_to_md.py] — 2026-03-19

### Correcciones aplicadas al script de conversión (5 fixes)
| # | Issue | Resultado |
|---|-------|-----------|
| 1 | Falso positivo `##` en "título de...", "sección de...", "capítulo de..." | 17 → 0 instancias |
| 2 | Running header del PDF embebido en texto (80/84 archivos) | Eliminado en todos |
| 3 | "Transitorios" sin formato heading | Ahora `## Transitorios` (74 archivos) |
| 4 | "ARTÍCULO TERCERO A ARTÍCULO DÉCIMO" sin heading | Ahora `### ARTÍCULO...` (58 archivos) |
| 5 | Ordinales ("Primero.", "Segundo.") sin negritas | Ahora `**Primero.-**` (77 archivos) |

**Se reconvirtieron los 84 archivos existentes con el script mejorado.**

## [Lote 8 — Leyes 074-083] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 074 | LGN | Ley de la Guardia Nacional |
| 075 | LPF | Ley de la Policía Federal |
| 076 | LDPAM | Ley de los Derechos de las Personas Adultas Mayores |
| 077 | LHHEUM | Ley de los Husos Horarios en los Estados Unidos Mexicanos |
| 078 | LIGIE | Ley de los Impuestos Generales de Importación y de Exportación |
| 079 | LINS | Ley de los Institutos Nacionales de Salud |
| 080 | LSAR | Ley de los Sistemas de Ahorro para el Retiro |
| 081 | LMigra | Ley de Migración |
| 082 | LMin | Ley de Minería |
| 083 | LN | Ley de Nacionalidad |

> A partir del lote 9 los lotes son de 15 leyes.

---

## [Lote 7 — Leyes 064-073] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 064 | LIE | Ley de Inversión Extranjera |
| 065 | LANSI | Ley de la Agencia Nacional de Seguridad Industrial y de Protección al Medio Ambiente del Sector Hidrocarburos |
| 066 | LCMM | Ley de la Casa de Moneda de México |
| 067 | LCNBV | Ley de la Comisión Nacional Bancaria y de Valores |
| 068 | LCNE | Ley de la Comisión Nacional de Energía |
| 069 | LCNDH | Ley de la Comisión Nacional de los Derechos Humanos |
| 070 | LESS | Ley de la Economía Social y Solidaria |
| 071 | LEPECFE | Ley de la Empresa Pública del Estado Comisión Federal de Electricidad |
| 072 | LEPEPM | Ley de la Empresa Pública del Estado Petróleos Mexicanos |
| 073 | LFGR | Ley de la Fiscalía General de la República |

---

## [Lote 6 — Leyes 054-063] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 054 | LFIV | Ley de Fomento a la Industria Vitivinícola |
| 055 | LFLL | Ley de Fomento para la Lectura y el Libro |
| 056 | LFAAR | Ley de Fondos de Aseguramiento Agropecuario y Rural |
| 057 | LFI | Ley de Fondos de Inversión |
| 058 | LGeo | Ley de Geotermia |
| 059 | LICal | Ley de Infraestructura de la Calidad |
| 060 | LIF | Ley de Ingresos de la Federación para el Ejercicio Fiscal 2026 |
| 061 | LIH | Ley de Ingresos sobre Hidrocarburos |
| 062 | LIC | Ley de Instituciones de Crédito |
| 063 | LISF | Ley de Instituciones de Seguros y de Fianzas |

---

## [Lote 5 — Leyes 044-053] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 044 | LDFEFM | Ley de Disciplina Financiera de las Entidades Federativas y los Municipios |
| 045 | LDPAM | Ley de Disciplina para el Personal de la Armada de México |
| 046 | LEMEFAGN | Ley de Educación Militar del Ejército, Fuerza Aérea y Guardia Nacional |
| 047 | LEN | Ley de Educación Naval |
| 048 | LEC | Ley de Energía para el Campo |
| 049 | LE | Ley de Expropiación |
| 050 | LEI | Ley de Extradición Internacional |
| 051 | LFEA | Ley de Firma Electrónica Avanzada |
| 052 | LFRCF | Ley de Fiscalización y Rendición de Cuentas de la Federación |
| 053 | LFCC | Ley de Fomento a la Confianza Ciudadana |

---

## [Lote 4 — Leyes 034-043] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 034 | LCJPJF | Ley de Carrera Judicial del Poder Judicial de la Federación |
| 035 | LCE | Ley de Comercio Exterior |
| 036 | LCM | Ley de Concursos Mercantiles |
| 037 | LCMOPFIH | Ley de Contribución de Mejoras por Obras Públicas Federales de Infraestructura Hidráulica |
| 038 | LCID | Ley de Cooperación Internacional para el Desarrollo |
| 039 | LCF | Ley de Coordinación Fiscal |
| 040 | LDRS | Ley de Desarrollo Rural Sustentable |
| 041 | LDSC | Ley de Desarrollo Sustentable de la Cafeticultura |
| 042 | LDSCA | Ley de Desarrollo Sustentable de la Caña de Azúcar |
| 043 | LDEFAGN | Ley de Disciplina del Ejército, Fuerza Aérea y Guardia Nacional |

---

## [Lote 3 — Leyes 024-033] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 024 | LASoc | Ley de Asistencia Social |
| 025 | LAPP | Ley de Asociaciones Público Privadas |
| 026 | LARCP | Ley de Asociaciones Religiosas y Culto Público |
| 027 | LAC | Ley de Aviación Civil |
| 028 | LAAT | Ley de Ayuda Alimentaria para los Trabajadores |
| 029 | LBio | Ley de Biocombustibles |
| 030 | LBOGM | Ley de Bioseguridad de Organismos Genéticamente Modificados |
| 031 | LCEC | Ley de Cámaras Empresariales y sus Confederaciones |
| 032 | LCPAF | Ley de Caminos, Puentes y Autotransporte Federal |
| 033 | LCP | Ley de Capitalización del PROCAMPO |

### Corregido (calidad)
- `compute_md_slug` ahora elimina sufijos numéricos de fecha en nombres de PDF (ej. `LCEC_120419` → `LCEC`). Afecta a ~34 leyes del catálogo completo.

---

## [Lote 2 — Leyes 014-023] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 014 | LAgra | Ley Agraria |
| 015 | LAASSP | Ley de Adquisiciones, Arrendamientos y Servicios del Sector Público |
| 016 | LAero | Ley de Aeropuertos |
| 017 | LAN | Ley de Aguas Nacionales |
| 018 | LACP | Ley de Ahorro y Crédito Popular |
| 019 | LAmn | Ley de Amnistía (DOF 22/01/2021) |
| 020 | LA | Ley de Amnistía (Sin reforma — versión anterior) |
| 021 | LAmp | Ley de Amparo, Reglamentaria de los artículos 103 y 107 de la Constitución |
| 022 | LAAM | Ley de Ascensos de la Armada de México |
| 023 | LAREFAGN | Ley de Ascensos y Recompensas del Ejército, Fuerza Aérea y Guardia Nacional |

### Cambiado (calidad del repo)
- `gen_indice.py` ahora incluye fecha de actualización y porcentaje de avance en el encabezado de `INDICE.md`.
- `README.md` actualizado: sección de estructura con convención de nombres correcta, nueva sección de **Progreso** con estado de lotes.

---

## [Lote 1 — Leyes 001-013 + LISR] — 2026-03-18

### Leyes publicadas (14)
| No. | Clave | Ley |
|-----|-------|-----|
| 001 | CPEUM | Constitución Política de los Estados Unidos Mexicanos |
| 002 | CCF | Código Civil Federal |
| 003 | CCom | Código de Comercio |
| 004 | CJM | Código de Justicia Militar |
| 005 | CFPC | Código Federal de Procedimientos Civiles |
| 006 | CFF | Código Fiscal de la Federación |
| 007 | CMPP | Código Militar de Procedimientos Penales |
| 008 | CNPCF | Código Nacional de Procedimientos Civiles y Familiares |
| 009 | CNPP | Código Nacional de Procedimientos Penales |
| 010 | CPF | Código Penal Federal |
| 011 | EGDF | Estatuto de Gobierno del Distrito Federal |
| 012 | ISEDIPL | Impuesto sobre Servicios Expresamente Declarados de Interés Público por Ley |
| 013 | LAdua | Ley Aduanera |
| 114 | LISR | Ley del Impuesto sobre la Renta |

### Corregido
- Convención de nombres: `{ABREV}_{nombre_en_snake_case}.md` aplicada consistently a todos los archivos.
- `derive_acronym` ahora trunca el nombre en la primera coma o paréntesis y limita el acrónimo a 8 caracteres para evitar nombres excesivamente largos.

## [0.2.0] — 2026-03-18

### Agregado
- `scripts/download_leyes.py` — Scraper que parsea la tabla de diputados.gob.mx y descarga los 315+ PDFs de leyes federales vigentes.
- `scripts/batch_convert.py` — Conversión en batch de todos los PDFs en `origen-docs/` a Markdown.
- `scripts/gen_indice.py` — Genera `INDICE.md` con tabla navegable y links a cada `.md` disponible.
- `INDICE.md` — Índice autogenerado de las 315 leyes con links a los Markdowns disponibles.
- `catalogo.json` — Catálogo estructurado (autogenerado) con metadata de cada ley.

### Cambiado
- Carpeta `leyes/` renombrada a `markdown/` para mayor claridad.
- `scripts/pdf_to_md.py` ahora genera output en `markdown/` por defecto.
- `README.md` reescrito para reflejar el alcance completo del proyecto (315+ leyes federales).

## [0.1.0] — 2026-03-18

### Agregado
- `scripts/pdf_to_md.py` — Script de conversión de PDF a Markdown estructurado.
- `markdown/LISR.md` — Ley del Impuesto Sobre la Renta convertida a Markdown.
- `README.md` inicial.
- `requirements.txt` con dependencia de `pdfplumber`.
- `.gitignore` configurado para excluir PDFs, venv y archivos de sistema.
