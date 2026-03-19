# TODOS — Mejoras al script de conversión PDF → Markdown

> Lista de inconsistencias detectadas en los archivos `.md` generados por `pdf_to_md.py`.
> Todas son causadas por el script y aplican a **todos** los archivos convertidos.

---

## 1. Falso positivo: palabras como "título", "capítulo", "sección" convertidas a heading `##`

**Prioridad:** Alta
**Archivos afectados:** 22+ (17 instancias detectadas con grep)
**Causa raíz:** `is_section_heading()` usa `re.IGNORECASE` y el character class `[IVXLCDM\d]` incluye la letra `D` — al ser case-insensitive, la `d` de palabras como "de" matchea como numeral romano.

**Ejemplo (LEPEPM línea 890):**
```markdown
## título de propiedad o traslativo de dominio y deben inscribirse en los registros públicos respectivos. Dicha inscripción
```
**Debería ser** texto normal de párrafo (viene de: "…considerarse como título de propiedad o traslativo de dominio…").

**Otros casos reales encontrados:**
- `## título de crédito, colocados entre el gran público inversionista` (LISR)
- `## título de concesión` (LGeo, LMin, LSAR)
- `## sección de puente transportador` (LIGIE)
- `## sección circular` (LIGIE)
- `## capítulo de compras gubernamentales` (LAASSP)
- `## capítulo IX, y título XI` (CCF)

**Fix propuesto:** Quitar `re.IGNORECASE` de `is_section_heading()`. Los encabezados reales en los PDFs siempre están en MAYÚSCULAS ("TÍTULO IV", "CAPÍTULO II") o en Title Case ("Capítulo Único"). Ajustar el regex para aceptar ambas variantes sin `IGNORECASE`:
```python
re.match(r'^(TÍTULO|CAPÍTULO|SECCIÓN|Título|Capítulo|Sección)\s+[IVXLCDM\d]+', line.strip())
```

---

## 2. Encabezado corrido (running header) del PDF se filtra en el texto

**Prioridad:** Alta
**Archivos afectados:** 80 de 84 archivos convertidos
**Causa raíz:** `is_header_line()` usa `HEADER_PATTERN_RE` con un regex genérico que solo matchea ciertos patrones como `LEY DEL|LEY FEDERAL|LEY GENERAL...` pero no cubre todos los títulos de leyes. Además, cuando el header de página se une a la siguiente línea por la lógica de unión de párrafos, ya no se puede filtrar.

**Ejemplo (LEPEPM líneas 57, 84, 108, etc.):**
```
...la comercialización y la LEY DE LA EMPRESA PÚBLICA DEL ESTADO, PETRÓLEOS MEXICANOS formulación con biocombustibles...
```
El texto "LEY DE LA EMPRESA PÚBLICA DEL ESTADO, PETRÓLEOS MEXICANOS" es el encabezado que se repite en cada página del PDF y debería eliminarse.

**Escala del problema:**
- LIGIE: ~921 instancias
- CPEUM: ~732 instancias
- CFF: ~539 instancias
- LIC: ~418 instancias
- ... (80 archivos en total)

**Fix propuesto:** Mejorar la detección de headers de dos maneras:
1. **Antes de unir líneas:** Detectar el título real de cada ley (primera línea en ALL CAPS) y usarlo como patrón de filtro dinámico durante la extracción.
2. **Post-procesamiento:** Eliminar ocurrencias del título de la ley que aparezcan inline. Se puede leer el título del `# H1` generado y limpiar el texto.

---

## 3. "Transitorios" / "Transitorio" no se formatea como encabezado

**Prioridad:** Media
**Archivos afectados:** Todos los que tienen artículos transitorios (la mayoría)
**Causa raíz:** `build_markdown()` solo detecta "Artículo N" y "TÍTULO/CAPÍTULO/SECCIÓN" como headings. No hay lógica para "Transitorios".

**Ejemplo (LEPEPM línea 909):**
```
Transitorios Primero. El presente Decreto entrará en vigor...
```
**Debería ser:**
```markdown
## Transitorios

**Primero.** El presente Decreto entrará en vigor...
```

En el PDF, "Transitorios" aparece centrado y en negritas, como título de sección.

**Fix propuesto:** Agregar detección de `^Transitorios?$` o `Transitorios` al inicio de línea como heading `##`. Debe separarse del texto que sigue.

