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
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
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
    ProyectoDesconocido, agrupar, corridas_del_banco, ejecuciones, lanzar_modificacion,
    marca_de, piezas_de, raices, resolver_proyecto)


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


class VistoBueno(BaseModel):
    respuestas: str = Field(default="", max_length=2000)
    """Vacío: se aprueba el concepto. Con texto: son las respuestas a las
    preguntas del ingeniero, y vuelve a proponer (F3.20 (concepto))."""


class Lista(BaseModel):
    nota: str = Field(default="", max_length=500)


class Rehacer(BaseModel):
    cambio: str = Field(default="", max_length=2000)
    desde_cero: bool = False
    """Sin esto, una pieza ya construida se corrige partiendo de ella."""


class Pedido(Modificacion):
    basado_en: str | None = None
    tipo: Literal["pieza", "mecanismo", "obra"]
    """F5.17 (pieza): una pieza suelta no pasa por el flujo de mecanismos,
    que exige dos piezas como mínimo. Obligatorio: con «mecanismo» por
    omisión, una página abierta antes del selector mandó el soporte de la
    Raspberry al flujo viejo de recetas (2026-11-04)."""


ESTATICOS = ("three.module.min.js", "OrbitControls.js")
"""Lo único que sirve `/estatico/`: ver `estatico/README.md`."""


