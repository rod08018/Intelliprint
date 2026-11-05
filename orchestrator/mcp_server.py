"""Servidor MCP de Intelliprint (F5.6 (telegram)).

Es la puerta por la que Crafty —el agente de OpenClaw que habla contigo en
Telegram— usa el sistema. OpenClaw pone la conversación; Intelliprint pone
el diseño. Esa separación es la de § 8.5: el canal es transporte, no un
agente del grafo.

Cada herramienta devuelve datos, nunca instrucciones. Lo que llegue por el
canal es una petición de diseño y nada más: aquí no hay ninguna forma de
ejecutar código arbitrario.

Se arranca solo (lo lanza OpenClaw por stdio):
    intelliprint-mcp
"""

import os
import sys
from pathlib import Path

from mcp.server import MCPServer

from orchestrator.jobs import JobStore
from orchestrator.registry import estado_de, indice

mcp = MCPServer(
    "intelliprint",
    instructions=(
        "Diseño de mecanismos imprimibles en 3D. `disenar_mecanismo` tarda "
        "minutos y trabaja en segundo plano: no esperes, pregunta el estado."
    ),
)


def _raiz() -> Path:
    for carpeta in [Path.cwd(), *Path.cwd().parents]:
        if (carpeta / "config" / "models.yaml").exists():
            return carpeta
    sys.exit("ejecuta intelliprint-mcp dentro del repo de Intelliprint")


def _proyectos() -> Path:
    raiz = _raiz()
    workspace = Path(os.environ.get("INTELLIPRINT_WORKSPACE") or raiz / "workspace")
    return workspace / "projects"


_STORE: JobStore | None = None


def _store() -> JobStore:
    """El gestor de trabajos, UNO para todo el servidor. Se creaba uno nuevo
    en cada llamada, con la lista de procesos vacía: «uno a la vez» nunca
    saltaba y cancelar no paraba nada. Así salieron dos sargentos a la vez
    (2026-10-26)."""
    global _STORE
    if _STORE is None:
        raiz = _raiz()
        ejecutable = raiz / ".venv" / "bin" / "intelliprint"
        comando = [str(ejecutable) if ejecutable.exists() else "intelliprint", "mecanismo"]
        _STORE = JobStore(_proyectos(), comando)
    return _STORE


def _orden_pieza() -> list[str]:
    """La orden de una pieza suelta (F5.17 (pieza)), con el mismo ejecutable
    que la de mecanismos."""
    ejecutable = _raiz() / ".venv" / "bin" / "intelliprint"
    return [str(ejecutable) if ejecutable.exists() else "intelliprint", "pieza"]


def _investigador():
    """El mismo buscador que usa una pieza antes de los requisitos
    (F3.21 (investigar)): la búsqueda de DeepSeek, con la clave de los agentes."""
    from orchestrator.cli import _cliente
    from orchestrator.investigar import BuscadorDeepSeek, Investigador
    from orchestrator.llm.router import Router

    env = dict(os.environ)
    router = Router.from_config_file(_raiz() / "config" / "models.yaml", env=env)
    return Investigador(_cliente(router, env), BuscadorDeepSeek(env["DEEPSEEK_API_KEY"]),
                        prompt_path=_raiz() / "config" / "agents" / "investigador.md",
                        log=lambda *_: None)


@mcp.tool()
def buscar_medidas(que: str) -> dict:
    """Busca en internet las medidas de un componente o pieza comprada (una
    placa, un motor, un servo, un perfil, una tuerca) y las devuelve con su
    fuente y una cita literal de la página, comprobada por el código.

    Úsalo cuando el usuario pregunte por medidas o nombre algo sin medirlo.
    NO hace falta antes de `disenar_pieza`: la pieza busca sola lo que falte
    y lo enseña en el concepto. Devuelve `texto`, listo para enseñar; dile
    siempre que lo compruebe con un calibre.

    Fallo que lo motivó (2026-11-05): con su propio buscador, Crafty puso los
    USB de la Raspberry Pi 4 en el borde equivocado y nadie lo comprobó.
    """
    r = _investigador().medidas_de(que)
    return {"datos": [d.model_dump() for d in r.datos], "sin_encontrar": r.sin_encontrar,
            "texto": r.texto_para_concepto() or "No encontré esas medidas."}


