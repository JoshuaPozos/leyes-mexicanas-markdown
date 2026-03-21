# TODOS — Mejoras al script de conversión PDF → Markdown

> Issues pendientes de corrección en `scripts/pdf_to_md.py`, `scripts/download_leyes.py` y/o los archivos `.md` generados.

---

## 1. ~~Renombrar PDFs descargados con el patrón slug de los MD~~ ✅

- **Estado:** Resuelto — `download_leyes.py` ahora guarda como `{md_slug}.pdf`
- **Archivos afectados:** `scripts/download_leyes.py`

---

## 2. ~~Falsos positivos en detección de encabezados de artículos~~ ✅

- **Estado:** Resuelto — `is_article_heading` y `ARTICLE_ORDINAL_RE` ahora solo reconocen mayúscula inicial; guardia de contexto rechaza referencias precedidas por preposiciones ("el", "del", "al", etc.)
- **Resultado:** 1762 falsos positivos → 0 en los 315 archivos
- **Archivos afectados:** `scripts/pdf_to_md.py`

---

## 3. Encabezados de tablas no se extraen correctamente de imágenes/OCR

- **Prioridad:** Alta
- **Archivos afectados:** `scripts/pdf_to_md.py`, todos los `.md` con tablas
- **Causa raíz:** Cuando el PDF contiene tablas renderizadas como imagen, el OCR no extrae correctamente los encabezados de columna. Los encabezados se pierden o se concatenan de forma ilegible en una sola línea.
- **Ejemplo:** En la LISR Art. 96, la "TARIFA MENSUAL" del PDF tiene encabezados claros: "Límite inferior | Límite superior | Cuota fija | Por ciento para aplicarse sobre el excedente del límite inferior". En el MD generado aparece como: `**TARIFA MENSUAL** Por ciento para aplicarse sobre el nte ura , Limite inferior Limite superior Cuota fija excedente del` — todo revuelto en una línea, y la tabla queda con encabezados genéricos `| $ | $ | $ | % |`.
- **Fix propuesto:** Mejorar el post-procesamiento de tablas detectadas por OCR: reconstruir encabezados a partir de la estructura de columnas, o aplicar heurísticas para separar el texto de encabezado cuando se detecta un patrón de tabla Markdown.
