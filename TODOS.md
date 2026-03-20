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

## 7. Fracciones con numerales romanos (I., II., III., etc.) no se formatean como lista

**Prioridad:** Alta
**Archivos afectados:** Todos (prácticamente todas las leyes usan fracciones con numerales romanos)
**Causa raíz:** `build_markdown()` no tiene lógica para detectar fracciones romanas. Las líneas que inician con `I.`, `II.`, `XVI.`, etc. se tratan como texto de párrafo normal y se unen con la línea anterior por la lógica de unión de párrafos.

**Ejemplo actual (LISR Artículo 93):**
```markdown
I. Las prestaciones distintas del salario que reciban los trabajadores del salario mínimo general...
II. Por el excedente de las prestaciones exceptuadas del pago del impuesto...
III. Las indemnizaciones por riesgos de trabajo o enfermedades...
```
Estas fracciones se muestran como párrafos continuos sin separación visual.

**Debería ser:**
```markdown

I. Las prestaciones distintas del salario que reciban los trabajadores del salario mínimo general...

II. Por el excedente de las prestaciones exceptuadas del pago del impuesto...

III. Las indemnizaciones por riesgos de trabajo o enfermedades...
```
Cada fracción debe ser un párrafo separado, garantizando un salto de línea antes del numeral romano.

**Regex propuesto para detectar fracciones:**
```python
FRACCION_ROMAN_RE = re.compile(
    r'^(X{0,3}(?:IX|IV|V?I{0,3}))\.\s+'
)
```
Esto matchea: `I.`, `II.`, `III.`, `IV.`, `V.`, `VI.`, ..., `XXIX.`, `XXX.`, etc.

**Fix propuesto:** En `build_markdown()`, cuando una línea inicia con un numeral romano seguido de `.`, tratarla como inicio de un nuevo párrafo (flush del buffer anterior y separar con línea en blanco).

---

## 8. Sub-incisos a), b), c), etc. no se formatean como sub-lista

**Prioridad:** Alta
**Archivos afectados:** Todos los que contienen fracciones con incisos (muy común en leyes fiscales)
**Causa raíz:** El script une todas las líneas en un solo párrafo. Los incisos `a)`, `b)`, `c)`, etc. que en el PDF aparecen en líneas separadas e indentadas, terminan inline dentro del mismo párrafo de la fracción.

**Ejemplo actual (LISR Artículo 93 fracción XVI):**
```markdown
XVI. Las remuneraciones por servicios personales subordinados que perciban los extranjeros, en los siguientes casos: a) Los agentes diplomáticos. b) Los agentes consulares, en el ejercicio de sus funciones, en los casos de reciprocidad. c) Los empleados de embajadas, legaciones y consulados extranjeros...
```

**Debería ser:**
```markdown
XVI. Las remuneraciones por servicios personales subordinados que perciban los extranjeros, en los siguientes casos:

a) Los agentes diplomáticos.

b) Los agentes consulares, en el ejercicio de sus funciones, en los casos de reciprocidad.

c) Los empleados de embajadas, legaciones y consulados extranjeros...
```

**PDF de referencia:** En el PDF, cada inciso (a, b, c, ...) aparece en una línea separada con indentación, como sub-lista.

**Regex propuesto:**
```python
INCISO_RE = re.compile(r'^([a-z]\))\s+')
```
Matchea: `a) `, `b) `, `c) `, ..., `z) `.

**Fix propuesto:** Dos niveles:
1. **En `build_markdown()`:** Detectar líneas que inician con `a)`, `b)`, etc. y tratarlas como nuevo párrafo.
2. **Post-proceso:** Si un inciso quedó inline (unido por la lógica de párrafos), splitear el texto en los patrones ` a) `, ` b) `, etc. y poner cada uno en su propia línea.

---

## 9. Tablas como imágenes en el PDF no se extraen

**Prioridad:** Media-Alta
**Archivos afectados:** LISR (Artículo 96 — TARIFA MENSUAL), y potencialmente más leyes con tablas fiscales
**Causa raíz:** Algunas tablas en los PDFs están embebidas como imágenes (no como texto/vectores). `pdfplumber.extract_text()` no puede leer texto de imágenes, y `page.extract_tables()` devuelve 0 tablas para estas páginas.

**Ejemplo (LISR Artículo 96):**