@mcp.tool()
def disenar_pieza(peticion: str) -> dict:
    """Diseña UNA pieza que no se mueve —un soporte, un gancho, una escuadra,
    un adaptador, un clip— y la construye y lamina.

    Para piezas sueltas. Si lo que pide tiene partes que se mueven entre sí
    (bisagras, trinquetes, prensas), es `disenar_mecanismo`.

    Devuelve el identificador al momento. Primero el ingeniero propone CÓMO
    resolverlo y para: `estado_proyecto` dirá «por aprobar» y traerá el
    `concepto`. Enséñaselo al usuario y pasa su respuesta a
    `aprobar_concepto`. Hasta entonces no se modela nada.

    La petición tiene que llevar TODAS las medidas que dio el usuario, tal
    cual: qué sujeta, a qué se atornilla, diámetros y separaciones de
    agujeros, carga.
    """
    store = _store()
    try:
        job = store.start(peticion, comando=_orden_pieza())
    except RuntimeError as e:
        return {"error": str(e), "en_marcha": store.current()}
    return {"proyecto": job,
            "aviso": "Diseñando la pieza. Tarda unos minutos; pregunta el estado de vez en cuando."}


@mcp.tool()
def disenar_mecanismo(peticion: str, referencias: list[str] | None = None) -> dict:
    """Diseña un mecanismo a partir de una petición en texto y lo verifica.

    Tarda varios minutos: devuelve al momento el identificador del proyecto
    y sigue trabajando por su cuenta. Consulta `estado_proyecto` para saber
    cómo va y `archivos_proyecto` cuando termine.

    La petición debe describir el mecanismo con todo lo que el usuario haya
    dicho: qué tiene que hacer, medidas, límites de movimiento y qué piezas
    exige. Cuanto más completa, menos rondas de corrección.

    `referencias` (opcional): lo que el usuario mandó como ejemplo de algo
    que YA funciona. Rutas de imágenes (jpg, png, webp) o textos (md, txt,
    json) que te llegaron por Telegram, o el id de un proyecto que ya salió.
    Pásalas siempre que el usuario mande fotos o diga «como el de antes».
    """
    from orchestrator.mechanisms.referencias import ReferenciaInvalida, desde_el_entorno

    referencias = [r for r in referencias or [] if r and r.strip()]
    # Antes de lanzar: si una referencia no vale, hay que saberlo ya, no diez
    # minutos después en el registro de un trabajo que murió al arrancar.
    try:
        desde_el_entorno(referencias, _proyectos().parent, os.environ)
    except ReferenciaInvalida as e:
        return {"error": f"referencia no válida: {e}"}
    store = _store()
    try:
        job = store.start(peticion, referencias=referencias)
    except RuntimeError as e:
        return {"error": str(e), "en_marcha": store.current()}
    return {
        "proyecto": job,
        "aviso": "Diseñando. Cada ronda tarda unos 4 minutos y sigue hasta que funciona, "
                 "se atasca o llega al tope de gasto. Pregunta el estado de vez en cuando; "
                 "no te quedes esperando.",
    }


@mcp.tool()
def estado_proyecto(proyecto: str = "") -> dict:
    """Cómo va un proyecto: si sigue trabajando, en qué ronda y lo último
    que hizo. Sin argumento, el más reciente.

    Mira el workspace entero, no solo lo que se lanzó desde aquí: un
    proyecto arrancado por consola cuenta igual."""
    carpeta = _proyectos() / proyecto if proyecto else None
    if carpeta is None:
        filas = indice(_proyectos())
        if not filas:
            return {"estado": "no hay proyectos todavía"}
        carpeta = Path(filas[0]["carpeta"])
    if not carpeta.exists():
        return {"error": f"no existe el proyecto {proyecto!r}"}
    from orchestrator.web.versiones import raices

    estado = estado_de(carpeta)
    # De qué encargo es versión: Crafty habla de proyectos, no de carpetas.
    estado["proyecto"] = raices(_proyectos().parent).get(carpeta.name, carpeta.name)
    if estado["estado"] == "por aprobar" and (carpeta / "concepto.md").exists():
        # F3.20 (concepto): lo que Crafty tiene que enseñar, y esperar.
        estado["concepto"] = (carpeta / "concepto.md").read_text(encoding="utf-8", errors="ignore")
    registro = carpeta / "run.log"
    if registro.exists():
        estado["ultimo"] = "\n".join(
            registro.read_text(errors="ignore").strip().splitlines()[-12:])
    return estado