---

## 4. "ARTÍCULO TERCERO A ARTÍCULO DÉCIMO" no se formatea como heading

**Prioridad:** Media
**Archivos afectados:** Al menos 4 archivos detectados (LEPEPM, LEPECFE, LBio, LGeo)
**Causa raíz:** `is_article_heading()` solo detecta "Artículo N" (con número). Los artículos de decretos que usan ordinales en texto ("ARTÍCULO TERCERO", "ARTÍCULO SEGUNDO") no se detectan.

**Ejemplo (LEPEPM línea 908):**
```
ARTÍCULO TERCERO A ARTÍCULO DÉCIMO.- …….
```
**Debería ser:**
```markdown
### ARTÍCULO TERCERO A ARTÍCULO DÉCIMO
.- …….
```

**Otros casos:**
- `ARTÍCULO SÉPTIMO A ARTÍCULO DÉCIMO.- ………` (LBio)
- `ARTÍCULO OCTAVO A ARTÍCULO DÉCIMO.- ………` (LGeo)
- `ARTÍCULO SEGUNDO A ARTÍCULO DÉCIMO.- ………` (LEPECFE)

**Fix propuesto:** Ampliar `is_article_heading()` para detectar también artículos con ordinales en texto:
```python
ORDINALS = r'(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SÉPTIMO|OCTAVO|NOVENO|DÉCIMO|...)'
re.match(rf'^ARTÍCULO\s+{ORDINALS}', line.strip())
```

---

## 5. Ordinales transitorios ("Primero.", "Segundo.", etc.) no están en negritas

**Prioridad:** Media
**Archivos afectados:** Todos los que tienen artículos transitorios
**Causa raíz:** No existe lógica de formateo para estas etiquetas. En el PDF aparecen en **negritas**.

**Ejemplo:**
```
Primero. El presente Decreto entrará en vigor el día siguiente...
Segundo. La Cámara de Diputados debe realizar las previsiones...
```
**Debería ser:**
```markdown
**Primero.** El presente Decreto entrará en vigor el día siguiente...
**Segundo.** La Cámara de Diputados debe realizar las previsiones...
```

**Ordinales a detectar:**
- Primero, Segundo, Tercero, Cuarto, Quinto, Sexto, Séptimo, Octavo, Noveno, Décimo
- Compuestos: Décimo Primero, Décimo Segundo, ..., Vigésimo, Vigésimo Primero, etc.
- Variantes con `.-` o `.` como separador

**Fix propuesto:** En `build_markdown()`, detectar líneas que inicien con un ordinal seguido de `.` o `.-` y envolver el ordinal en `**bold**`.

---

## 6. Secciones con nombre descriptivo no se detectan como heading

**Prioridad:** Baja
**Archivos afectados:** Varios
**Causa raíz:** `is_section_heading()` solo matchea "TÍTULO/CAPÍTULO/SECCIÓN + numeral". Pero en muchos PDFs hay encabezados como "Disposiciones Generales", "Del Régimen Fiscal", que aparecen centrados y en una línea separada.

**Ejemplo (LEPEPM):**
```
Capítulo Único Disposiciones Generales
```
Esto debería ser:
```markdown
## Capítulo Único
### Disposiciones Generales
```

**Nota:** Este es más difícil de resolver de forma genérica ya que requiere detectar texto centrado o en mayúsculas que actúa como sub-encabezado. Podría requerir analizar la posición del texto en el PDF (coordenadas x).

---

## Resumen de prioridades

| # | Issue | Prioridad | Impacto |
|---|-------|-----------|---------|
| 1 | Falso positivo `##` en "título de..." | Alta | 22+ líneas mal formateadas |
| 2 | Header corrido del PDF en el texto | Alta | 80/84 archivos, miles de instancias |
| 3 | "Transitorios" sin formato heading | Media | Casi todos los archivos |
| 4 | "ARTÍCULO TERCERO..." sin heading | Media | 4+ archivos |
| 5 | Ordinales sin negritas | Media | Casi todos los archivos |
| 6 | Nombres de sección descriptivos | Baja | Varios archivos |

---

## Notas

- Los issues 1-5 se corrigen en `scripts/pdf_to_md.py`.
- Después de corregir el script, se deben **reconvertir todos los archivos** existentes.
- El issue 2 (running header) es el de mayor impacto visual y de contenido.
