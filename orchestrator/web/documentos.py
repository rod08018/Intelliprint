"""Los documentos de un proyecto, para leerlos en la web (F5.5 (web)).

La pieza de calibración trae en calibracion.md qué es cada agujero y qué
apuntar, y la web no lo enseñaba (2026-10-24). Se pasa a HTML con un
subconjunto pequeño de Markdown —títulos, listas, tablas, código, negrita—
y TODO se escapa antes: un documento lo puede haber escrito un modelo, y
es dato, no HTML.
"""

import html
import re
from pathlib import Path

DOCUMENTOS = {
    "calibracion.md": "Cómo usar esta pieza",
    "blocked.md": "Por qué se detuvo",
    "review.md": "Informe del revisor",
}
"""Qué se enseña y con qué título. Ni request.md (ya va en el detalle) ni
design_cost.md (ya va en la columna de coste)."""


def _en_linea(texto: str) -> str:
    texto = html.escape(texto, quote=False)
    texto = re.sub(r"`([^`]+)`", r"<code>\1</code>", texto)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", texto)


def _celdas(linea: str) -> list[str]:
    return [c.strip() for c in linea.strip().strip("|").split("|")]


def a_html(markdown: str) -> str:
    salida: list[str] = []
    lineas = markdown.splitlines()
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        if linea.startswith("```"):
            bloque = []
            i += 1
            while i < len(lineas) and not lineas[i].startswith("```"):
                bloque.append(lineas[i])
                i += 1
            salida.append(f"<pre>{html.escape(chr(10).join(bloque), quote=False)}</pre>")
        elif m := re.match(r"(#{1,3}) (.*)", linea):
            nivel = len(m.group(1)) + 2   # h3–h5: dentro de una página que ya tiene los suyos
            salida.append(f"<h{nivel}>{_en_linea(m.group(2))}</h{nivel}>")
        elif linea.startswith("|"):
            filas = []
            while i < len(lineas) and lineas[i].startswith("|"):
                if not re.fullmatch(r"\|[\s|:-]+\|?", lineas[i].strip()):
                    filas.append(_celdas(lineas[i]))
                i += 1
            i -= 1
            cabecera, *cuerpo = filas
            salida.append(
                "<table><thead><tr>" + "".join(f"<th>{_en_linea(c)}</th>" for c in cabecera)
                + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f"<td>{_en_linea(c)}</td>" for c in f) + "</tr>"
                          for f in cuerpo)
                + "</tbody></table>")
        elif linea.startswith(("- ", "* ")):
            items = []
            while i < len(lineas) and lineas[i].startswith(("- ", "* ")):
                items.append(f"<li>{_en_linea(lineas[i][2:])}</li>")
                i += 1
            i -= 1
            salida.append("<ul>" + "".join(items) + "</ul>")
        elif linea.strip():
            salida.append(f"<p>{_en_linea(linea)}</p>")
        i += 1
    return "\n".join(salida)


def documentos_de(carpeta: Path) -> list[dict]:
    return [{"archivo": nombre, "titulo": titulo,
             "html": a_html((Path(carpeta) / nombre).read_text(encoding="utf-8", errors="ignore"))}
            for nombre, titulo in DOCUMENTOS.items() if (Path(carpeta) / nombre).is_file()]
