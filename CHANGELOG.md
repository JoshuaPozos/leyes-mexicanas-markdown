# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.

## [Fix 11 — Headers de tablas OCR reconstruidos] — 2026-03-21

- `_build_table_from_spatial()` reescrito: separación título/headers/datos usando gap vertical
- `assign_to_columns()`: cambiado de closest-center a column boundaries (punto medio entre centros)
- `_assign_header_row()`: filas de header con texto en 1-2 columnas adyacentes se fusionan correctamente
- Detección de filas de unidades (`$ $ $ %`) e incorporación al nombre de columna
- Filtro de ruido OCR en filas de header (requiere al menos una palabra de ≥4 letras)
- **Resultado:** Headers genéricos `| $ | $ | $ | % |` → `| Limite inferior ($) | Limite superior ($) | Cuota fija ($) | Por ciento para... (%) |`
- Todos los 315 `.md` regenerados

## [Fix 10 — Falsos positivos en headings de artículos] — 2026-03-21

- `is_article_heading()`: eliminado `re.IGNORECASE` — solo reconoce "Artículo" con A mayúscula
- `ARTICLE_ORDINAL_RE`: cambiado a match explícito "ARTÍCULO|Artículo" sin IGNORECASE
- `split_article_heading()`: eliminado `re.IGNORECASE` para consistencia
- Guardia de contexto en `build_markdown()`: si el buffer termina con preposición ("el", "del", "al", etc.), el "Artículo N" se une como texto, no como heading
- **Resultado:** 1 762 falsos positivos → 0 en los 315 archivos
- Todos los 315 `.md` regenerados

## [Lote 14 — Leyes 295-315] — 2026-03-21

### Leyes publicadas (21) — Catálogo completo 315/315 🎉
| No. | Clave | Ley |
|-----|-------|-----|
| 295 | LRFVACGR | Ley Reglamentaria de la Fracción V del Artículo 76 de la Constitución |
| 296 | LRArt76 | Ley Reglamentaria de la fracción VI del artículo 76 de la Constitución |
| 297 | LRFXIIIB | Ley Reglamentaria de la Fracción XIII Bis del Apartado B, del Artículo 123 |
| 298 | LRFXAC | Ley Reglamentaria de la Fracción XVIII del Artículo 73 Constitucional |
| 299 | LRFIyII | Ley Reglamentaria de las Fracciones I y II del Artículo 105 |
| 300 | LRACMN | Ley Reglamentaria del Artículo 27 Constitucional en Materia Nuclear |
| 301 | LRArt3 | Ley Reglamentaria del Artículo 3o. de la Constitución |
| 302 | LRAC | Ley Reglamentaria del Artículo 5o. Constitucional |
| 303 | LRArt6 | Ley Reglamentaria del artículo 6o. de la Constitución |
| 304 | LRSF | Ley Reglamentaria del Servicio Ferroviario |
| 305 | LCA | Ley sobre Cámaras Agrícolas |
| 306 | LCS | Ley Sobre el Contrato de Seguro |
| 307 | LEBHN | Ley sobre el Escudo, la Bandera y el Himno Nacionales |
| 308 | LATIME | Ley Sobre la Aprobación de Tratados Internacionales en Materia Económica |
| 309 | LSCT | Ley sobre la Celebración de Tratados |
| 310 | LRPCAP | Ley sobre Refugiados, Protección Complementaria y Asilo Político |
| 311 | OGA | Ordenanza General de la Armada |
| 312 | PEF | Presupuesto de Egresos de la Federación para el Ejercicio Fiscal 2026 |
| 313 | Reg_Diputados | Reglamento de la Cámara de Diputados |
| 314 | Reg_Senado | Reglamento del Senado de la República |
| 315 | RGICGEUM | Reglamento para el Gobierno Interior del Congreso General |

---

## [Lote 13 — Leyes 250-294] — 2026-03-21

### Leyes publicadas (45)
Leyes orgánicas (LOAM, LOPDC, LOPGJDF, LOUAAAN, LOUAM, LOUNAM, LOTA, LONF, LOSHF, LOBB, LOBNCE, LOBNOSP, LOBNE, LOCFCRL, LOCGEUM, LOEFAM, LOINAH, LOIPN, LOPJF, LOSCM, LOTFJA), leyes para conservar/determinar/impulsar (LCNP, LDVUMA, LDCMPME, LD, LUPDECR, LIISPCEN, LC, LCACSEFAM, LPPDDHP, LTPCPIMCP, LTOSF), leyes para regular (LRASCAP, LRAF, LRITF, LRSIC), leyes que aprueban/crean/declaran/establecen (LAAMCCBD, LCFGFA, LCINBAL, LAEM, LCUAC, LCUEFA, LDRMNYU, LCCAIF, LEBEM).

