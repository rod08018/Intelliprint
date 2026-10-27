"""Interfaz web: pedir un diseño, ver los proyectos con sus versiones,
pedir modificaciones, bajarlos en zip y abrirlos en PrusaSlicer (F5.5 (web)).

Corre dentro del contenedor y se abre desde el navegador del PC. Es el
subconjunto de F5.5 (web) que hacía falta ya —encontrar un proyecto, llevárselo,
mirarlo en PrusaSlicer—; los botones de los gates llegan con ellos.

El identificador de un proyecto viene de la URL, es decir, lo escribe
quien quiera. Se trata como texto ajeno: un nombre, nunca una ruta.

    docker compose up -d web      ->  http://localhost:8080
"""

import json
import io
import os
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field, field_validator

from orchestrator.impresion import perfil_activo
from orchestrator.proyecto_3mf import Pieza, escribir_3mf
from orchestrator.slicing import UsoDesconocido, ajustes_de_uso
from orchestrator.hostpaths import RutaFueraDelWorkspace, a_ruta_del_host
from orchestrator.jobs import JobStore
from orchestrator.registry import en_marcha, estado_de
from orchestrator.web.documentos import documentos_de
from orchestrator.web.estadisticas import estadisticas
from orchestrator.categorias import CATEGORIAS
from orchestrator.web import paginas
from orchestrator.web.versiones import (  # noqa: F401 (los tests los importan de aquí)
    ProyectoDesconocido, agrupar, ejecuciones, lanzar_modificacion, marca_de,
    piezas_de, raices, resolver_proyecto)


def empaquetar(carpeta: Path) -> bytes:
    """El proyecto en un zip, dentro de una carpeta con su nombre.

    Sin el `.git` interno (F1.15 (versionado)): es el historial del sistema,
    no el diseño, y solo engorda la descarga.
    """
    carpeta = Path(carpeta)
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(carpeta.rglob("*")):
            relativa = f.relative_to(carpeta)
            if ".git" in relativa.parts or not f.is_file():
                continue
            z.write(f, f"{carpeta.name}/{relativa.as_posix()}")
    return memoria.getvalue()


