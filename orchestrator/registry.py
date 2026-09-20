"""Registro de proyectos (F5.1 (registro)).

`workspace/projects` se llenó de carpetas mezcladas —pruebas, intentos
fallidos y proyectos buenos— sin forma de saber cuál era cuál. Aquí se
clasifica cada una por lo que hay DENTRO: si terminó sin fallos, si quedó
a medias o si sigue trabajando.

Dos reglas:

- En `projects/` queda solo lo **aprobado**. Lo demás se **mueve** a
  `archivo/`, con todo su contenido: archivar no es borrar.
- El historial de cada proyecto ya está dentro, en `rondas/`: cada ronda
  guarda el mecanismo que propuso el agente. No hace falta un control de
  versiones aparte para saber cómo evolucionó.
"""

import json
import os
import shutil
import time
from pathlib import Path

RECIENTE_S = 30 * 60
"""Una carpeta tocada hace poco puede ser un proyecto en marcha lanzado a
mano, sin job.json. Archivarla le quita la carpeta al proceso mientras
trabaja (pasó de verdad con la leva)."""

ARTEFACTOS = ("assembly.FCStd", "animation.gif", "review.md", "design_cost.md")


def _lee_json(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, TypeError):
        return False
    return True


def estado_de(carpeta: Path) -> dict:
    """Qué es este proyecto, mirando lo que tiene dentro."""
    rondas = _lee_json(carpeta / "rounds.json") or []
    coste = _lee_json(carpeta / "design_cost.json") or {}
    mecanismo = _lee_json(carpeta / "mechanism.json") or {}
    trabajo = _lee_json(carpeta / "job.json") or {}
    peticion = ""
    if (carpeta / "request.md").exists():
        peticion = (carpeta / "request.md").read_text(errors="ignore").strip().splitlines()[0][:60]

    motivo = rondas[-1].get("feedback", "") if rondas else ""
    # Un proyecto anterior al registro (o hecho a mano) no tiene rounds.json,
    # pero si dejó piezas y ensamble es trabajo bueno: no se archiva.
    tiene_obra = ((carpeta / "assembly.FCStd").exists()
                  or any(carpeta.glob("*.FCStd")) or any(carpeta.glob("parts/*/*.step")))
    tocado_hace = time.time() - max(
        (f.stat().st_mtime for f in carpeta.rglob("*") if f.is_file()), default=0)
    # Sin rounds.json y tocado hace nada: lo más probable es que siga
    # trabajando. Un proyecto terminado no vuelve a "en marcha" por ser reciente.
    if (trabajo.get("pid") and _vivo(trabajo["pid"])) or (not rondas and tocado_hace < RECIENTE_S):
        estado = "en marcha"
    elif not rondas:
        estado = "antiguo" if tiene_obra else "incompleto"
    elif motivo:
        estado = "fallido"
    else:
        estado = "aprobado"

    return {
        "id": carpeta.name,
        "titulo": mecanismo.get("title") or peticion or carpeta.name,
        "peticion": peticion,
        "estado": estado,
        "rondas": len(rondas),
        "usd": round(float(coste.get("resumen", {}).get("total_usd", 0.0)), 4),
        "motivo": motivo.strip().splitlines()[0][:120] if motivo else "",
        "archivos": [a for a in ARTEFACTOS if (carpeta / a).exists()],
        "carpeta": str(carpeta),
    }


def indice(carpeta: Path) -> list[dict]:
    """Todos los proyectos, del más reciente al más antiguo."""
    carpeta = Path(carpeta)
    proyectos = [p for p in carpeta.iterdir() if p.is_dir()]
    return [estado_de(p) for p in sorted(proyectos, key=lambda p: p.name, reverse=True)]


def escribir_indice(carpeta: Path) -> Path:
    carpeta = Path(carpeta)
    filas = indice(carpeta)
    total = sum(f["usd"] for f in filas)
    iconos = {"aprobado": "✅", "antiguo": "📦", "fallido": "❌",
              "en marcha": "⏳", "incompleto": "⚠️"}
    lineas = [
        "# Proyectos", "",
        f"{len(filas)} proyectos · {sum(1 for f in filas if f['estado'] == 'aprobado')} aprobados "
        f"· coste total {total:.2f} USD", "",
        "| Proyecto | Estado | Rondas | USD | Qué es | Archivos |",
        "|---|---|---:|---:|---|---|",
    ]
    for f in filas:
        archivos = ", ".join(a.split(".")[0] for a in f["archivos"]) or "—"
        detalle = f["motivo"] or f["peticion"] or f["titulo"]
        lineas.append(f"| [{f['id']}]({f['id']}/) | {iconos.get(f['estado'], '')} {f['estado']} | "
                      f"{f['rondas']} | {f['usd']:.2f} | {detalle} | {archivos} |")
    destino = carpeta / "INDEX.md"
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return destino


def archivar(proyectos: Path, archivo: Path, proteger: set[str] | None = None) -> list[str]:
    """Deja en `proyectos` solo lo aprobado y MUEVE el resto a `archivo`.

    Nunca borra: un intento fallido sigue siendo la única prueba de por qué
    algo no funcionó."""
    proyectos, archivo = Path(proyectos), Path(archivo)
    proteger = proteger or set()
    movidos = []
    for fila in indice(proyectos):
        if (fila["estado"] in {"aprobado", "antiguo", "en marcha"}
                or fila["id"] in proteger):
            continue
        archivo.mkdir(parents=True, exist_ok=True)
        destino = archivo / fila["id"]
        if destino.exists():
            destino = archivo / f"{fila['id']}-{len(movidos) + 1}"
        shutil.move(fila["carpeta"], destino)
        movidos.append(fila["id"])
    escribir_indice(proyectos)
    if movidos:
        escribir_indice(archivo)
    return movidos