def crear_app(workspace: Path, puente=None, host_workspace: str = "",
              trabajos: JobStore | None = None, raiz: Path = Path("."),
              orden_pieza: list[str] | None = None,
              orden_obra: list[str] | None = None) -> FastAPI:
    """La aplicación. `puente` es la URL del MCP del host, o en los tests el
    propio servidor; None si no hay puente configurado. `trabajos` lanza los
    diseños que se piden desde la página; None si esta web no puede. `raiz`
    es donde está config/, para leer el perfil activo."""
    app = FastAPI(title="Intelliprint", docs_url=None, redoc_url=None)
    perfil = perfil_activo(raiz).laminado
    app.state.trabajos = trabajos
    workspace = Path(workspace)

    def _proyecto(id: str, banco: bool = False) -> Path:
        """`banco`: también los proyectos del banco, que se miran y se bajan
        pero no se tocan; las rutas que cambian algo no lo pasan."""
        try:
            return resolver_proyecto(id, workspace, banco=banco)
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
            comando = {"pieza": orden_pieza, "obra": orden_obra}.get(pedido.tipo)
            if pedido.tipo != "mecanismo" and not comando:
                raise HTTPException(503, f"esta web no tiene con qué diseñar «{pedido.tipo}»")
            return {"id": trabajos.start(pedido.peticion, referencias=referencias,
                                         comando=comando)}
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
                                       pieza=pedido.pieza, orden_pieza=orden_pieza)
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        except ValueError as e:   # una pieza que no existe
            raise HTTPException(422, str(e))

    @app.post("/api/proyectos/{id}/aprobar")
    def aprobar(id: str, visto: VistoBueno) -> dict:
        """El visto bueno al concepto del ingeniero, o las respuestas a sus
        preguntas. Es la barrera humana antes de gastar en modelar."""
        if trabajos is None:
            raise HTTPException(503, "esta web no tiene con qué lanzar diseños")
        carpeta = _proyecto(id)
        if carpeta.parent != trabajos.carpeta:
            raise HTTPException(409, "solo se aprueban conceptos de proyectos en curso")
        otro = trabajos.current()
        if otro:
            raise HTTPException(409, f"ya hay un proyecto en marcha ({otro}); espera a que termine")
        try:
            return {"id": trabajos.aprobar(carpeta.name, respuestas=visto.respuestas, por="web")}
        except ValueError as e:     # no hay concepto que aprobar
            raise HTTPException(409, str(e))
        except RuntimeError as e:
            raise HTTPException(409, str(e))

    # --- La obra, nodo a nodo (F7.3 (arbol)) ------------------------------------

    def _obra_en_curso(id: str) -> Path:
        from orchestrator import obra
        if trabajos is None:
            raise HTTPException(503, "esta web no tiene con qué lanzar diseños")
        carpeta = _proyecto(id)
        if carpeta.parent != trabajos.carpeta or not obra.es_obra(carpeta):
            raise HTTPException(409, f"{id} no es un proyecto por partes en curso")
        return carpeta

    def _nodo(carpeta: Path, nodo: str) -> str:
        from orchestrator import obra
        try:
            return obra.cargar_obra(carpeta).nodo(nodo).id
        except KeyError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/proyectos/{id}/nodos/{nodo}/lista")
    def dar_por_lista(id: str, nodo: str) -> dict:
        """«Está bien, la siguiente»: congela la pieza, la ficha y sigue."""
        carpeta = _obra_en_curso(id)
        try:
            trabajos.dar_por_lista(carpeta.name, _nodo(carpeta, nodo), por="web")
        except (ValueError, RuntimeError) as e:
            raise HTTPException(409, str(e))
        return {"id": carpeta.name, "nodo": nodo}

    @app.post("/api/proyectos/{id}/seguir")
    def seguir(id: str) -> dict:
        """Lanza lo siguiente de la obra si no espera a nadie."""
        carpeta = _obra_en_curso(id)
        try:
            trabajos.seguir(carpeta.name)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(409, str(e))
        return {"id": carpeta.name}

    @app.post("/api/proyectos/{id}/nodos/{nodo}/impresa")
    def marcar_impresa(id: str, nodo: str, pedido: Lista) -> dict:
        """La prueba física: se apunta y no relanza nada."""
        from orchestrator import obra
        carpeta = _obra_en_curso(id)
        try:
            obra.marcar_impresa(carpeta, _nodo(carpeta, nodo), nota=pedido.nota)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"id": carpeta.name, "nodo": nodo}

    @app.post("/api/proyectos/{id}/nodos/{nodo}/rehacer")
    def rehacer(id: str, nodo: str, pedido: Rehacer) -> dict:
        carpeta = _obra_en_curso(id)
        try:
            rehechos = trabajos.rehacer(carpeta.name, _nodo(carpeta, nodo), cambio=pedido.cambio,
                                        desde_cero=pedido.desde_cero)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(409, str(e))
        return {"id": carpeta.name, "rehechos": rehechos}

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
        carpeta = _proyecto(id, banco=True)
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
        gif = _proyecto(id, banco=True) / "animation.gif"
        if not gif.is_file():
            raise HTTPException(404, "este proyecto todavía no tiene animación")
        return FileResponse(gif, media_type="image/gif")

    @app.get("/proyectos/{id}/nodos/{nodo}/animation.gif")
    def animacion_de_nodo(id: str, nodo: str) -> FileResponse:
        """La de un conjunto de la obra, en su tarjeta (F7.6 (animacion))."""
        from orchestrator import obra
        carpeta = _proyecto(id, banco=True)
        try:
            nodo = obra.cargar_obra(carpeta).nodo(nodo).id   # un id del árbol, no una ruta
        except (KeyError, OSError, ValueError):
            raise HTTPException(404, f"este proyecto no tiene ningún conjunto {nodo!r}")
        gif = carpeta / obra.NODOS / nodo / "animation.gif"
        if not gif.is_file():
            raise HTTPException(404, "este conjunto todavía no tiene animación")
        return FileResponse(gif, media_type="image/gif")

    @app.get("/estatico/{nombre}")
    def estatico(nombre: str) -> FileResponse:
        """three.js para el visor (F7.9 (visor)), desde la propia web: corre
        en la red de casa y tiene que funcionar sin internet."""
        if nombre not in ESTATICOS:
            raise HTTPException(404, "no existe")
        return FileResponse(Path(__file__).parent / "estatico" / nombre,
                            media_type="text/javascript",
                            headers={"Cache-Control": "public, max-age=86400"})

    def _conjunto(id: str, nodo: str) -> tuple[Path, str]:
        from orchestrator import obra
        carpeta = _proyecto(id, banco=True)
        try:
            nodo = obra.cargar_obra(carpeta).nodo(nodo).id   # un id del árbol, no una ruta
        except (KeyError, OSError, ValueError):
            raise HTTPException(404, f"este proyecto no tiene ningún conjunto {nodo!r}")
        return carpeta, nodo

    @app.get("/proyectos/{id}/nodos/{nodo}/ensamble.json")
    def ensamble(id: str, nodo: str) -> FileResponse:
        """Las mallas del visor 3D (F7.9 (visor)), las que dejó la verificación."""
        from orchestrator import obra
        from orchestrator.conjunto import ENSAMBLE
        carpeta, nodo = _conjunto(id, nodo)
        ruta = carpeta / obra.NODOS / nodo / ENSAMBLE
        if not ruta.is_file():
            raise HTTPException(404, "este conjunto todavía no tiene ensamble para el visor")
        return FileResponse(ruta, media_type="application/json")

    @app.get("/proyectos/{id}/nodos/{nodo}/tornillos")
    def tornillos_del_conjunto(id: str, nodo: str) -> list[dict]:
        """Cada tornillo del conjunto, en el marco de la pieza donde apoya
        su cabeza, para que el visor lo dibuje y se mueva con ella."""
        from orchestrator.tornilleria import tornillos
        carpeta, nodo = _conjunto(id, nodo)
        return [t.para_el_visor() for t in tornillos(carpeta, nodo)]

    @app.get("/proyectos/{id}/nodos/{nodo}/poses")
    def poses_del_conjunto(id: str, nodo: str, request: Request) -> dict:
        """Cada pieza en su sitio con las articulaciones a los ángulos que se
        piden (`?soporte=90`), y lo que choca ahí. Lo calcula Python con la
        cinemática con la que se barrieron los choques: el navegador solo
        dibuja."""
        from orchestrator import obra
        from orchestrator.conjunto import VERIFICACION, pose_para_el_visor
        carpeta, nodo = _conjunto(id, nodo)
        if not (carpeta / obra.NODOS / nodo / VERIFICACION).is_file():
            raise HTTPException(404, "este conjunto todavía no se ha movido")
        try:
            angulos = {k: float(v) for k, v in request.query_params.items()}
        except ValueError:
            raise HTTPException(422, "cada ángulo es un número de grados")
        from orchestrator.estudio import en_la_pose
        pose = pose_para_el_visor(carpeta, nodo, angulos)
        # F7.10 (estudio): el par de cada servo y el vuelco en esa pose.
        pose["estudio"] = en_la_pose(carpeta, nodo, pose["angulos"])
        return pose

    @app.get("/proyectos/{id}/nodos/{nodo}/alcance.png")
    def alcance_del_conjunto(id: str, nodo: str) -> Response:
        """Planta y alzado del recorrido del punto de carga (F7.10 (estudio))."""
        from orchestrator import obra
        from orchestrator.estudio import ESTUDIO, dibujo_del_alcance
        carpeta, nodo = _conjunto(id, nodo)
        ruta = carpeta / obra.NODOS / nodo / ESTUDIO
        if not ruta.is_file():
            raise HTTPException(404, "este conjunto todavía no tiene estudio de movimientos")
        e = json.loads(ruta.read_text(encoding="utf-8"))
        return Response(dibujo_del_alcance(e), media_type="image/png")

    @app.get("/banco", response_class=HTMLResponse)
    def banco() -> str:
        return paginas.banco(corridas_del_banco(workspace), hay_puente=puente is not None)

    @app.get("/proyectos/{id}.zip")
    def bajar(id: str) -> Response:
        carpeta = _proyecto(id, banco=True)
        return Response(
            empaquetar(carpeta), media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{carpeta.name}.zip"'},
        )

    @app.post("/proyectos/{id}/abrir")
    def abrir(id: str, nodo: str | None = None) -> dict:
        """`nodo`: solo las piezas de ese nodo de una obra, para imprimirlo y
        probarlo antes de seguir con la siguiente."""
        carpeta = _proyecto(id, banco=True)
        piezas = piezas_de(carpeta)
        if nodo:
            piezas = [p for p in piezas if p.parent.parent.parent.name == nodo
                      and p.parent.parent.parent.parent.name == "nodos"]
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
        carpeta = _proyecto(id, banco=True)
        partes = carpeta.relative_to(workspace).parts
        del_banco = partes[1] if partes[0] == "banco" else ""   # la corrida
        grupos = agrupar(ejecuciones(workspace, banco=bool(del_banco)), workspace)
        g = next((g for g in grupos if g["id"] == id or any(x["id"] == id for x in g["versiones"])),
                 None)
        if g is None:
            raise HTTPException(404, f"no hay ningún proyecto llamado {id!r}")
        elegida = v or (id if id != g["id"] else None)
        ocupado = bool((trabajos.current() if trabajos else None) or en_marcha(workspace / "projects"))
        # Lo del banco se mira: sin botones que lancen nada.
        return paginas.proyecto(g, elegida, workspace, hay_puente=puente is not None,
                                puede_pedir=trabajos is not None and not del_banco,
                                ocupado=ocupado, del_banco=del_banco)

    @app.get("/proyectos/{id}/piezas/{nombre}.png")
    def vista_de_pieza(id: str, nombre: str) -> FileResponse:
        """Una pieza sola, para su tarjeta. Se guarda en `vistas/` —que no
        cuenta como trabajo del proyecto— y se redibuja si la STL es nueva."""
        carpeta = _proyecto(id, banco=True)
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

    # Lo que el usuario midió en su impresora (F2.21 (impresora)).
    from orchestrator.web import impresora
    impresora.rutas(app, workspace, raiz)
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
        trabajos=JobStore(workspace / "projects", ["intelliprint", "mecanismo"],
                          comando_pieza=["intelliprint", "pieza"]),
        orden_pieza=["intelliprint", "pieza"],
        orden_obra=["intelliprint", "obra"],
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("WEB_PORT", "8080")))


if __name__ == "__main__":
    main()
