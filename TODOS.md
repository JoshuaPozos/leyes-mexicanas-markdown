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

## 3. ~~Encabezados de tablas no se extraen correctamente de imágenes/OCR~~ ✅

- **Estado:** Resuelto — `_build_table_from_spatial` reconstruye headers de columna desde filas pre-tabla usando boundaries y detección de filas de unidades
- **Resultado:** Headers como `| $ | $ | $ | % |` → `| Limite inferior ($) | Limite superior ($) | Cuota fija ($) | Por ciento para aplicarse sobre el excedente del (%) |`
- **Archivos afectados:** `scripts/pdf_to_md.py`

---

## 4. ~~Tablas OCR aparecían desplazadas de su posición en el texto~~ ✅

- **Estado:** Resuelto — `extract_lines()` ahora extrae texto por regiones verticales (arriba/tabla/abajo) en vez de agregar la tabla al final de la página
- **Resultado:** Art. 96 LISR: la TARIFA MENSUAL ahora aparece justo después de "la siguiente:" y antes de "Quienes hagan pagos..."
- **Archivos afectados:** `scripts/pdf_to_md.py`