@mcp.tool()
def archivos_proyecto(proyecto: str = "") -> dict:
    """Archivos del proyecto, ya copiados donde el canal puede leerlos:
    `animacion` (el GIF del movimiento, lo PRIMERO que hay que mandar),
    `ensamble` (.FCStd para abrir en FreeCAD), `revision` y `coste`.

    Si no aparece `animacion`, el proyecto todavía no la generó: dilo en vez
    de mandar otra cosa en su lugar."""
    from orchestrator.jobs import entregar

    carpeta = _proyectos() / proyecto if proyecto else None
    if carpeta is None:
        filas = indice(_proyectos())
        if not filas:
            return {"error": "no hay proyectos todavía"}
        carpeta = Path(filas[0]["carpeta"])
    if not carpeta.exists():
        return {"error": f"no existe el proyecto {proyecto!r}"}
    archivos = entregar(carpeta)
    if "animacion" not in archivos:
        archivos["aviso"] = ("este proyecto todavía no tiene animación; "
                             "no mandes otro archivo como si lo fuera")
    return archivos


@mcp.tool()
def listar_proyectos(limite: int = 10) -> list[dict]:
    """Los proyectos más recientes, cada uno con sus versiones. Un proyecto
    es un encargo; cada vez que se rediseña o se modifica, una versión más.

    `proyecto` es el id con el que se nombra el encargo; `mejor`, la versión
    que hay que enseñar; `en_marcha`, la que está trabajando si hay alguna."""
    from orchestrator.web.versiones import proyectos

    resumen = []
    for g in proyectos(_proyectos().parent)[:limite]:
        resumen.append({
            "proyecto": g["id"],
            "nombre": g.get("titulo"),
            "estado": "en marcha" if g.get("en_marcha") else g["estado"],
            "motivo": g.get("motivo", ""),
            "mejor": g["mejor"],
            "en_marcha": g.get("en_marcha"),
            "usd_total": g.get("usd_total", 0),
            "versiones": [{"id": v["id"], "version": v["version"], "estado": v["estado"],
                           "motivo": v.get("motivo", ""), "modificacion": v.get("modificacion"),
                           "usd": (v.get("coste") or {}).get("usd", 0)}
                          for v in g["versiones"]],
        })
    return resumen


@mcp.tool()
def modificar_proyecto(proyecto: str, cambio: str, pieza: str = "") -> dict:
    """Cambia algo de un proyecto que ya existe: crea una VERSIÓN nueva del
    mismo proyecto partiendo de su mejor versión (o de la versión que
    nombres). Úsalo para toda corrección, cambio o reintento de un encargo;
    `disenar_mecanismo` es solo para encargos nuevos.

    `cambio`: lo que el usuario quiere distinto, con sus palabras y medidas.
    `pieza` (opcional): si el cambio es de una sola pieza, su nombre; las
    demás se quedan como están."""
    from orchestrator.web.versiones import (
        ProyectoDesconocido, lanzar_modificacion, proyectos, resolver_proyecto)

    if not cambio.strip():
        return {"error": "di qué hay que cambiar"}
    workspace = _proyectos().parent
    try:
        base = resolver_proyecto(proyecto, workspace)
    except ProyectoDesconocido:
        return {"error": f"no existe el proyecto {proyecto!r}; búscalo con listar_proyectos"}
    # Nombrado el encargo, se parte de su mejor versión, no de la primera.
    grupo = next((g for g in proyectos(workspace) if g["id"] == base.name), None)
    if grupo:
        base = resolver_proyecto(grupo["mejor"], workspace)
    store = _store()
    try:
        r = lanzar_modificacion(store, workspace, base, cambio, pieza=pieza,
                                orden_pieza=_orden_pieza())
    except RuntimeError as e:
        return {"error": str(e), "en_marcha": store.current()}
    except ValueError as e:   # una pieza que no existe
        return {"error": str(e)}
    return {"proyecto": r["proyecto"], "version": r["id"], "basado_en": base.name,
            "aviso": "Versión nueva en marcha. Pregunta el estado de vez en cuando."}


