# TODOS — Modelo canónico + IDs estables

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
