# 🇲🇽 mx-md — Leyes mexicanas en Markdown

Convierte los PDFs oficiales de leyes y códigos mexicanos a **Markdown limpio y estructurado**, listo para usarse en agentes de IA, RAG, búsqueda semántica o cualquier herramienta que consuma texto.

---

## ¿Por qué existe esto?

Los PDFs de la [Cámara de Diputados](https://www.diputados.gob.mx) son la fuente oficial de la legislación mexicana, pero son difíciles de consumir programáticamente:

- Encabezados y pies de página repetidos en cada hoja
- Marcadores de página embebidos en mitad del texto
- Sin estructura semántica aprovechable

Este repo los convierte a Markdown con jerarquía clara (`##` por Título/Capítulo, `###` por Artículo) para que tus agentes puedan trabajar con ellos sin fricción.

---

## 📂 Estructura del repositorio

```
mx-md/
├── leyes/                  # Markdowns generados (listos para usar)
│   └── LISR.md             # Ley del Impuesto Sobre la Renta
├── scripts/
│   └── pdf_to_md.py        # Script de conversión (CLI)
├── origen-docs/            # Coloca aquí los PDFs fuente (no versionados)
├── requirements.txt
└── README.md
```

---

## 📋 Leyes disponibles

| Ley | Última reforma | Archivo |
|-----|---------------|---------|
| Ley del Impuesto Sobre la Renta (LISR) | 01-04-2024 | [`leyes/LISR.md`](leyes/LISR.md) |

> ¿Necesitas otra ley? Descarga el PDF de [diputados.gob.mx](https://www.diputados.gob.mx/LeyesBiblio/index.htm), ponlo en `origen-docs/` y corre el script.

---

## 🚀 Uso

### 1. Instalar dependencias

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Convertir un PDF

```bash
# Conversión básica (genera leyes/<nombre>.md automáticamente)
python scripts/pdf_to_md.py origen-docs/LISR.pdf

# Con título personalizado y progreso visible
python scripts/pdf_to_md.py origen-docs/LISR.pdf \
  --title "Ley del Impuesto Sobre la Renta (LISR)" \
  --output leyes/LISR.md \
  --verbose

# Ver ayuda
python scripts/pdf_to_md.py --help
```

### Parámetros disponibles

| Parámetro | Descripción |
|-----------|-------------|
| `pdf` | Ruta al PDF fuente (requerido) |
| `--output`, `-o` | Ruta de salida del `.md` |
| `--title`, `-t` | Título H1 del documento generado |
| `--verbose`, `-v` | Muestra progreso página a página |

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

## 🔧 Cómo funciona el script

1. **Extracción** — usa [`pdfplumber`](https://github.com/jsvine/pdfplumber) para extraer texto con alta fidelidad, respetando tolerancias de caracteres y líneas.
2. **Limpieza** — filtra encabezados repetitivos de cada página y marcadores de paginación (`N de 313`).
3. **Estructuración** — detecta `TÍTULO`, `CAPÍTULO`, `SECCIÓN` y `Artículo N` para asignar niveles de encabezado Markdown.
4. **Unión de líneas** — une líneas de continuación que el PDF partió artificialmente, incluyendo palabras con guión.

---

## 📥 Fuentes de los PDFs

Todos los PDFs deben descargarse directamente de fuentes oficiales:

- **Cámara de Diputados** → [diputados.gob.mx/LeyesBiblio](https://www.diputados.gob.mx/LeyesBiblio/index.htm)
- **DOF (Diario Oficial de la Federación)** → [dof.gob.mx](https://www.dof.gob.mx)

> Los PDFs **no están versionados** en este repositorio por su tamaño y porque cambian con cada reforma. Siempre descarga la versión vigente de la fuente oficial.

---

## 🤝 Contribuir

¿Quieres agregar otra ley? El flujo es simple:

1. Descarga el PDF oficial y ponlo en `origen-docs/`
2. Corre `python scripts/pdf_to_md.py origen-docs/<archivo>.pdf --verbose`
3. Revisa que el Markdown generado sea correcto
4. Abre un PR con el `.md` en `leyes/` y actualiza la tabla en este README

---

## Licencia

MIT — el código es libre. El contenido de las leyes es de dominio público conforme a la legislación mexicana.
