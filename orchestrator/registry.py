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

import contextlib
import datetime
import json
import os
import shutil
import subprocess
import threading
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

LATIDO = "latido"
"""El archivo que el proceso de un diseño toca mientras vive. El pid de
job.json solo se puede comprobar desde SU contenedor: Crafty lanza en el
del MCP y la web mira desde el suyo, así que el sargento salía «⚠️
incompleto» mientras el razonador pensaba su primera ronda (2026-10-26).
El latido se ve desde cualquier contenedor que comparta `workspace/`."""

LATIDO_CADA_S = 20
LATIDO_VALE_S = 90
"""Más de cuatro latidos perdidos: el proceso murió sin poder quitar el
archivo (SIGKILL, el contenedor recreado)."""

NO_ES_TRABAJO = (*DERIVADOS, LATIDO)
"""Lo que no cuenta como «tocado hace poco». El latido dice que el proceso
existe, no que avance: contarlo escondería un proyecto colgado."""

ICONOS = {"aprobado": "✅", "con reparos": "🟠", "antiguo": "📦", "fallido": "❌",
          "en marcha": "⏳", "incompleto": "⚠️"}

ARTEFACTOS = ("assembly.FCStd", "animation.gif", "review.md", "design_cost.md")


@contextlib.contextmanager
def latir(carpeta: Path):
    """Mientras dure el `with`, un hilo toca `carpeta/latido` cada
    LATIDO_CADA_S. Al salir lo quita, para que la web no espere LATIDO_VALE_S
    en ver que terminó."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / LATIDO
    parar = threading.Event()

    def _latir():
        while True:
            try:
                archivo.touch()
            except OSError:
                pass   # la carpeta se movió: el diseño fallará por su cuenta
            if parar.wait(LATIDO_CADA_S):
                return

    hilo = threading.Thread(target=_latir, name="latido", daemon=True)
    hilo.start()
    try:
        yield
    finally:
        parar.set()
        hilo.join()
        archivo.unlink(missing_ok=True)


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


def _suspensos_del_revisor(carpeta: Path) -> int:
    """Cuántos requisitos de la petición dice el revisor que NO se cumplen.
    «No verificable» no cuenta: nadie lo comprueba, ni a favor ni en contra."""
    revision = _lee_json(carpeta / "review.json") or {}
    return sum(1 for i in revision.get("items", []) if i.get("verdict") == "no_cumple")


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
         if f.is_file() and f.relative_to(carpeta).parts[0] not in NO_ES_TRABAJO), default=0)
    # Sin rounds.json y tocado hace nada: lo más probable es que siga
    # trabajando. Un proyecto terminado no vuelve a "en marcha" por ser reciente.
    # «Tocado hace poco» es para lo lanzado a mano, que no deja job.json.
    # Si lo hay, manda el proceso: su latido, que se ve desde cualquier
    # contenedor, y si no late (anterior al latido), su pid.
    latido = carpeta / LATIDO
    if latido.exists():
        try:
            vivo = time.time() - latido.stat().st_mtime < LATIDO_VALE_S
        except OSError:   # lo quitó justo ahora: terminó
            vivo = False
    elif trabajo.get("pid"):
        vivo = _vivo(trabajo["pid"], trabajo.get("inicio"))
    else:
        vivo = not rondas and tocado_hace < RECIENTE_S
    if vivo:
        estado = "en marcha"
    elif not rondas:
        estado = "antiguo" if tiene_obra else "incompleto"
    elif motivo:
        estado = "fallido"
    elif suspensos := _suspensos_del_revisor(carpeta):
        # Sin choques es que funciona, no que sea lo pedido: el revisor solo
        # puede devolver el diseño unas pocas veces, y agotadas, el sargento
        # salía ✅ «aprobado» con 11 requisitos del usuario sin cumplir
        # (2026-10-26).
        estado = "con reparos"
        motivo = (f"funciona, pero el revisor encontró {suspensos} "
                  f"requisito{'s' if suspensos > 1 else ''} de la petición sin cumplir")
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


def en_marcha(carpeta: Path) -> str | None:
    """Un proyecto de `carpeta` que sigue trabajando, lo lanzara quien lo
    lanzara: la web, Crafty desde el contenedor del MCP o una consola. Lo que
    ven todos es el workspace, no la memoria de quien pregunta."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return None
    for fila in indice(carpeta):
        if fila["estado"] == "en marcha":
            return fila["id"]
    return None


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
        lineas.append(f"| [{f['id']}]({f['id']}/) | {ICONOS.get(f['estado'], '')} {f['estado']} | "
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
        # Con reparos también se queda: funciona y tiene piezas, es obra.
        if (fila["estado"] in {"aprobado", "con reparos", "antiguo", "en marcha"}
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