---

## [Lotes 10-12 — Leyes 115-249] — 2026-03-21

### Leyes publicadas (135)
Incluye: leyes del instituto (LISSFAM, LISSSTE, LIFNVT, LIFNCT, LIMJ, LINPI), leyes del mercado/sector (LMV, LSE, LSH, LSS, LSM, LSPM), leyes del servicio (LSAT, LSEM, LSPCAPF), leyes del sistema (LSNIEG, LSNIIMSP, LSPREM), ley en materia de telecomunicaciones (LMTR), leyes federales contra/de/del/para (LFCDO…LFMZAAH — 48 leyes), leyes generales (LGAMVLV…LGPSDMS — 58 leyes), leyes nacionales (LMEUM…LNUF — 8 leyes), ley orgánica APF (LOAPF).

---

## [Fix Issues 6-9 — OCR y mejoras] — 2026-03-19

### Correcciones aplicadas
| # | Issue | Resultado |
|---|-------|-----------|
| 6 | Nombres descriptivos de sección sin formato | Ahora se añaden como `— NOMBRE` al heading |
| 7 | Fracciones romanas (I., II., XVI.) pegadas sin separar | Ahora en párrafos separados |
| 8 | Sub-incisos a), b), c) pegados inline | Ahora en párrafos separados |
| 9 | Tablas-imagen sin contenido (placeholder) | OCR con Tesseract: extracción real de tablas |

---

## [Lote 9 — Leyes 084-113] — 2026-03-19

### Leyes publicadas (30)
| No. | Clave | Ley |
|-----|-------|-----|
| 084 | LNCM | Ley de Navegación y Comercio Marítimos |
| 085 | LOPSRM | Ley de Obras Públicas y Servicios Relacionados con las Mismas |
| 086 | LOG | Ley de Organizaciones Ganaderas |
| 087 | LPlan | Ley de Planeación |
| 088 | LPTE | Ley de Planeación y Transición Energética |
| 089 | LPERC | Ley de Premios, Estímulos y Recompensas Civiles |
| 090 | LPO | Ley de Productos Orgánicos |
| 091 | LPAB | Ley de Protección al Ahorro Bancario |
| 092 | LPCINECD | Ley de Protección al Comercio y la Inversión de Normas Extranjeras |
| 093 | LPEAM | Ley de Protección del Espacio Aéreo Mexicano |
| 094 | LPDUSF | Ley de Protección y Defensa al Usuario de Servicios Financieros |
| 095 | LP | Ley de Puertos |
| 096 | LRAM | Ley de Recompensas de la Armada de México |
| 097 | LRCDN | Ley de Responsabilidad Civil por Daños Nucleares |
| 098 | LSInt | Ley de Seguridad Interior |
| 099 | LSN | Ley de Seguridad Nacional |
| 100 | LSP | Ley de Sistemas de Pagos |
| 101 | LSRLIP | Ley de Sociedades de Responsabilidad Limitada de Interés Público |
| 102 | LSSS | Ley de Sociedades de Solidaridad Social |
| 103 | LTF | Ley de Tesorería de la Federación |
| 104 | LTFCCG | Ley de Transparencia y de Fomento a la Competencia en el Crédito Garantizado |
| 105 | LUC | Ley de Uniones de Crédito |
| 106 | LVZMM | Ley de Vertimientos en las Zonas Marinas Mexicanas |
| 107 | LVGC | Ley de Vías Generales de Comunicación |
| 108 | LViv | Ley de Vivienda |
| 109 | LBM | Ley del Banco de México |
| 110 | LDOFGG | Ley del Diario Oficial de la Federación y Gacetas Gubernamentales |
| 111 | LFMPED | Ley del Fondo Mexicano del Petróleo para la Estabilización y el Desarrollo |
| 112 | LIVA | Ley del Impuesto al Valor Agregado |
| 113 | LIEPS | Ley del Impuesto Especial sobre Producción y Servicios |

A partir del lote 9 los lotes son de 30 leyes.

