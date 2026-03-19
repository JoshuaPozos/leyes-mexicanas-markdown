# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.

## [Lote 4 — Leyes 034-043] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 034 | LCJPJF | Ley de Carrera Judicial del Poder Judicial de la Federación |
| 035 | LCE | Ley de Comercio Exterior |
| 036 | LCM | Ley de Concursos Mercantiles |
| 037 | LCMOPFIH | Ley de Contribución de Mejoras por Obras Públicas Federales de Infraestructura Hidráulica |
| 038 | LCID | Ley de Cooperación Internacional para el Desarrollo |
| 039 | LCF | Ley de Coordinación Fiscal |
| 040 | LDRS | Ley de Desarrollo Rural Sustentable |
| 041 | LDSC | Ley de Desarrollo Sustentable de la Cafeticultura |
| 042 | LDSCA | Ley de Desarrollo Sustentable de la Caña de Azúcar |
| 043 | LDEFAGN | Ley de Disciplina del Ejército, Fuerza Aérea y Guardia Nacional |

---

## [Lote 3 — Leyes 024-033] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 024 | LASoc | Ley de Asistencia Social |
| 025 | LAPP | Ley de Asociaciones Público Privadas |
| 026 | LARCP | Ley de Asociaciones Religiosas y Culto Público |
| 027 | LAC | Ley de Aviación Civil |
| 028 | LAAT | Ley de Ayuda Alimentaria para los Trabajadores |
| 029 | LBio | Ley de Biocombustibles |
| 030 | LBOGM | Ley de Bioseguridad de Organismos Genéticamente Modificados |
| 031 | LCEC | Ley de Cámaras Empresariales y sus Confederaciones |
| 032 | LCPAF | Ley de Caminos, Puentes y Autotransporte Federal |
| 033 | LCP | Ley de Capitalización del PROCAMPO |

### Corregido (calidad)
- `compute_md_slug` ahora elimina sufijos numéricos de fecha en nombres de PDF (ej. `LCEC_120419` → `LCEC`). Afecta a ~34 leyes del catálogo completo.

---

## [Lote 2 — Leyes 014-023] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 014 | LAgra | Ley Agraria |
| 015 | LAASSP | Ley de Adquisiciones, Arrendamientos y Servicios del Sector Público |
| 016 | LAero | Ley de Aeropuertos |
| 017 | LAN | Ley de Aguas Nacionales |
| 018 | LACP | Ley de Ahorro y Crédito Popular |
| 019 | LAmn | Ley de Amnistía (DOF 22/01/2021) |
| 020 | LA | Ley de Amnistía (Sin reforma — versión anterior) |
| 021 | LAmp | Ley de Amparo, Reglamentaria de los artículos 103 y 107 de la Constitución |
| 022 | LAAM | Ley de Ascensos de la Armada de México |
| 023 | LAREFAGN | Ley de Ascensos y Recompensas del Ejército, Fuerza Aérea y Guardia Nacional |

### Cambiado (calidad del repo)
- `gen_indice.py` ahora incluye fecha de actualización y porcentaje de avance en el encabezado de `INDICE.md`.
- `README.md` actualizado: sección de estructura con convención de nombres correcta, nueva sección de **Progreso** con estado de lotes.

---

## [Lote 1 — Leyes 001-013 + LISR] — 2026-03-18

### Leyes publicadas (14)
| No. | Clave | Ley |
|-----|-------|-----|
| 001 | CPEUM | Constitución Política de los Estados Unidos Mexicanos |
| 002 | CCF | Código Civil Federal |
| 003 | CCom | Código de Comercio |
| 004 | CJM | Código de Justicia Militar |
| 005 | CFPC | Código Federal de Procedimientos Civiles |
| 006 | CFF | Código Fiscal de la Federación |
| 007 | CMPP | Código Militar de Procedimientos Penales |
| 008 | CNPCF | Código Nacional de Procedimientos Civiles y Familiares |
| 009 | CNPP | Código Nacional de Procedimientos Penales |
| 010 | CPF | Código Penal Federal |
| 011 | EGDF | Estatuto de Gobierno del Distrito Federal |
| 012 | ISEDIPL | Impuesto sobre Servicios Expresamente Declarados de Interés Público por Ley |
| 013 | LAdua | Ley Aduanera |
| 114 | LISR | Ley del Impuesto sobre la Renta |

### Corregido
- Convención de nombres: `{ABREV}_{nombre_en_snake_case}.md` aplicada consistently a todos los archivos.
- `derive_acronym` ahora trunca el nombre en la primera coma o paréntesis y limita el acrónimo a 8 caracteres para evitar nombres excesivamente largos.

## [0.2.0] — 2026-03-18

### Agregado
- `scripts/download_leyes.py` — Scraper que parsea la tabla de diputados.gob.mx y descarga los 315+ PDFs de leyes federales vigentes.
- `scripts/batch_convert.py` — Conversión en batch de todos los PDFs en `origen-docs/` a Markdown.
- `scripts/gen_indice.py` — Genera `INDICE.md` con tabla navegable y links a cada `.md` disponible.
- `INDICE.md` — Índice autogenerado de las 315 leyes con links a los Markdowns disponibles.
- `catalogo.json` — Catálogo estructurado (autogenerado) con metadata de cada ley.

### Cambiado
- Carpeta `leyes/` renombrada a `markdown/` para mayor claridad.
- `scripts/pdf_to_md.py` ahora genera output en `markdown/` por defecto.
- `README.md` reescrito para reflejar el alcance completo del proyecto (315+ leyes federales).

## [0.1.0] — 2026-03-18

### Agregado
- `scripts/pdf_to_md.py` — Script de conversión de PDF a Markdown estructurado.
- `markdown/LISR.md` — Ley del Impuesto Sobre la Renta convertida a Markdown.
- `README.md` inicial.
- `requirements.txt` con dependencia de `pdfplumber`.
- `.gitignore` configurado para excluir PDFs, venv y archivos de sistema.
