"""Configuración de logging compartida para los scripts del proyecto.

Uso:
    from _log import get_logger
    logger = get_logger(__name__)

    logger.debug("detalle interno")
    logger.info("progreso")
    logger.warning("algo fuera de lo común pero no fatal")
    logger.error("error recuperable")
    logger.exception("error con stacktrace")  # dentro de except

Nivel controlable por la variable de entorno `MX_MD_LOG_LEVEL` (DEBUG, INFO,
WARNING, ERROR, CRITICAL). Default: WARNING — los scripts no producen ruido en
ejecución normal y los mensajes de UX al usuario se mantienen como `print()`.

Todos los logs van a stderr para no contaminar stdout (importante si algún
script en el futuro produce salida estructurada en stdout).
"""

from __future__ import annotations

import logging
import os
import sys

_LEVEL_DEFAULT = "WARNING"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%H:%M:%S"

_configured = False


def _configure_root() -> None:
    """Configura el root logger una sola vez por proceso."""
    global _configured
    if _configured:
        return

    level_name = os.environ.get("MX_MD_LOG_LEVEL", _LEVEL_DEFAULT).upper()
    level = getattr(logging, level_name, logging.WARNING)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))

    root = logging.getLogger()
    root.setLevel(level)
    # Evita duplicados si la raíz ya tenía handlers (p. ej. en tests)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger configurado para el módulo dado."""
    _configure_root()
    return logging.getLogger(name)