def usos_de(carpeta: Path) -> dict[str, str]:
    """El uso que el diseñador declaró para cada pieza (F3.16 (usos)). Se lee
    el JSON a pelo: un mechanism.json anterior a los usos no lo trae, y no
    por eso deja de valer. Sin uso, «general»."""
    try:
        spec = json.loads((Path(carpeta) / "mechanism.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {p["name"]: p.get("uso") or "general" for p in spec.get("parts", []) if "name" in p}


def piezas_con_uso(carpeta: Path) -> list[dict]:
    usos = usos_de(carpeta)
    return [{"nombre": stl.stem, "uso": usos.get(stl.stem, "general")} for stl in piezas_de(carpeta)]


class Modificacion(BaseModel):
    peticion: str = Field(max_length=20_000)
    pieza: str = Field(default="", max_length=200)
    """Si el cambio es de una sola pieza, cuál: las demás no se tocan."""

    @field_validator("peticion")
    @classmethod
    def _con_texto(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("escribe qué quieres que diseñe o que cambie")
        return v.strip()


class Categoria(BaseModel):
    categoria: str

    @field_validator("categoria")
    @classmethod
    def _de_la_lista(cls, v: str) -> str:
        if v not in CATEGORIAS:
            raise ValueError("elige una de: " + ", ".join(CATEGORIAS))
        return v


class Pedido(Modificacion):
    basado_en: str | None = None


def crear_app(workspace: Path, puente=None, host_workspace: str = "",
              trabajos: JobStore | None = None, raiz: Path = Path(".")) -> FastAPI:
    """La aplicación. `puente` es la URL del MCP del host, o en los tests el
    propio servidor; None si no hay puente configurado. `trabajos` lanza los
    diseños que se piden desde la página; None si esta web no puede. `raiz`
    es donde está config/, para leer el perfil activo."""
    app = FastAPI(title="Intelliprint", docs_url=None, redoc_url=None)
    perfil = perfil_activo(raiz).laminado
    app.state.trabajos = trabajos
    workspace = Path(workspace)

    def _proyecto(id: str) -> Path:
        try:
            return resolver_proyecto(id, workspace)
        except ProyectoDesconocido:
            raise HTTPException(404, f"no hay ningún proyecto llamado {id!r}")

    @app.post("/api/disenar")
    def disenar(pedido: Pedido) -> dict:
        if trabajos is None:
            raise HTTPException(503, "esta web no tiene con qué lanzar diseños")
        referencias = [_proyecto(pedido.basado_en).name] if pedido.basado_en else []
        otro = trabajos.current() or en_marcha(workspace / "projects")
        if otro:
            raise HTTPException(
                409, f"ya hay un proyecto en marcha ({otro}); espera a que termine")
        try:
            return {"id": trabajos.start(pedido.peticion, referencias=referencias)}
        except RuntimeError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/proyectos/{id}/modificar")
    def modificar(id: str, pedido: Modificacion) -> dict:
        """Una versión nueva del proyecto de `id`, partiendo de `id`.

        Antes, cambiar algo era pedir un diseño nuevo «partiendo de» otro, y
        cada intento salía como un proyecto más en la lista."""
        if trabajos is None:
            raise HTTPException(503, "esta web no tiene con qué lanzar diseños")
        base = _proyecto(id)
        otro = trabajos.current() or en_marcha(workspace / "projects")
        if otro:
            raise HTTPException(
                409, f"ya hay un proyecto en marcha ({otro}); espera a que termine")
        try:
            return lanzar_modificacion(trabajos, workspace, base, pedido.peticion,
                                       pieza=pedido.pieza)
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        except ValueError as e:   # una pieza que no existe
            raise HTTPException(422, str(e))

    @app.get("/api/proyectos")
    def proyectos() -> list[dict]:
        return agrupar(ejecuciones(workspace), workspace)

    @app.get("/api/proyectos/{id}")
    def detalle(id: str) -> dict:
        """Una VERSIÓN: el id es el de su carpeta."""
        carpeta = _proyecto(id)
        en_marcha = estado_de(carpeta)["estado"] == "en marcha"
        peticion = ((carpeta / "request.md").read_text(encoding="utf-8", errors="ignore").strip()
                    if (carpeta / "request.md").is_file() else "")
        return {"id": carpeta.name, "peticion": peticion,
                "modificacion": marca_de(carpeta).get("modificacion"),
                "piezas": piezas_con_uso(carpeta),
                "es_mecanismo": (carpeta / "mechanism.json").is_file(),
                "vista": bool(piezas_de(carpeta)),
                "documentos": documentos_de(carpeta),
                **estadisticas(carpeta, en_marcha=en_marcha)}

    @app.get("/proyectos/{id}/vista.png")
    def vista(id: str) -> FileResponse:
        """Las piezas dibujadas, para lo que no tiene animación. Se guarda en
        el proyecto y solo se redibuja si alguna STL es más nueva."""
        carpeta = _proyecto(id)
        piezas = piezas_de(carpeta)
        if not piezas:
            raise HTTPException(404, "este proyecto no tiene piezas construidas")
        png = carpeta / "vista.png"
        if not png.is_file() or png.stat().st_mtime < max(p.stat().st_mtime for p in piezas):
            from orchestrator.vista import dibujar_piezas
            try:
                dibujar_piezas(piezas, png)
            except ValueError as e:
                raise HTTPException(409, str(e))
        return FileResponse(png, media_type="image/png")

    @app.get("/proyectos/{id}/animation.gif")
    def animacion(id: str) -> FileResponse:
        gif = _proyecto(id) / "animation.gif"
        if not gif.is_file():
            raise HTTPException(404, "este proyecto todavía no tiene animación")
        return FileResponse(gif, media_type="image/gif")

    @app.get("/proyectos/{id}.zip")
    def bajar(id: str) -> Response:
        carpeta = _proyecto(id)
        return Response(
            empaquetar(carpeta), media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{carpeta.name}.zip"'},
        )

    @app.post("/proyectos/{id}/abrir")
    def abrir(id: str) -> dict:
        carpeta = _proyecto(id)
        piezas = piezas_de(carpeta)
        if not piezas:
            raise HTTPException(409, "este proyecto no tiene ninguna pieza construida")
        if puente is None:
            raise HTTPException(
                503, "no hay puente con el PrusaSlicer del PC. Arráncalo en el "
                "host con: powershell scripts\\start-host-mcps.ps1")

        from orchestrator.mcp.client import ClienteMCP, LlamadaFallida, PuenteInalcanzable
        # Un proyecto .3mf con cada pieza y los ajustes de su uso: con las
        # STL sueltas, el gatillo que aguanta un resorte se laminaría como
        # la tapa (F3.16 (usos)).
        catalogo = Path(raiz) / "config" / "slicing"
        usos = usos_de(carpeta)
        try:
            proyecto = escribir_3mf(
                [Pieza(p.stem, p, ajustes_de_uso(usos.get(p.stem, "general"), catalogo))
                 for p in piezas],
                catalogo / perfil, carpeta / "imprimir" / f"{carpeta.name}.3mf")
        except (UsoDesconocido, ValueError) as e:
            raise HTTPException(409, f"no se pudo preparar el proyecto para PrusaSlicer: {e}")
        try:
            stls = [a_ruta_del_host(proyecto.as_posix(), workspace.as_posix(), host_workspace)]
        except RutaFueraDelWorkspace as e:
            raise HTTPException(500, str(e))
        try:
            respuesta = ClienteMCP(puente, timeout=60).llamar(
                "abrir_en_prusaslicer", stls=stls, perfil=perfil)
        except PuenteInalcanzable as e:
            raise HTTPException(
                503, f"el puente del PC no contesta ({e}). ¿Está arrancado? "
                "powershell scripts\\start-host-mcps.ps1")
        except LlamadaFallida as e:
            raise HTTPException(502, str(e))
        if not respuesta.get("ok"):
            raise HTTPException(502, respuesta.get("error") or "PrusaSlicer no se abrió")
        return {**respuesta, "abiertas": len(piezas)}

    @app.get("/", response_class=HTMLResponse)
    def portada() -> str:
        return paginas.galeria(agrupar(ejecuciones(workspace), workspace), workspace,
                               hay_puente=puente is not None, puede_pedir=trabajos is not None)

    @app.get("/p/{id}", response_class=HTMLResponse)
    def pagina_de_proyecto(id: str, v: str | None = None) -> str:
        """Un proyecto con sus versiones. `id` puede ser el del proyecto o el
        de cualquiera de sus versiones; `v` elige cuál se enseña."""
        _proyecto(id)
        grupos = agrupar(ejecuciones(workspace), workspace)
        g = next((g for g in grupos if g["id"] == id or any(x["id"] == id for x in g["versiones"])),
                 None)
        if g is None:
            raise HTTPException(404, f"no hay ningún proyecto llamado {id!r}")
        elegida = v or (id if id != g["id"] else None)
        ocupado = bool((trabajos.current() if trabajos else None) or en_marcha(workspace / "projects"))
        return paginas.proyecto(g, elegida, workspace, hay_puente=puente is not None,
                                puede_pedir=trabajos is not None, ocupado=ocupado)

    @app.get("/proyectos/{id}/piezas/{nombre}.png")
    def vista_de_pieza(id: str, nombre: str) -> FileResponse:
        """Una pieza sola, para su tarjeta. Se guarda en `vistas/` —que no
        cuenta como trabajo del proyecto— y se redibuja si la STL es nueva."""
        carpeta = _proyecto(id)
        stl = next((p for p in piezas_de(carpeta) if p.stem == nombre), None)
        if stl is None:
            raise HTTPException(404, f"este proyecto no tiene ninguna pieza {nombre!r}")
        png = carpeta / "vistas" / f"{stl.stem}.png"
        if not png.is_file() or png.stat().st_mtime < stl.stat().st_mtime:
            from orchestrator.vista import dibujar_piezas
            png.parent.mkdir(exist_ok=True)
            try:
                dibujar_piezas([stl], png)
            except ValueError as e:
                raise HTTPException(409, str(e))
        return FileResponse(png, media_type="image/png")

    @app.post("/api/proyectos/{id}/categoria")
    def cambiar_categoria(id: str, pedido: Categoria) -> dict:
        _proyecto(id)
        raiz = raices(workspace).get(id, id)
        paginas.fijar_categoria(workspace, raiz, pedido.categoria)
        return {"proyecto": raiz, "categoria": pedido.categoria}

    return app


def main() -> None:
    """Arranque dentro del contenedor."""
    import uvicorn

    workspace = Path(os.environ.get("INTELLIPRINT_WORKSPACE") or "workspace")
    app = crear_app(
        workspace,
        puente=os.environ.get("PRUSASLICER_BRIDGE") or None,
        host_workspace=os.environ.get("HOST_WORKSPACE", ""),
        # La misma orden que lanza Crafty (mcp_server._store).
        trabajos=JobStore(workspace / "projects", ["intelliprint", "mecanismo"]),
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("WEB_PORT", "8080")))


if __name__ == "__main__":
    main()