@mcp.tool()
def continuar_proyecto(proyecto: str = "") -> dict:
    """Sigue intentando un proyecto que no quedó resuelto, partiendo de su
    último diseño y del motivo por el que falló (no empieza de cero).
    Sin argumento, el más reciente."""
    store = _store()
    if not proyecto:
        proyectos = store.list(1)
        if not proyectos:
            return {"error": "no hay proyectos todavía"}
        proyecto = proyectos[0]["id"]
    try:
        store.resume(proyecto)
    except (KeyError, RuntimeError) as e:
        return {"error": str(e)}
    return {"proyecto": proyecto, "aviso": "Reintentando desde el último diseño."}


@mcp.tool()
def aprobar_concepto(proyecto: str, respuestas: str = "") -> dict:
    """El visto bueno del usuario al concepto de una pieza «por aprobar».

    Sin `respuestas`: el usuario aprueba la idea tal cual y se modela.
    Con `respuestas`: lo que contestó a las preguntas del ingeniero, o lo
    que quiere cambiar de la idea, con SUS palabras. NO aprueba: el
    ingeniero propone otro concepto, que vuelve a esperar. Llámalo solo
    cuando el usuario haya dicho que sí, o con lo que haya contestado."""
    store = _store()
    try:
        store.aprobar(proyecto, respuestas=respuestas, por="telegram")
    except (KeyError, ValueError, RuntimeError) as e:
        return {"error": str(e)}
    if respuestas.strip():
        return {"proyecto": proyecto,
                "aviso": "El ingeniero rehace el concepto con lo que has dicho."}
    return {"proyecto": proyecto, "aviso": "Aprobado: diseñando la pieza. Tarda unos minutos."}


@mcp.tool()
def ordenar_proyectos(archivar_fallidos: bool = False) -> dict:
    """Índice de los proyectos del workspace: qué es cada uno, si quedó
    aprobado o falló, cuántas rondas costó y cuánto se gastó. Con
    `archivar_fallidos`, mueve lo no aprobado a `archivo/` (no borra nada)."""
    from orchestrator.registry import archivar, escribir_indice, indice

    raiz = _raiz()
    workspace = Path(os.environ.get("INTELLIPRINT_WORKSPACE") or raiz / "workspace")
    proyectos = workspace / "projects"
    movidos = archivar(proyectos, workspace / "archivo") if archivar_fallidos else []
    return {"indice": str(escribir_indice(proyectos)), "archivados": movidos,
            "proyectos": indice(proyectos)}


@mcp.tool()
def cancelar_proyecto(proyecto: str) -> dict:
    """Detiene un proyecto en marcha."""
    store = _store()
    store.cancel(proyecto)
    return store.status(proyecto)


def opciones_de_arranque(env) -> tuple[str, dict]:
    """Cómo servir: por stdio (lo lanza OpenClaw como subproceso, uso
    nativo) o por HTTP a la red del compose (F0.2 (docker)).

    En contenedores Crafty no puede lanzarlo: el binario, FreeCAD y el
    modelo están en la imagen del orquestador, no en la de OpenClaw.
    """
    if env.get("INTELLIPRINT_MCP_TRANSPORT") != "streamable-http":
        return "stdio", {}
    from mcp.server.transport_security import TransportSecuritySettings

    puerto = int(env.get("INTELLIPRINT_MCP_PORT") or 8200)
    return "streamable-http", {
        "host": "0.0.0.0",
        "port": puerto,
        # El servidor valida la cabecera Host contra el rebinding de DNS.
        # Crafty llega como `intelliprint-mcp:<puerto>`; sin nombrarlo aquí,
        # cada llamada daría 421 y el error no diría por qué.
        "transport_security": TransportSecuritySettings(
            allowed_hosts=[f"intelliprint-mcp:{puerto}", f"localhost:{puerto}",
                           f"127.0.0.1:{puerto}"],
            allowed_origins=["*"],
        ),
    }


def main() -> None:
    transporte, opciones = opciones_de_arranque(os.environ)
    mcp.run(transporte, **opciones)


if __name__ == "__main__":
    main()
