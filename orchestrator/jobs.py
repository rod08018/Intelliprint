"""Trabajos en segundo plano (F5.6 (telegram)).

Diseñar tarda minutos, y quien pide por Telegram no puede quedarse
colgado esperando. Cada petición se lanza como un proceso
propio, con su carpeta de proyecto y su registro; el estado se lee de
esos archivos, así que sobrevive a que se reinicie quien pregunta.

Uno cada vez (regla 9 de § 4): dos proyectos a la vez se pelean por
FreeCAD, por el modelo y por el saldo.
"""

import datetime as dt
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

from orchestrator.tasks import slug

ARCHIVOS = {
    "animacion": "animation.gif",
    "ensamble": "assembly.FCStd",
    "revision": "review.md",
    "coste": "design_cost.md",
    "bloqueo": "blocked.md",
    "mecanismo": "mechanism.json",
    "peticion": "request.md",
    "registro": "run.log",
}


ENTORNO = {**os.environ, "PYTHONUNBUFFERED": "1"}
"""Sin esto, Python guarda lo que imprime en un búfer de 8 KB cuando la
salida es un archivo: `run.log` se queda VACÍO durante rondas enteras y
quien pregunta por el estado no ve nada (pasó con el Geneva drive)."""


BUZON_POR_DEFECTO = Path.home() / ".openclaw" / "workspace" / "intelliprint"
"""Dónde dejar copias para el canal. OpenClaw se niega a mandar archivos
fuera de su propia carpeta, así que Intelliprint los deja allí listos
(fallo real: Crafty no pudo enviarte el GIF y mandó el .FCStd)."""


def entregar(proyecto: Path, buzon: Path | None = None) -> dict[str, str]:
    """Copia los archivos del proyecto al buzón del canal y devuelve dónde
    quedaron. No toca los originales."""
    proyecto = Path(proyecto)
    # INTELLIPRINT_BUZON: en Docker, el MCP y Crafty montan el mismo volumen
    # en la MISMA ruta, así que las rutas que se devuelven valen a los dos
    # lados sin traducir nada.
    destino = Path(buzon or os.environ.get("INTELLIPRINT_BUZON") or BUZON_POR_DEFECTO) / proyecto.name
    destino.mkdir(parents=True, exist_ok=True)
    entregados = {}
    for nombre, archivo in ARCHIVOS.items():
        origen = proyecto / archivo
        if origen.exists():
            copia = destino / archivo
            shutil.copy2(origen, copia)
            entregados[nombre] = str(copia)
    # Las imágenes de evidencia del bloqueo: es lo que deja ver el problema.
    for imagen in sorted(proyecto.glob("fallo_*.png")):
        copia = destino / imagen.name
        shutil.copy2(imagen, copia)
        entregados.setdefault("evidencias", []).append(str(copia))
    return entregados


ESPERA_AL_CANCELAR_S = 5
"""Lo que se espera a que el trabajo cancelado muera de verdad. Sin
manejador de SIGTERM muere al momento; esto es por si no."""


class FlujoRetirado(ValueError):
    """El proyecto lo hizo un flujo que ya no existe: se ve, pero no se sigue."""