El PDF muestra una "TARIFA MENSUAL" con columnas: Límite inferior, Límite superior, Cuota fija, % sobre excedente. En el markdown generado, la tabla simplemente desaparece:
```markdown
La retención se calculará aplicando a la totalidad de los ingresos obtenidos en un mes de calendario, la siguiente:
Quienes hagan pagos por concepto de gratificación anual...
```
Debería haber una tabla markdown entre "la siguiente:" y "Quienes hagan pagos...".

**Diagnóstico técnico:**
- Página 130 del LISR.pdf tiene 2 imágenes: logo (56×53px) y tabla (390×292px)
- `page.extract_tables()` retorna `[]` (0 tablas)
- `page.images[1]` es la tabla: `x0=111, y0=247.5, x1=501, y1=539.9`
- La tabla contiene datos numéricos fiscales que no se pueden reconstruir sin OCR

**Opciones de solución (de menos a más compleja):**

### Opción A: Placeholder (mínimo esfuerzo)
Detectar imágenes grandes en la página y agregar un placeholder:
```markdown
<!-- TABLA: imagen no extraíble (ver PDF original, página 130) -->
```
**Pro:** Simple, no requiere dependencias extra.
**Contra:** No incluye los datos.

### Opción B: OCR con pytesseract (mejor resultado)
1. Detectar imágenes grandes en cada página (ancho > 200px y alto > 100px → probable tabla)
2. Extraer la imagen del PDF con `page.crop().to_image().original`
3. Aplicar OCR con `pytesseract.image_to_string()` o `pytesseract.image_to_data()`
4. Parsear el resultado del OCR a tabla markdown

**Dependencias extra:** `pytesseract`, `Pillow`, Tesseract-OCR instalado en el sistema (`brew install tesseract` + `tesseract-ocr-spa` para idioma español).

```python
# Pseudocódigo
from PIL import Image
import pytesseract

for img in page.images:
    if (img['x1'] - img['x0']) > 200 and (img['bottom'] - img['top']) > 100:
        cropped = page.crop((img['x0'], img['top'], img['x1'], img['bottom']))
        pil_img = cropped.to_image(resolution=300).original
        text = pytesseract.image_to_string(pil_img, lang='spa')
        # Parsear a tabla markdown...
```

**Pro:** Automatizado, extrae la tabla real.
**Contra:** Requiere Tesseract instalado, OCR puede tener errores en números.

### Opción C: Híbrida (recomendada)
1. Intentar `page.extract_tables()` primero (para tablas basadas en texto/vectores)
2. Si no hay tablas pero hay imágenes grandes, intentar OCR si `pytesseract` está disponible
3. Si OCR no disponible, insertar placeholder con número de página

**Fix propuesto:** Implementar Opción C como la más robusta.

---

## Resumen de prioridades

| # | Issue | Prioridad | Estado |
|---|-------|-----------|--------|
| 1 | Falso positivo `##` en "título de..." | Alta | ✅ Resuelto (17 → 0) |
| 2 | Header corrido del PDF en el texto | Alta | ✅ Resuelto (80 → 0 archivos) |
| 3 | "Transitorios" sin formato heading | Media | ✅ Resuelto (74 archivos) |
| 4 | "ARTÍCULO TERCERO..." sin heading | Media | ✅ Resuelto (58 archivos) |
| 5 | Ordinales sin negritas | Media | ✅ Resuelto (77 archivos) |
| 6 | Nombres de sección descriptivos | Baja | ✅ Resuelto (114 archivos, ~48 FP eliminados) |
| 7 | Fracciones romanas (I., II., III.) sin separar | Alta | ✅ Resuelto (114 archivos) |
| 8 | Sub-incisos a), b), c) inline | Alta | ✅ Resuelto (114 archivos) |
| 9 | Tablas-imagen no extraídas del PDF | Media-Alta | ✅ Resuelto (placeholders, 114 archivos) |

---

## Notas

- Los issues 1-5 fueron corregidos en `scripts/pdf_to_md.py` el 2026-03-19.
- Los 84 archivos existentes fueron reconvertidos con el script mejorado.
- El issue 6 queda pendiente (requiere análisis de coordenadas del PDF).
- Los issues 7-9 fueron documentados el 2026-03-19. Aplican a todos los archivos convertidos.
- Los issues 7-8 fueron corregidos en `scripts/pdf_to_md.py` y los 114 archivos reconvertidos (commit `e72b398`).
- Los issues 6 y 9 fueron corregidos: nombres descriptivos de sección con `—`, placeholders para tablas-imagen, ~48 falsos positivos eliminados (commit `a0912fa`).