## [Fix TODOS — Mejoras pdf_to_md.py] — 2026-03-19

### Correcciones aplicadas al script de conversión (5 fixes)
| # | Issue | Resultado |
|---|-------|-----------|
| 1 | Falso positivo `##` en "título de...", "sección de...", "capítulo de..." | 17 → 0 instancias |
| 2 | Running header del PDF embebido en texto (80/84 archivos) | Eliminado en todos |
| 3 | "Transitorios" sin formato heading | Ahora `## Transitorios` (74 archivos) |
| 4 | "ARTÍCULO TERCERO A ARTÍCULO DÉCIMO" sin heading | Ahora `### ARTÍCULO...` (58 archivos) |
| 5 | Ordinales ("Primero.", "Segundo.") sin negritas | Ahora `**Primero.-**` (77 archivos) |

**Se reconvirtieron los 84 archivos existentes con el script mejorado.**

## [Lote 8 — Leyes 074-083] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 074 | LGN | Ley de la Guardia Nacional |
| 075 | LPF | Ley de la Policía Federal |
| 076 | LDPAM | Ley de los Derechos de las Personas Adultas Mayores |
| 077 | LHHEUM | Ley de los Husos Horarios en los Estados Unidos Mexicanos |
| 078 | LIGIE | Ley de los Impuestos Generales de Importación y de Exportación |
| 079 | LINS | Ley de los Institutos Nacionales de Salud |
| 080 | LSAR | Ley de los Sistemas de Ahorro para el Retiro |
| 081 | LMigra | Ley de Migración |
| 082 | LMin | Ley de Minería |
| 083 | LN | Ley de Nacionalidad |

> A partir del lote 9 los lotes son de 15 leyes.

---

## [Lote 7 — Leyes 064-073] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 064 | LIE | Ley de Inversión Extranjera |
| 065 | LANSI | Ley de la Agencia Nacional de Seguridad Industrial y de Protección al Medio Ambiente del Sector Hidrocarburos |
| 066 | LCMM | Ley de la Casa de Moneda de México |
| 067 | LCNBV | Ley de la Comisión Nacional Bancaria y de Valores |
| 068 | LCNE | Ley de la Comisión Nacional de Energía |
| 069 | LCNDH | Ley de la Comisión Nacional de los Derechos Humanos |
| 070 | LESS | Ley de la Economía Social y Solidaria |
| 071 | LEPECFE | Ley de la Empresa Pública del Estado Comisión Federal de Electricidad |
| 072 | LEPEPM | Ley de la Empresa Pública del Estado Petróleos Mexicanos |
| 073 | LFGR | Ley de la Fiscalía General de la República |

---

## [Lote 6 — Leyes 054-063] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 054 | LFIV | Ley de Fomento a la Industria Vitivinícola |
| 055 | LFLL | Ley de Fomento para la Lectura y el Libro |
| 056 | LFAAR | Ley de Fondos de Aseguramiento Agropecuario y Rural |
| 057 | LFI | Ley de Fondos de Inversión |
| 058 | LGeo | Ley de Geotermia |
| 059 | LICal | Ley de Infraestructura de la Calidad |
| 060 | LIF | Ley de Ingresos de la Federación para el Ejercicio Fiscal 2026 |
| 061 | LIH | Ley de Ingresos sobre Hidrocarburos |
| 062 | LIC | Ley de Instituciones de Crédito |
| 063 | LISF | Ley de Instituciones de Seguros y de Fianzas |

---

## [Lote 5 — Leyes 044-053] — 2026-03-18

### Leyes publicadas (10)
| No. | Clave | Ley |
|-----|-------|-----|
| 044 | LDFEFM | Ley de Disciplina Financiera de las Entidades Federativas y los Municipios |
| 045 | LDPAM | Ley de Disciplina para el Personal de la Armada de México |
| 046 | LEMEFAGN | Ley de Educación Militar del Ejército, Fuerza Aérea y Guardia Nacional |
| 047 | LEN | Ley de Educación Naval |
| 048 | LEC | Ley de Energía para el Campo |
| 049 | LE | Ley de Expropiación |
| 050 | LEI | Ley de Extradición Internacional |
| 051 | LFEA | Ley de Firma Electrónica Avanzada |
| 052 | LFRCF | Ley de Fiscalización y Rendición de Cuentas de la Federación |
| 053 | LFCC | Ley de Fomento a la Confianza Ciudadana |

---

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