class JobStore:
    def __init__(self, carpeta: Path, comando: list[str],
                 comando_pieza: list[str] | None = None) -> None:
        """`comando`: la orden por omisión, la de un backlog (`intelliprint
        obra`). `comando_pieza`: la de una pieza suelta. Hasta F9.13 (limpieza)
        la orden por omisión era `intelliprint mecanismo`, y todo lo que no
        decía qué era acababa en ese flujo."""
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._comando = comando
        self._comando_pieza = comando_pieza
        self._procesos: dict[str, subprocess.Popen] = {}

    # --- lanzar y parar -------------------------------------------------------

    def start(self, peticion: str, proyecto: dict | None = None,
              comando: list[str] | None = None) -> str:
        """`proyecto`: si esto es una versión nueva de un proyecto que ya
        existe, de cuál (`web.versiones`). Se escribe ANTES de arrancar:
        mientras trabaja, la web ya tiene que pintarla dentro de su proyecto.

        `comando`: otra orden que la del gestor, p. ej. `intelliprint pieza`
        para una pieza suelta (F5.17 (pieza)). Queda en job.json para reanudar."""
        comando = comando or self._comando
        en_marcha = self.current()
        if en_marcha:
            raise RuntimeError(
                f"ya hay un proyecto en marcha ({en_marcha}); espera a que termine o cancélalo"
            )
        nombre = f"{dt.datetime.now():%Y-%m-%d-%H%M%S}-{slug(peticion.splitlines()[0])[:40]}"
        # Una modificación conserva la primera línea de la petición, y con
        # ella el nombre: dos en el mismo segundo chocaban al crear la carpeta.
        base, n = nombre, 1
        while (self.carpeta / nombre).exists():
            n += 1
            nombre = f"{base}-{n}"
        destino = self.carpeta / nombre
        destino.mkdir(parents=True)
        (destino / "request.md").write_text(peticion + "\n", encoding="utf-8")
        if proyecto:
            (destino / "proyecto.json").write_text(
                json.dumps(proyecto, ensure_ascii=False), encoding="utf-8")
        registro = (destino / "run.log").open("w", encoding="utf-8")
        # `start_new_session`: el trabajo tiene su propio grupo de procesos, así
        # se puede cancelar con todo lo que lanza (freecadcmd incluido).
        proceso = subprocess.Popen(
            [*comando, str(destino / "request.md"), "--archivo", "--carpeta", str(destino)],
            stdout=registro, stderr=subprocess.STDOUT, start_new_session=True,
            env=ENTORNO,
        )
        self._procesos[nombre] = proceso
        (destino / "job.json").write_text(json.dumps(
            {"pid": proceso.pid, "inicio": dt.datetime.now().isoformat(), "comando": comando}),
            encoding="utf-8")
        return nombre

    def resume(self, job_id: str) -> str:
        """Vuelve a lanzar un proyecto en su propia carpeta, con la orden con
        la que se lanzó: sigue donde se quedó en vez de empezar otro."""
        destino = self.carpeta / job_id
        if not destino.exists():
            raise KeyError(f"no existe el proyecto {job_id!r}")
        en_marcha = self.current()
        if en_marcha:
            raise RuntimeError(f"ya hay un proyecto en marcha ({en_marcha})")
        return self._relanzar(job_id)

    def _orden_de(self, destino: Path) -> list[str]:
        """Con qué orden se sigue un proyecto que ya existe. Lo dice lo que
        hay en su carpeta; lo que no se sabe qué es no se lanza."""
        from orchestrator import obra
        from orchestrator.registry import _lee_json
        comando = (_lee_json(destino / "job.json") or {}).get("comando")
        if (destino / "concepto.json").exists() and self._comando_pieza:
            # Concepto solo tiene una pieza. Sin job.json (se pidió con
            # `intelliprint pieza`), aprobarlo lanzaba la orden por defecto, la
            # de mecanismos, y esa dejaba escrito «mecanismo» en job.json para
            # la siguiente vez (el soporte del HC-SR04, 2026-11-05).
            return self._comando_pieza
        if "mecanismo" in (comando or []) or (destino / "mechanism.json").is_file():
            # Los proyectos de mecanismo siguen en el workspace con
            # `intelliprint mecanismo` en su job.json. Relanzarla era un error
            # de argparse en run.log y un «fallido» sin explicación.
            raise FlujoRetirado(
                f"{destino.name} es un mecanismo, y el flujo de mecanismos se retiró: se "
                "puede ver, descargar y abrir en PrusaSlicer, pero no continuar ni cambiar. "
                "Lo que se mueve se pide ahora como un robot o conjunto (un backlog).")
        if comando:
            return comando
        if obra.es_obra(destino):
            return self._comando
        # Ni job.json con orden ni nada que diga qué es (un proyecto anterior
        # al registro, la pieza de calibración): con la orden por omisión se
        # desglosaría como backlog, gastando modelo, algo que no lo es.
        raise ValueError(f"de {destino.name} no se sabe con qué orden se lanzó: "
                         "no se puede continuar desde aquí")

    def _relanzar(self, job_id: str, comando: list[str] | None = None) -> str:
        destino = self.carpeta / job_id
        # Antes de abrir el registro: lo que no se puede seguir no deja rastro.
        comando = comando or self._orden_de(destino)
        registro = (destino / "run.log").open("a", encoding="utf-8")
        proceso = subprocess.Popen(
            [*comando, str(destino / "request.md"), "--archivo",
             "--carpeta", str(destino), "--continuar"],
            stdout=registro, stderr=subprocess.STDOUT, start_new_session=True,
            env=ENTORNO,
        )
        self._procesos[job_id] = proceso
        # El registro mira este pid y su hora de arranque: con los del
        # proceso viejo, el proyecto reanudado nunca salía «en marcha».
        (destino / "job.json").write_text(json.dumps(
            {"pid": proceso.pid, "inicio": dt.datetime.now().isoformat(), "comando": comando}),
            encoding="utf-8")
        (destino / "cancelado").unlink(missing_ok=True)
        return job_id

    def aprobar(self, job_id: str, respuestas: str = "", por: str = "") -> str:
        """El visto bueno al concepto del ingeniero (F3.20 (concepto)), y sigue.

        Con `respuestas` NO se aprueba: van al ingeniero, tal cual las
        escribió la persona, y propone otro concepto que vuelve a esperar. Contestar puede cambiar la idea, y lo que se modela tiene
        que ser algo que la persona haya visto."""
        from orchestrator import obra
        from orchestrator.pieza import ANTERIOR, CONCEPTO, RESPUESTAS, aprobar_concepto
        destino = self.carpeta / job_id
        if obra.es_obra(destino):
            # F7.2 (desglose): lo que espera es el desglose o el concepto del
            # nodo en el que se está; lo decide la obra.
            self._libre()
            obra.aprobar(destino, respuestas=respuestas, por=por)
            return self._relanzar(job_id)
        if not (destino / CONCEPTO).exists():
            raise ValueError(f"{job_id} no tiene ningún concepto esperando el visto bueno")
        # Antes de tocar nada: con la marca puesta, un proyecto sin rondas y
        # recién tocado parece «en marcha», y se negaba a reanudarse a sí mismo.
        en_marcha = self.current()
        if en_marcha:
            raise RuntimeError(f"ya hay un proyecto en marcha ({en_marcha})")
        # La orden, antes de mover el concepto: es lo que dice que esto es
        # una pieza cuando no hay job.json.
        comando = self._orden_de(destino)
        if respuestas.strip():
            # Al ingeniero, no a la petición: el agente de requisitos hacía de
            # cada cifra de una respuesta un requisito (2026-11-09).
            with (destino / RESPUESTAS).open("a", encoding="utf-8") as f:
                f.write(respuestas.strip() + "\n")
            # El contestado es el punto de partida del siguiente concepto:
            # sin él el ingeniero empezaba de cero (pan-tilt, 2026-11-09).
            (destino / CONCEPTO).replace(destino / ANTERIOR)
        else:
            aprobar_concepto(destino, por=por)
        return self._relanzar(job_id, comando)

    def _libre(self) -> None:
        en_marcha = self.current()
        if en_marcha:
            raise RuntimeError(f"ya hay un proyecto en marcha ({en_marcha})")

    def dar_por_lista(self, job_id: str, nodo: str | None = None, por: str = "",
                      impresa: bool = False, nota: str = "") -> str:
        """«Está bien, la siguiente» (F7.2 (desglose)): congela el nodo y
        sigue con el que le toca."""
        from orchestrator import obra
        self._libre()
        obra.dar_por_lista(self.carpeta / job_id, nodo, por=por, impresa=impresa, nota=nota)
        return self._relanzar(job_id)

    def seguir(self, job_id: str) -> str:
        """Lanza lo siguiente de la obra cuando no espera a nadie: una pieza
        por empezar o un conjunto por mover. Si la orden muere a medias, la
        persona sigue desde la web (pan-tilt, 2026-11-09)."""
        from orchestrator import obra
        self._libre()
        destino = self.carpeta / job_id
        nodo = obra.siguiente(destino)
        if nodo is None or obra.estados(destino)[nodo] not in obra.SE_LANZAN:
            raise ValueError("lo siguiente espera tu visto bueno, no un empujón")
        return self._relanzar(job_id)

    def rehacer(self, job_id: str, nodo: str, cambio: str = "",
                desde_cero: bool = False) -> list[str]:
        """Cambia un nodo, y lo que se diseñó contra él, y sigue. Si la pieza
        ya está construida y se dice qué cambiar, se CORRIGE partiendo de
        ella (`obra.corregir`); empezar de cero hay que pedirlo."""
        from orchestrator import obra
        self._libre()
        destino = self.carpeta / job_id
        if not desde_cero and cambio.strip() and obra.programa_construido(destino, nodo):
            rehechos = obra.corregir(destino, nodo, cambio)
        else:
            rehechos = obra.rehacer(destino, nodo, cambio=cambio)
        self._relanzar(job_id)
        return rehechos

    def cancel(self, job_id: str) -> bool:
        """Para el trabajo y dice si lo paró (F9.12 (pantalla)).

        `False`: aquí no había nada que parar. O el trabajo ya no corría, o
        corre en OTRO contenedor —lo que lanza Crafty vive en el del MCP y lo
        que lanza la web, en el suyo— y desde este no se le puede mandar una
        señal: su pid es de allí. Sin esta respuesta, quien llama no tiene
        cómo saberlo: la marca `cancelado` puede ser de una vez anterior."""
        proceso = self._procesos.get(job_id)
        if proceso and proceso.poll() is None:
            # El grupo entero: el proceso lanza freecadcmd por su cuenta.
            try:
                os.killpg(os.getpgid(proceso.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proceso.terminate()
            try:
                proceso.wait(timeout=ESPERA_AL_CANCELAR_S)
                muerto = True
            except subprocess.TimeoutExpired:
                muerto = False
        elif (pid := self._cancelar_ajeno(job_id)):
            muerto = self._esperar_a_que_muera(job_id, pid)
        else:
            return False
        destino = self.carpeta / job_id
        (destino / "cancelado").write_text("", encoding="utf-8")
        if muerto:
            # Muere con SIGTERM sin pasar por el `finally` que quita su
            # latido, y el registro lo da por vivo mientras el latido sea
            # reciente: la web seguía diciendo «Diseñando…» y sin dejar pedir
            # nada minuto y medio después de cancelar. Solo si ha muerto: a
            # uno que siga vivo no se le quita lo que dice que lo está.
            # El de la carpeta y el del nodo que se estuviera diseñando.
            from orchestrator.obra import NODOS
            from orchestrator.registry import LATIDO
            for latido in (destino / LATIDO, *destino.glob(f"{NODOS}/*/{LATIDO}")):
                latido.unlink(missing_ok=True)
        return True

    def _cancelar_ajeno(self, job_id: str) -> int | None:
        """Un trabajo que no lanzó este gestor: el MCP creaba uno nuevo en
        cada llamada y `cancelar_proyecto` contestaba «terminado» con el
        trabajo siguiendo (2026-10-26). Se para por el pid de job.json, solo
        si ese proceso es el que arrancó con el trabajo. Devuelve el pid al
        que mandó la señal, o None si aquí no hay tal proceso."""
        from orchestrator.registry import _lee_json, _vivo

        trabajo = _lee_json(self.carpeta / job_id / "job.json") or {}
        pid = trabajo.get("pid")
        if not pid or not _vivo(pid, trabajo.get("inicio")):
            return None
        try:
            # Lanzado con start_new_session: su grupo lleva su mismo número.
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return None
        return pid

    def _esperar_a_que_muera(self, job_id: str, pid: int) -> bool:
        """De un proceso que no es hijo de este gestor no hay `wait()`: se
        mira si sigue ahí."""
        import time

        from orchestrator.registry import _lee_json, _vivo

        inicio = (_lee_json(self.carpeta / job_id / "job.json") or {}).get("inicio")
        limite = time.monotonic() + ESPERA_AL_CANCELAR_S
        while _vivo(pid, inicio):
            if time.monotonic() > limite:
                return False
            time.sleep(0.1)
        return True

    # --- consultar ------------------------------------------------------------

    def current(self) -> str | None:
        """Lo que está trabajando: lo lanzado aquí, y si no, lo que diga el
        workspace. Con solo la memoria de este gestor, Crafty lanzó un
        segundo sargento con el primero a medias (2026-10-26)."""
        from orchestrator.registry import en_marcha

        for nombre, proceso in self._procesos.items():
            if proceso.poll() is None:
                return nombre
        return en_marcha(self.carpeta)

    def status(self, job_id: str, lineas: int = 12) -> dict:
        carpeta = self.carpeta / job_id
        if not carpeta.exists():
            raise KeyError(f"no existe el proyecto {job_id!r}")
        proceso = self._procesos.get(job_id)
        if proceso:
            codigo = proceso.poll()
        else:
            # No lo lanzó este gestor: el registro dice si sigue trabajando.
            from orchestrator.registry import estado_de
            codigo = None if estado_de(carpeta)["estado"] == "en marcha" else 0
        cancelado = (carpeta / "cancelado").exists()
        estado = ("trabajando" if codigo is None else
                  "cancelado" if cancelado else
                  "terminado" if codigo == 0 else "fallido")
        registro = carpeta / "run.log"
        texto = registro.read_text(errors="ignore") if registro.exists() else ""
        return {
            "id": job_id,
            "estado": estado,
            "peticion": (carpeta / "request.md").read_text(errors="ignore")[:400]
            if (carpeta / "request.md").exists() else "",
            "ultimo": "\n".join(texto.strip().splitlines()[-lineas:]),
            "carpeta": str(carpeta),
        }

    def artifacts(self, job_id: str) -> dict[str, str]:
        carpeta = self.carpeta / job_id
        return {nombre: str(carpeta / archivo)
                for nombre, archivo in ARCHIVOS.items() if (carpeta / archivo).exists()}

    def list(self, limite: int = 10) -> list[dict]:
        # Por cuándo se LANZÓ (job.json, con microsegundos), y por la fecha de
        # la carpeta solo si no hay job.json. Con la fecha de la carpeta, dos
        # proyectos del mismo segundo salían a veces al revés: cualquier
        # archivo que se escribe dentro la mueve (test intermitente, 2026-11-04).
        from orchestrator.registry import _lee_json

        def lanzado(p: Path) -> str:
            inicio = (_lee_json(p / "job.json") or {}).get("inicio")
            return inicio or dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat()

        carpetas = sorted((p for p in self.carpeta.iterdir() if p.is_dir()),
                          key=lambda p: (lanzado(p), p.name), reverse=True)
        return [self.status(p.name, lineas=3) for p in carpetas[:limite]]
