"""
constants.py — Constantes operativas centralizadas para el pipeline mx-md.

Todos los números mágicos y umbrales que afectan el comportamiento de
extracción y conversión viven aquí, con una breve nota del *porqué* de
cada valor. Cambiarlos es decisión deliberada: pueden romper el baseline
de regresión (315/315 leyes byte-a-byte).

Las pruebas de regresión (`shitty/check_regression.sh`) se asumen como la
red de seguridad: cualquier ajuste a estas constantes debe revalidarse.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Logging / progreso
# ---------------------------------------------------------------------------

#: Cada cuántas páginas se loggea progreso al extraer texto de un PDF.
#: Valor pensado para PDFs de varios cientos de páginas (CPEUM, LIGIE):
#: log demasiado frecuente satura `MX_MD_LOG_LEVEL=DEBUG`, demasiado
#: espaciado dificulta diagnosticar dónde se atora el extractor.
PROGRESS_LOG_INTERVAL = 20


# ---------------------------------------------------------------------------
# Detección de tablas-imagen (pdfplumber)
# ---------------------------------------------------------------------------

#: Ancho mínimo (px) para considerar una imagen embebida como tabla-imagen.
#: Valor calibrado contra los PDFs de la Cámara: las tablas-imagen reales
#: superan los 200 px de ancho; logos y separadores quedan por debajo.
IMAGE_TABLE_MIN_WIDTH = 200

#: Alto mínimo (px) equivalente para considerar tabla-imagen.
#: El umbral más permisivo en el alto evita descartar tablas pequeñas
#: (e.g. 5-6 filas) que sí merecen pasar por OCR.
IMAGE_TABLE_MIN_HEIGHT = 100


# ---------------------------------------------------------------------------
# pdfplumber — extracción de texto
# ---------------------------------------------------------------------------

#: Tolerancia horizontal (px) para `extract_text`. Con valores bajos (1-3)
#: pdfplumber respeta mejor la separación entre columnas y evita pegar
#: palabras de filas adyacentes en tablas.
PDFPLUMBER_X_TOLERANCE = 2

#: Tolerancia vertical (px) para `extract_text`. Mismo razonamiento que
#: `PDFPLUMBER_X_TOLERANCE`: 2 px da el balance correcto contra el corpus
#: actual. Subirlo causa "líneas pegadas" en PDFs con interlineado denso.
PDFPLUMBER_Y_TOLERANCE = 2


# ---------------------------------------------------------------------------
# OCR (Tesseract)
# ---------------------------------------------------------------------------

#: Resolución (DPI) al renderizar una región de PDF antes del OCR.
#: 300 DPI es el estándar mínimo recomendado por Tesseract para texto
#: impreso; bajarlo degrada la confianza, subirlo no mejora reconocimiento
#: pero multiplica el tiempo de OCR (cuadrático en DPI).
OCR_RESOLUTION_DPI = 300

#: Idiomas Tesseract para las leyes. Español como primario; inglés como
#: secundario para abreviaturas técnicas (USD, LATAM, FOB, CIF) que
#: aparecen en arancelarias (LIGIE, LFD).
OCR_LANG = "spa+eng"

#: PSM (Page Segmentation Mode) 6 = "bloque de texto uniforme".
#: Valor pensado para tablas-imagen ya recortadas: trata el contenido
#: como un bloque homogéneo en lugar de buscar layout multi-columna.
OCR_PSM_CONFIG = "--psm 6"

#: Confianza mínima Tesseract para aceptar una palabra OCR (`conf >= 1`).
#: Tesseract reporta `-1` para tokens placeholder/invisibles; `1` filtra
#: solo eso, sin descartar palabras de baja confianza que aún pueden ser
#: legítimas (números cortos, símbolos `$`, `%`).
OCR_MIN_CONFIDENCE = 1


# ---------------------------------------------------------------------------
# Reconstrucción de tablas desde datos espaciales OCR
# ---------------------------------------------------------------------------

#: Tolerancia (px) para agrupar palabras OCR en la misma fila por
#: y-center. Calibrado para tablas con interlineado típico de las leyes
#: federales: bajar de 12 px fragmenta filas (palabras de la misma fila
#: caen en buckets distintos), subirlo fusiona filas adyacentes.
OCR_ROW_TOLERANCE = 12

#: Fracción mínima de palabras numéricas en una fila para clasificarla
#: como "fila de datos". Junto con `NUMERIC_ROW_MIN`, separa filas de
#: encabezado (texto) de filas de tabulador (números).
NUMERIC_ROW_FRACTION = 0.5

#: Mínimo absoluto de palabras numéricas en una fila para clasificarla
#: como "fila de datos". Evita falsos positivos en filas cortas (e.g.
#: una fila de 2 columnas con un número y una palabra: 50% sería 1, lo
#: cual no basta).
NUMERIC_ROW_MIN = 2

#: Razón mínima entre el mayor gap vertical y el gap promedio para
#: separar título de encabezados de columna en una tabla OCR.
#: 1.5 = "el corte tiene que ser claramente más amplio que el espaciado
#: regular entre filas pre-tabla". Bajarlo genera falsos cortes; subirlo
#: pierde separaciones reales.
TITLE_HEADER_GAP_RATIO = 1.5

#: Mínimo de letras alfabéticas en una palabra para que su fila cuente
#: como "fila de header real". Filtra ruido OCR (palabras de 1-3 chars
#: que suelen ser artefactos de reconocimiento).
OCR_HEADER_MIN_LETTERS = 4


# ---------------------------------------------------------------------------
# Detección del running header (título repetido en cada página)
# ---------------------------------------------------------------------------

#: Longitud mínima de una línea ALL CAPS para considerarla candidato a
#: running header. Filtra encabezados cortos como "DOF" o "MÉXICO" que
#: pueden aparecer en cualquier ley sin ser su título.
RUNNING_HEADER_MIN_LENGTH = 15

#: Mínimo de repeticiones (en distintas páginas) para confirmar que una
#: línea ALL CAPS es el running header. 3 evita que líneas ALL CAPS
#: legítimas del cuerpo (capítulos, transitorios) sean clasificadas como
#: header repetido.
RUNNING_HEADER_MIN_REPETITIONS = 3


# ---------------------------------------------------------------------------
# Detección de nombres descriptivos (títulos sin numeral)
# ---------------------------------------------------------------------------

#: Longitud máxima general para que una línea sea candidata a "nombre
#: descriptivo". Más allá de 100 chars es párrafo, no título.
DESCRIPTIVE_NAME_MAX_LENGTH = 100

#: Longitud máxima específica para títulos en Title Case con prefijo
#: ("De la...", "Del...", "Sobre..."). Más estricto que el general
#: porque estos prefijos son frecuentes en cuerpo de párrafo también.
DESCRIPTIVE_NAME_TITLE_CASE_MAX_LENGTH = 80


# ---------------------------------------------------------------------------
# download_leyes — red y rate limiting
# ---------------------------------------------------------------------------

#: Timeout (segundos) para fetch del índice HTML de diputados.gob.mx.
#: La página es pequeña (~200 KB) pero el servidor responde lento en
#: horas pico; 30 s da margen sin colgar el script si el sitio cae.
INDEX_FETCH_TIMEOUT_SECS = 30

#: Timeout (segundos) para descargar un PDF individual. Las leyes más
#: grandes (LIGIE ~50 MB) tardan más; 60 s cubre el peor caso observado.
PDF_DOWNLOAD_TIMEOUT_SECS = 60

#: Pausa (segundos) entre descargas consecutivas. Etiqueta de cortesía
#: para el servidor: con 315 leyes a descargar, 0.3 s × 315 ≈ 95 s de
#: overhead total, aceptable. Ráfagas más rápidas pueden disparar
#: throttling del lado de diputados.gob.mx.
BETWEEN_DOWNLOADS_SLEEP_SECS = 0.3


# ---------------------------------------------------------------------------
# Slug y acrónimos
# ---------------------------------------------------------------------------

#: Longitud máxima del slug snake_case del nombre de la ley.
#: 70 chars permite nombres legibles ("ley_general_de_los_derechos...")
#: sin reventar paths en filesystems con límites históricos (255 chars
#: incluyendo prefijo de carpeta + sufijo .pdf/.md).
SLUG_MAX_LENGTH = 70

#: Longitud máxima del acrónimo derivado del nombre de la ley.
#: 8 chars cubre los acrónimos más largos del corpus actual sin
#: convertirse en cadena ilegible (e.g. LFTAIPGMD = 9, ya excede; en
#: ese caso se usa el stem del PDF como abreviatura).
ACRONYM_MAX_LENGTH = 8


# ---------------------------------------------------------------------------
# batch_convert — paralelización
# ---------------------------------------------------------------------------

#: Timeout (segundos) por PDF al invocar `pdf_to_md.py` como subprocess
#: dentro del pool de conversión. 300 s = 5 min cubre LIGIE (la ley más
#: pesada del corpus, ~50 MB con OCR de cientos de tablas) con holgura.
#: Si un PDF excede el timeout, el worker reporta error y el batch
#: continúa con los demás en lugar de colgarse indefinidamente.
BATCH_CONVERT_TIMEOUT_SECS = 300


# ---------------------------------------------------------------------------
# download_leyes — robustez (retry / validación / allowlist / hashing)
# ---------------------------------------------------------------------------

#: Reintentos máximos por PDF ante errores transitorios de red.
#: 3 cubre fallos puntuales (timeout esporádico, 502/503 efímero) sin
#: amplificar la carga sobre diputados.gob.mx si el sitio está caído.
DOWNLOAD_MAX_RETRIES = 3

#: Base (segundos) del backoff exponencial entre reintentos.
#: La espera del intento N es `BASE * 2**N`: 1 s, 2 s, 4 s — total ~7 s
#: en el peor caso, suficiente para superar throttling cortos sin
#: alargar la corrida completa.
DOWNLOAD_BACKOFF_BASE_SECS = 1.0

#: Bytes mágicos que todo PDF válido empieza. Cualquier descarga que
#: no comience con esta secuencia es errónea (página de error HTML,
#: redirect a sitio caído, archivo corrupto) y debe descartarse antes
#: de escribir al disco.
PDF_MAGIC_BYTES = b"%PDF-"

#: Allowlist de hosts permitidos para descargas. Solo aceptamos URLs
#: del sitio oficial de la Cámara de Diputados; cualquier otro host
#: indica un catálogo manipulado o un redirect malicioso. La tupla
#: incluye la variante `www.` porque ambas se ven en el HTML.
ALLOWED_DOWNLOAD_HOSTS = ("diputados.gob.mx", "www.diputados.gob.mx")
