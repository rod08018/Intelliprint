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

import datetime
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

COLGADO_S = 12 * 60
"""Un proyecto vivo escribe algo cada pocos minutos (una ronda tarda ~4).
Si lleva más de esto sin tocar un archivo, algo va mal. Lo que NO sirve es
mirar cuánto lleva en marcha: un mecanismo difícil tarda una hora."""

RECIENTE_S = 30 * 60
"""Una carpeta tocada hace poco puede ser un proyecto en marcha lanzado a
mano, sin job.json. Archivarla le quita la carpeta al proceso mientras
trabaja (pasó de verdad con la leva)."""

DERIVADOS = ("vista.png", "imprimir")
"""Lo que la WEB escribe dentro del proyecto (la vista de las piezas, el
.3mf para PrusaSlicer). No es trabajo del proyecto: contarlo como «tocado
hace poco» hacía que mirar la pieza de calibración la pusiera en marcha y
bloqueara «Diseñar» media hora (2026-10-24)."""

ARTEFACTOS = ("assembly.FCStd", "animation.gif", "review.md", "design_cost.md")


def _lee_json(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


TOLERANCIA_ARRANQUE_S = 120
"""Entre que el JobStore lanza el proceso y apunta la hora pasa un instante;
dos minutos sobran y un pid reutilizado por otro trabajo nunca cae dentro."""


def _vivo(pid: int, inicio: str | None = None) -> bool:
    """Trabajando de verdad, no solo presente en la tabla de procesos.

    Un proceso que terminó y que su padre no ha recogido queda **zombi**, y
    `os.kill(pid, 0)` responde que sí existe: el Geneva drive falló a las
    09:42 y seis horas después el registro seguía diciendo «en marcha».

    Y `os.kill` también acepta el id de un HILO, que `ps -p` no encuentra:
    los job.json guardan pids de otro contenedor, y en el de la web eran
    hilos del propio servidor (2026-10-23, tres proyectos «trabajando» y la
    página sin dejar pedir nada). Sin respuesta de `ps` no hay proceso.

    Ni siquiera un proceso vivo de verdad basta: el pid es el que tuvo en
    SU contenedor, y en otro lo lleva quien sea. El brazo robótico corría
    como pid 8 y tres proyectos de hacía un mes, con `"pid": 8`, salían
    «trabajando» (2026-10-24). Con `inicio`, el proceso tiene que haber
    arrancado cuando arrancó ese trabajo."""
    try:
        os.kill(pid, 0)
    except (OSError, TypeError):
        return False
    salida = subprocess.run(["ps", "-p", str(pid), "-o", "state=,etimes="],
                            capture_output=True, text=True).stdout.split()
    if not salida or salida[0].startswith("Z"):
        return False
    if inicio and len(salida) > 1:
        try:
            lanzado = datetime.datetime.fromisoformat(inicio).timestamp()
            arranco = time.time() - int(salida[1])
        except ValueError:
            return True
        return abs(arranco - lanzado) <= TOLERANCIA_ARRANQUE_S
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
        (f.stat().st_mtime for f in carpeta.rglob("*")
         if f.is_file() and f.relative_to(carpeta).parts[0] not in DERIVADOS), default=0)
    # Sin rounds.json y tocado hace nada: lo más probable es que siga
    # trabajando. Un proyecto terminado no vuelve a "en marcha" por ser reciente.
    # «Tocado hace poco» es para lo lanzado a mano, que no deja job.json.
    # Si lo hay, manda el proceso.
    if trabajo.get("pid"):
        vivo = _vivo(trabajo["pid"], trabajo.get("inicio"))
    else:
        vivo = not rondas and tocado_hace < RECIENTE_S
    if vivo:
        estado = "en marcha"
    elif not rondas:
        estado = "antiguo" if tiene_obra else "incompleto"
    elif motivo:
        estado = "fallido"
    else:
        estado = "aprobado"

    return {
        "id": carpeta.name,
        "segundos_sin_moverse": int(tocado_hace),
        "parece_colgado": estado == "en marcha" and tocado_hace > COLGADO_S,
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
    # Por fecha real: los nombres antiguos no llevan hora y quedarían arriba.
    proyectos = [p for p in carpeta.iterdir() if p.is_dir()]
    return [estado_de(p) for p in sorted(
        proyectos, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)]


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
