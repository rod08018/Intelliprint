"""Evidencias cuando el sistema se detiene (F3.15 (mecanismos)).

Decir "no pude" no sirve para decidir. Este módulo deja, en la carpeta del
proyecto, qué falla, dónde falla —una imagen de la pose exacta— y cómo fue
evolucionando el fallo ronda a ronda, junto con lo que el agente intentó
en cada una y las opciones reales que tiene la persona.
"""

import re
from pathlib import Path

NUMEROS = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def evolucion(rondas: list[dict]) -> list[float]:
    """El primer número de cada fallo: sirve para ver si se acerca o no."""
    valores = []
    for r in rondas:
        encontrados = NUMEROS.findall(r.get("feedback", "") or "")
        # El primero suele ser el de la pieza o el ángulo; interesa la medida.
        medidas = [float(x.replace(",", ".")) for x in encontrados]
        if medidas:
            valores.append(medidas[-1] if len(medidas) == 1 else medidas[-1])
    return valores


def render_frame(meshes, poses, out: Path, *, title: str = "",
                 resaltar: set[str] | None = None, view=(30, -55)) -> Path:
    """Dibuja UNA pose y la guarda como imagen. Las piezas de `resaltar` van
    en rojo: son las que chocan o no llegan."""
    from orchestrator.animation import COLOR_EJE, COLORES, render_gif

    colores = {n: ("#d7263d" if resaltar and n in resaltar else COLORES.get(n, COLOR_EJE))
               for n in meshes}
    out = Path(out)
    gif = render_gif(meshes, [(0, poses)], out.with_suffix(".gif"),
                     title=title, colors=colores, label=lambda t: "", view=view)
    from PIL import Image

    with Image.open(gif) as img:
        img.convert("RGB").save(out)
    Path(gif).unlink(missing_ok=True)
    return out


def _opciones(parada: str, mejora: str) -> list[str]:
    if parada == "presupuesto":
        return [
            "**Subir el tope** de gasto en `config/models.yaml` (`max_usd_per_project`) y seguir "
            "desde donde se quedó, con `--continuar`.",
            "Dejarlo aquí y revisar el último diseño: puede estar cerca.",
        ]
    comunes = [
        "**Simplificar el requisito** que lo bloquea (menos carrera, más holgura, "
        "menos piezas) y volver a pedirlo.",
        "**Dar una pista concreta** en la petición: qué solución mecánica quieres "
        "(muelle de lámina en vez de helicoidal, tope en la base en vez de en el brazo…).",
        "**Seguir intentando** con `--continuar`: parte del último diseño y de este fallo.",
    ]
    if mejora == "acercándose":
        return ["**Seguir intentando**: cada ronda se acercaba, puede salir con unas pocas más "
                "(`--continuar`)."] + comunes[:2]
    return comunes


def escribir_bloqueo(carpeta: Path, *, titulo: str, parada: str, rondas: list[dict],
                     gasto_usd: float, imagenes: list[str], peticion: str,
                     planes: list[dict] | None = None) -> Path:
    """Escribe `blocked.md`: el parte para la persona."""
    carpeta = Path(carpeta)
    valores = evolucion(rondas)
    if len(valores) >= 2 and valores[-1] < valores[0]:
        mejora = "acercándose"
        frase = (f"El fallo fue mejorando: de {valores[0]:g} a {valores[-1]:g} "
                 "entre la primera y la última ronda.")
    elif len(valores) >= 2:
        frase = "El fallo **no mejoró** entre rondas: el diseño no avanzaba."
        mejora = "sin avanzar"
    else:
        frase, mejora = "", "desconocida"

    ultimo = next((r.get("feedback", "") for r in reversed(rondas) if r.get("feedback")), "")
    motivo = {
        "atascado": "se **atascó**: el mismo fallo se repetía y el diseño no avanzaba",
        "presupuesto": f"se acabó el **presupuesto** del proyecto ({gasto_usd:.2f} USD)",
        "rondas": "se alcanzó el límite de rondas",
    }.get(parada, parada)

    lineas = [
        f"# {titulo}: hace falta que decidas", "",
        f"Intelliprint {motivo} tras **{len(rondas)} rondas** y **{gasto_usd:.2f} USD**.", "",
        f"**Estado:** {parada}", "",
        "## Lo que pediste", "", f"> {peticion.strip().splitlines()[0][:300]}", "",
        "## Qué falla", "", "```", ultimo.strip()[:1200], "```", "",
    ]
    if frase:
        lineas += [frase, ""]
    if imagenes:
        lineas += ["## Dónde falla", ""]
        lineas += [f"![{Path(i).stem}]({i})" for i in imagenes]
        lineas += ["", "En rojo, las piezas implicadas.", ""]
    if planes:
        lineas += ["## Qué intentó", "",
                   "| Ronda | Causa que supuso | Qué cambió |", "|---:|---|---|"]
        lineas += [f"| {p['ronda']} | {p.get('causa', '')} | {p.get('cambio', '')} |"
                   for p in planes]
        lineas += [""]
    lineas += ["## Qué puedes hacer", ""]
    lineas += [f"{i}. {o}" for i, o in enumerate(_opciones(parada, mejora), start=1)]
    lineas += ["", "El último diseño completo está en `mechanism.json`, y cada intento en "
               "`rondas/`. El ensamble y la animación son del último que se pudo montar.", ""]

    destino = carpeta / "blocked.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return destino
