# 🇲🇽 mx-md — Leyes mexicanas en Markdown

Las **315+ leyes federales vigentes** de México convertidas a **Markdown limpio y estructurado**, listas para usarse en agentes de IA, RAG, búsqueda semántica o cualquier herramienta que consuma texto.

Fuente oficial: [Cámara de Diputados — Leyes Federales Vigentes](https://www.diputados.gob.mx/LeyesBiblio/index.htm)

👉 **[Ver índice completo de leyes](INDICE.md)**

---

## ¿Por qué existe esto?

Los PDFs de la [Cámara de Diputados](https://www.diputados.gob.mx) son la fuente oficial de la legislación mexicana, pero son difíciles de consumir programáticamente:

- Encabezados y pies de página repetidos en cada hoja
- Marcadores de página embebidos en mitad del texto
- Sin estructura semántica aprovechable

Este repo los convierte a Markdown con jerarquía clara (`##` por Título/Capítulo, `###` por Artículo) para que tus agentes puedan trabajar con ellos sin fricción.

---

## � Progreso

| Lote | Leyes | Estado |
|------|-------|--------|
| Lote 1 | 001-013 + LISR (114) | ✅ Publicado |
| Lote 2 | 014-023 | ✅ Publicado |
| Lote 3 | 024-033 | ✅ Publicado |
| Lote 4 | 034-043 | ✅ Publicado |
| Lote 5 | 044-053 | ✅ Publicado |
| Lote 6 | 054-063 | ✅ Publicado |
| Lote 7 | 064-073 | ✅ Publicado |
| Lotes 8-32 | 074-315 | ⏳ Pendiente |

Consulta el [CHANGELOG](CHANGELOG.md) y el [INDICE](INDICE.md) para el estado actualizado ley por ley.

---

## 📂 Estructura del repositorio

```
mx-md/
├── markdown/               # Markdowns generados (listos para usar)
│   ├── CPEUM_constitucion_politica_de_los_estados_unidos_mexicanos.md
│   ├── LISR_ley_del_impuesto_sobre_la_renta.md
│   ├── CFF_codigo_fiscal_de_la_federacion.md
│   └── ...                 # Convención: {ABREV}_{nombre_snake_case}.md
├── scripts/
│   ├── download_leyes.py   # Descarga todos los PDFs desde diputados.gob.mx
│   ├── batch_convert.py    # Convierte todos los PDFs a Markdown
│   ├── pdf_to_md.py        # Conversión individual (CLI)
│   └── gen_indice.py       # Genera INDICE.md
├── origen-docs/            # PDFs descargados (no versionados)
├── catalogo.json           # Catálogo de leyes (generado automáticamente)
├── INDICE.md               # Índice navegable de todas las leyes
├── CHANGELOG.md            # Historial de lotes publicados
├── requirements.txt
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
pip install -r requirements.txt
```

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

### 3. Convertir a Markdown

```bash
# Convertir todos los PDFs
python scripts/batch_convert.py

# Solo los que no se han convertido
python scripts/batch_convert.py --skip-existing

# Convertir un PDF específico
python scripts/pdf_to_md.py origen-docs/LISR.pdf --verbose
```

### 4. Regenerar el índice

```bash
python scripts/gen_indice.py
```

---

## 🤖 Cómo usarlo en un agente / RAG

El Markdown generado tiene esta estructura consistente:

```markdown
# Ley del Impuesto Sobre la Renta (LISR)

## TÍTULO I
DISPOSICIONES GENERALES

### Artículo 1
Las personas físicas y las morales están obligadas al pago...

### Artículo 2
Para los efectos de esta Ley, se considera establecimiento permanente...
```

Puedes chunkearlo por artículo (cada `### Artículo N` es un chunk natural), por capítulo, o cargarlo completo dependiendo del contexto de tu ventana.

---

## 🔧 Cómo funciona

1. **Scraping** — `download_leyes.py` parsea la tabla de [diputados.gob.mx](https://www.diputados.gob.mx/LeyesBiblio/index.htm) y descarga cada PDF.
2. **Extracción** — `pdf_to_md.py` usa [`pdfplumber`](https://github.com/jsvine/pdfplumber) para extraer texto con alta fidelidad.
3. **Limpieza** — filtra encabezados repetitivos de cada página y marcadores de paginación (`N de 313`).
4. **Estructuración** — detecta `TÍTULO`, `CAPÍTULO`, `SECCIÓN` y `Artículo N` para asignar niveles de encabezado Markdown.
5. **Unión de líneas** — une líneas de continuación que el PDF partió artificialmente, incluyendo palabras con guión.
6. **Índice** — `gen_indice.py` genera un `INDICE.md` navegable con links a cada ley disponible.

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

## Licencia

MIT — el código es libre. El contenido de las leyes es de dominio público conforme a la legislación mexicana.
