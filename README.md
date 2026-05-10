# 🇲🇽 mx-md — Leyes mexicanas en Markdown y JSON canónico

Las **315 leyes federales vigentes** de México en **Markdown estructurado** y **JSON canónico (AST)**, listas para agentes de IA, RAG, búsqueda semántica, APIs legales o cualquier herramienta que consuma texto o datos estructurados.

- **37,939 artículos** · **58,310 fracciones** · **35,176 notas de reforma** · **42 tablas OCR**
- Fuente oficial: [Cámara de Diputados — Leyes Federales Vigentes](https://www.diputados.gob.mx/LeyesBiblio/index.htm)

👉 **[Ver índice completo de leyes](INDICE.md)**

---

## ¿Por qué existe esto?

Los PDFs de la [Cámara de Diputados](https://www.diputados.gob.mx) son la fuente oficial de la legislación mexicana, pero son difíciles de consumir programáticamente:

- Encabezados y pies de página repetidos en cada hoja
- Marcadores de página embebidos en mitad del texto
- Sin estructura semántica aprovechable

Este repo los convierte a dos formatos complementarios:

1. **JSON canónico (AST)** — Árbol sintáctico estructurado con IDs estables, ideal para APIs, búsquedas exactas y análisis programático.
2. **Markdown** — Renderizado desde el JSON, con jerarquía clara (`##` por Título/Capítulo, `###` por Artículo), ideal para RAG, LLMs y lectura humana.

El **JSON es la fuente de verdad**; el Markdown es una de sus vistas.

---

## 📊 Progreso

**315/315 leyes** — catálogo completo.

Consulta el [CHANGELOG](CHANGELOG.md) y el [INDICE](INDICE.md) para el estado actualizado ley por ley.

---

## 📂 Estructura del repositorio

```
mx-md/
├── canonical/              # JSON canónico (AST) — fuente de verdad
│   ├── CPEUM_constitucion_politica_de_los_estados_unidos_mexicanos.json
│   ├── LISR_ley_del_impuesto_sobre_la_renta.json
│   └── ...                 # 315 archivos, uno por ley
├── markdown/               # Markdown renderizado desde el JSON
│   ├── CPEUM_constitucion_politica_de_los_estados_unidos_mexicanos.md
│   ├── LISR_ley_del_impuesto_sobre_la_renta.md
│   └── ...                 # Convención: {ABREV}_{nombre_snake_case}.md
├── schema/
│   ├── law_ast.schema.json # JSON Schema del AST canónico
│   └── example_cpeum_fragment.json
├── scripts/
│   ├── download_leyes.py   # Descarga todos los PDFs desde diputados.gob.mx
│   ├── batch_convert.py    # Convierte todos los PDFs a JSON + Markdown (paralelo)
│   ├── pdf_to_md.py        # Conversión individual (CLI)
│   ├── gen_indice.py       # Genera INDICE.md con stats por ley
│   ├── constants.py        # Constantes operativas con docstrings (umbrales, timeouts)
│   └── _log.py             # Logging estructurado (MX_MD_LOG_LEVEL)
├── tests/                  # Suite de pytest (307 tests, cobertura 48 %)
├── origen-docs/            # PDFs descargados (no versionados)
├── catalogo.json           # Catálogo de leyes con SHA-256 por PDF
├── INDICE.md               # Índice navegable con conteo de artículos
├── CHANGELOG.md            # Historial de cambios
├── pyproject.toml          # Empaquetado y dependencias (extras: [dev])
├── requirements.lock       # Lockfile reproducible (versiones exactas)
└── README.md
```

### Convención de nombres

Los archivos Markdown siguen el patrón `{ABREV}_{nombre_snake_case}.md`:

- `ABREV` — la sigla oficial de la ley (ej. `CPEUM`, `CFF`, `LISR`). Para las pocas leyes cuyo PDF tiene nombre numérico, se deriva del nombre completo (máx. 8 letras).
- `nombre_snake_case` — el nombre completo normalizado a ASCII y snake_case, truncado a 70 caracteres.

---

## 🚀 Uso rápido

### 1. Instalar dependencias

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Instalación normal (rangos de versión flexibles)
pip install -e .

# Instalación reproducible (versiones exactas del lockfile)
pip install -r requirements.lock && pip install -e . --no-deps

# Para desarrollo (incluye ruff, mypy, pytest)
pip install -e ".[dev]"
```

> Tesseract debe estar instalado a nivel de sistema operativo para el OCR de tablas:
> macOS: `brew install tesseract` · Ubuntu/Debian: `apt install tesseract-ocr`

### 2. Descargar todos los PDFs

```bash
# Descargar las 315+ leyes (~2 GB)
python scripts/download_leyes.py

# Solo ver el catálogo sin descargar
python scripts/download_leyes.py --list

# Descargar solo las que faltan
python scripts/download_leyes.py --skip-existing

# Descargar solo las primeras 10 (para probar)
python scripts/download_leyes.py --limit 10
```

El descargador valida cada PDF antes de aceptarlo (bytes mágicos `%PDF-`,
host en allowlist `diputados.gob.mx`, retry con backoff exponencial ante
fallos transitorios) y anota el SHA-256 de cada archivo en `catalogo.json`
para detectar reformas upstream entre corridas.

### 3. Convertir a JSON + Markdown

```bash
# Convertir todos los PDFs en paralelo (default: os.cpu_count() workers)
python scripts/batch_convert.py

# Controlar el paralelismo (1 = serial, útil para depurar)
python scripts/batch_convert.py --workers 4

# Timeout por PDF (default 300 s) — un PDF que se cuelgue se reporta como
# error sin bloquear al pool
python scripts/batch_convert.py --timeout 600

# Solo los que no se han convertido
python scripts/batch_convert.py --skip-existing

# Solo JSON (sin Markdown)
python scripts/batch_convert.py --format json

# Solo Markdown (sin JSON)
python scripts/batch_convert.py --format md

# Convertir con validación contra schema
python scripts/batch_convert.py --validate

# Convertir un PDF específico
python scripts/pdf_to_md.py origen-docs/LISR_ley_del_impuesto_sobre_la_renta.pdf --verbose
```

Speedup medido con 8 cores: ~**2.4x** vs serial (bottleneck es OCR / I/O,
no CPU puro).

### 4. Regenerar el índice

```bash
python scripts/gen_indice.py
```

---

## 🤖 Cómo usarlo en un agente / RAG

### Markdown

El Markdown tiene esta estructura consistente:

```markdown
# Ley del Impuesto Sobre la Renta

## TÍTULO I
DISPOSICIONES GENERALES

### Artículo 1
Las personas físicas y las morales están obligadas al pago...

### Artículo 2
Para los efectos de esta Ley, se considera establecimiento permanente...
```

Puedes chunkearlo por artículo (cada `### Artículo N` es un chunk natural), por capítulo, o cargarlo completo.

### JSON canónico (AST)

Cada ley tiene un JSON estructurado con nodos tipados e IDs estables:

```json
{
  "schema_version": "1.0.0",
  "id": "LISR_ley_del_impuesto_sobre_la_renta",
  "abbreviation": "LISR",
  "name": "LEY del Impuesto Sobre la Renta",
  "structure": [
    {
      "type": "titulo",
      "id": "titulo-i",
      "heading": "TÍTULO I",
      "descriptor": "DISPOSICIONES GENERALES",
      "children": [
        {
          "type": "articulo",
          "id": "titulo-i.articulo-1",
          "heading": "Artículo 1",
          "content": [
            { "type": "paragraph", "text": "Las personas físicas y las morales están obligadas..." },
            { "type": "fraccion", "ordinal": "I", "text": "Las residentes en México..." }
          ]
        }
      ]
    }
  ]
}
```

Los IDs son paths jerárquicos estables: `titulo-i.capitulo-ii.articulo-15`. Puedes usarlos para referencia directa, linking cruzado, y versionado.

---

## 🔧 Cómo funciona

```
PDF → extract_lines() → build_ast() → AST canónico (JSON)
                                        ├── json.dump() → canonical/{slug}.json
                                        └── render_markdown() → markdown/{slug}.md
```

1. **Scraping** — `download_leyes.py` parsea la tabla de [diputados.gob.mx](https://www.diputados.gob.mx/LeyesBiblio/index.htm) y descarga cada PDF.
2. **Extracción** — `extract_lines()` usa [`pdfplumber`](https://github.com/jsvine/pdfplumber) para extraer texto, filtrando headers repetitivos y marcadores de página. Tablas-imagen se extraen con OCR (Tesseract).
3. **AST** — `build_ast()` construye un árbol canónico: detecta Títulos, Capítulos, Secciones, Artículos, fracciones, incisos, notas de reforma y tablas. Asigna IDs estables jerárquicos.
4. **JSON** — El AST se serializa como JSON. Cada archivo cumple `schema/law_ast.schema.json`.
5. **Markdown** — `render_markdown()` recorre el AST y produce Markdown limpio. El JSON es la fuente de verdad.
6. **Índice** — `gen_indice.py` genera un `INDICE.md` con links a cada ley y conteo de artículos.

---

## 📥 Fuentes

Todos los PDFs se descargan directamente de la fuente oficial:

- **Cámara de Diputados** → [diputados.gob.mx/LeyesBiblio](https://www.diputados.gob.mx/LeyesBiblio/index.htm)

> Los PDFs **no están versionados** en este repositorio por su tamaño y porque cambian con cada reforma. El script siempre descarga la versión vigente.

---

## 🤝 Contribuir

1. Clona el repo y ejecuta los scripts de descarga/conversión
2. Si el Markdown de alguna ley tiene errores, mejora la lógica en `pdf_to_md.py`
3. Abre un PR con los cambios

---

## 🛠️ Desarrollo

### Instalar dependencias de dev

```bash
pip install -e ".[dev]"     # incluye pytest, pytest-cov, ruff, mypy
```

### Tests

```bash
pytest tests/ -q             # suite completa (~8 s, 307 tests)
pytest tests/ --cov=scripts  # con cobertura (48 % global)
```

### Lint y type-check

```bash
ruff check scripts/ tests/
mypy scripts/                # disallow_untyped_defs activado
```

Ambos corren automáticamente en CI (`.github/workflows/ci.yml`) sobre
Python 3.10, 3.11 y 3.12 en cada push.

### Logging estructurado

Los scripts usan `getLogger(__name__)` con nivel controlable por variable
de entorno:

```bash
MX_MD_LOG_LEVEL=DEBUG python scripts/pdf_to_md.py origen-docs/CPEUM.pdf
```

Niveles: `DEBUG`, `INFO`, `WARNING` (default), `ERROR`, `CRITICAL`.

### Constantes operativas

`scripts/constants.py` centraliza los umbrales y timeouts que afectan la
conversión (tolerancias OCR, DPI, magic bytes, retries, paralelismo, etc.).
Cada constante tiene un docstring explicando *por qué* el valor elegido.
Cambiarlos requiere revalidar el baseline de regresión.

---

## Licencia

MIT — el código es libre. El contenido de las leyes es de dominio público conforme a la legislación mexicana.
