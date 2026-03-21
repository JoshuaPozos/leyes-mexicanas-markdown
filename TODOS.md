# TODOS — Mejoras al script de conversión PDF → Markdown

> Issues pendientes de corrección en `scripts/pdf_to_md.py`, `scripts/download_leyes.py` y/o los archivos `.md` generados.

---

## 1. ~~Renombrar PDFs descargados con el patrón slug de los MD~~ ✅

- **Estado:** Resuelto — `download_leyes.py` ahora guarda como `{md_slug}.pdf`
- **Archivos afectados:** `scripts/download_leyes.py`

---

## 2. Falsos positivos en detección de encabezados de artículos

- **Prioridad:** Alta
- **Archivos afectados:** `scripts/pdf_to_md.py`, todos los `.md` generados
- **Causa raíz:** El script interpreta cualquier aparición de "artículo" o "artículos" como un encabezado de artículo (`### Artículo N`), incluso cuando es solo una referencia dentro del cuerpo del texto (ej. "salvo lo previsto en el artículo 96 de esta Ley").
- **Ejemplo:** En la LISR, el Artículo 90 menciona "salvo lo previsto en el artículo 96 de esta Ley" como referencia. El script lo parte y genera un falso `### artículo 96` (línea 2097) con minúscula, cortando el párrafo del Art. 90. El verdadero Artículo 96 aparece más adelante (línea 2278) con su contenido propio.
- **Fix propuesto:** Validar que un encabezado de artículo real:
  - Inicia con "Artículo" en mayúscula (no "artículo" en minúscula mid-sentence)
  - Aparece al inicio de un párrafo / después de punto y aparte, no mid-sentence
  - No está precedido por preposiciones como "el", "del", "al", "los" que indicarían una referencia

---

## 3. Encabezados de tablas no se extraen correctamente de imágenes/OCR

- **Prioridad:** Alta
- **Archivos afectados:** `scripts/pdf_to_md.py`, todos los `.md` con tablas
- **Causa raíz:** Cuando el PDF contiene tablas renderizadas como imagen, el OCR no extrae correctamente los encabezados de columna. Los encabezados se pierden o se concatenan de forma ilegible en una sola línea.
- **Ejemplo:** En la LISR Art. 96, la "TARIFA MENSUAL" del PDF tiene encabezados claros: "Límite inferior | Límite superior | Cuota fija | Por ciento para aplicarse sobre el excedente del límite inferior". En el MD generado aparece como: `**TARIFA MENSUAL** Por ciento para aplicarse sobre el nte ura , Limite inferior Limite superior Cuota fija excedente del` — todo revuelto en una línea, y la tabla queda con encabezados genéricos `| $ | $ | $ | % |`.
- **Fix propuesto:** Mejorar el post-procesamiento de tablas detectadas por OCR: reconstruir encabezados a partir de la estructura de columnas, o aplicar heurísticas para separar el texto de encabezado cuando se detecta un patrón de tabla Markdown.
