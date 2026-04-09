# TODOS — Modelo canónico + IDs estables

---

## Estado actual (completado)

El pipeline de conversión PDF → Markdown está completo y estable:
- 315/315 leyes federales vigentes convertidas
- Scraping de diputados.gob.mx + descarga de PDFs
- Limpieza de headers, paginación, running headers
- Detección de jerarquía: Título > Capítulo > Sección > Artículo
- OCR de tablas-imagen con Tesseract + reconstrucción espacial
- 12 fixes aplicados (falsos positivos, tablas, transitorios, etc.)

---

## 1 — Modelo canónico JSON/AST

**Meta:** Que el pipeline emita un AST estructurado (JSON) como fuente canónica, y que el Markdown se genere desde ese AST. Hoy el Markdown es el centro; debe convertirse en un formato de salida más.

### 1.1 Schema del AST ✅

- [x] Diseñar JSON Schema para el AST (`schema/law_ast.schema.json`)
- [x] Crear ejemplo concreto con fragmento de la CPEUM (`schema/example_cpeum_fragment.json`)

**Nodos estructurales:** `libro`, `titulo`, `capitulo`, `seccion`, `articulo`, `transitorios`, `transitorio_articulo`
**Nodos de contenido:** `paragraph`, `fraccion`, `inciso`, `numeral`, `apartado`, `table`, `reform_note`
**IDs estables:** paths jerárquicos tipo `titulo-1.capitulo-2.art-15`

### 1.2 Refactorizar `pdf_to_md.py` para emitir AST

- [ ] Separar `build_markdown()` en dos funciones:
  - `build_ast(lines) → dict` — construye el árbol canónico (misma lógica de detección)
  - `render_markdown(ast) → list[str]` — recorre el AST y emite Markdown
- [ ] Enriquecer el AST con metadatos del catálogo (`source`, `abbreviation`, `catalog_number`, etc.)
- [ ] Generar IDs estables para cada nodo: `{parent_id}.{type}-{ordinal}`
- [ ] Parsear notas de reforma inline como nodos `reform_note` separados del texto
  - Detectar patrón `(Párrafo|Fracción|Artículo|Inciso) (reformado|adicionado|derogado) DOF DD-MM-YYYY`
  - Extraer `action` y `dof_date` como campos estructurados
- [ ] Detectar y estructurar fracciones (`I.`, `II.`) e incisos (`a)`, `b)`) como nodos propios en vez de párrafos planos
- [ ] Detectar apartados (`A.`, `B.`) como contenedores de fracciones (relevante en CPEUM y leyes laborales)
- [ ] Estructurar tablas como nodos `table` con `headers[]`, `rows[][]`, `source_method` y `source_page`

### 1.3 Doble output: JSON + Markdown

- [ ] `pdf_to_md.py` genera ambos: `{slug}.json` en `canonical/` + `{slug}.md` en `markdown/`
- [ ] Crear directorio `canonical/` en la raíz (315 JSON, uno por ley)
- [ ] `batch_convert.py` ejecuta ambos outputs
- [ ] Flag `--format json|md|both` (default: `both`)
- [ ] Validar cada JSON contra el schema con flag `--validate`

### 1.4 Actualizar gen_indice.py

- [ ] Incluir conteo de artículos/nodos por ley (extraído del JSON)
- [ ] Agregar columna de link al JSON canónico en el índice
- [ ] Regenerar INDICE.md

### 1.5 Documentación

- [ ] Actualizar README.md con la nueva estructura (`canonical/`, schema, doble output)
- [ ] Documentar el schema en README o en `schema/README.md`
- [ ] Actualizar sección "Cómo funciona" con el nuevo pipeline: PDF → AST → JSON + MD

---

## Decisiones de diseño

### ¿Por qué JSON y no base de datos?
- Este es el repo público, open-source. Los JSON son accesibles sin infra.
- Se versionan con git: cualquiera puede clonar y tener las 315 leyes estructuradas.

### ¿Por qué generar el AST al mismo tiempo que el MD?
- La lógica de detección (artículos, secciones, transitorios, fracciones, etc.) ya existe en `build_markdown()`.
- Parsear el Markdown de vuelta al AST sería frágil y redundante.
- El refactor es: extraer esa lógica a `build_ast()`, y que `render_markdown()` solo recorra el árbol.

### IDs estables
- Formato: `titulo-primero.capitulo-i.art-1`
- Son paths jerárquicos, no hashes. Legibles y predecibles.
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
