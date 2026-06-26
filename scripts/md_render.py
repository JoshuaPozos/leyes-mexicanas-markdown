#!/usr/bin/env python3
"""md_render.py — Renderiza un AST canónico (JSON) a líneas de Markdown.

El AST es la fuente de verdad; el Markdown es una de sus vistas. Extraído de
`pdf_to_md.py` (Sprint 3.1 — modularización); `pdf_to_md` re-exporta estas
funciones, así que la salida es byte-idéntica y la API pública no cambia.
"""

import re


def render_markdown(ast: dict) -> list[str]:
    """
    Renderiza un AST canónico (JSON) a líneas de Markdown.
    El AST es la fuente de verdad; el Markdown es una de sus vistas.
    """
    lines: list[str] = []

    # Encabezado meta
    name = ast.get("name", "")
    lines.extend([
        f"# {name}",
        "",
        "> Documento generado automáticamente a partir del PDF oficial.",
        "> Fuente: Cámara de Diputados del H. Congreso de la Unión — [diputados.gob.mx](https://www.diputados.gob.mx)",
        "",
        "---",
        "",
    ])

    # Preámbulo
    _render_content(ast.get("preamble", []), lines)

    # Estructura
    for node in ast.get("structure", []):
        _render_node(node, lines)

    return lines


def _render_content(elements: list[dict], lines: list[str]) -> None:
    """Renderiza elementos de contenido (párrafos, fracciones, etc.) a Markdown."""
    for i, elem in enumerate(elements):
        t = elem.get("type", "")
        if t == "paragraph":
            lines.append(elem.get("text", ""))
        elif t == "fraccion":
            if i > 0:
                lines.append("")
            lines.append(f"{elem['ordinal']}. {elem.get('text', '')}")
        elif t == "inciso":
            if i > 0:
                lines.append("")
            lines.append(f"{elem['ordinal']}) {elem.get('text', '')}")
        elif t == "reform_note":
            lines.append(elem.get("text", ""))
        elif t == "table":
            _render_table(elem, lines)


def _render_table(table: dict, lines: list[str]) -> None:
    """Renderiza un nodo tabla a formato Markdown."""
    title = table.get("title")
    headers = table.get("headers", [])
    rows = table.get("rows", [])
    lines.append("")
    if title:
        lines.append(f"**{title}**")
    if headers:
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
    lines.append("")


def _render_node(node: dict, lines: list[str]) -> None:
    """Renderiza un nodo estructural del AST a Markdown."""
    ntype = node.get("type", "")
    heading = node.get("heading", "")
    descriptor = node.get("descriptor")
    content = list(node.get("content", []))
    children = node.get("children", [])

    if ntype in ("titulo", "capitulo", "seccion", "transitorios"):
        h = heading
        if descriptor:
            h += f" — {descriptor}"
        lines.append("")
        lines.append(f"## {h}")
        lines.append("")

    elif ntype == "articulo":
        lines.append("")
        lines.append(f"### {heading}")

    elif ntype == "transitorio_articulo":
        ordinal = node.get("ordinal", "") or heading
        if re.match(r'(?:ARTÍCULO|Artículo)\s', heading or ordinal):
            lines.append("")
            lines.append(f"### {heading}")
        else:
            # Ordinal transitorio: **Ordinal.-** texto
            if content and content[0].get("type") == "paragraph":
                lines.append(f"**{ordinal}.-** {content[0]['text']}")
                content = content[1:]
            else:
                lines.append(f"**{ordinal}.-**")

    _render_content(content, lines)

    for child in children:
        _render_node(child, lines)
