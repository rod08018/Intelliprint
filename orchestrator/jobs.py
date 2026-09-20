"""Trabajos en segundo plano (F5.6 (telegram)).

Diseñar un mecanismo tarda minutos, y quien pide por Telegram no puede
quedarse colgado esperando. Cada petición se lanza como un proceso
propio, con su carpeta de proyecto y su registro; el estado se lee de
esos archivos, así que sobrevive a que se reinicie quien pregunta.

Uno cada vez (regla 9 de § 4): dos proyectos a la vez se pelean por
FreeCAD, por el modelo y por el saldo.
"""

import datetime as dt
import json
import signal
import subprocess
from pathlib import Path

from orchestrator.tasks import slug

ARCHIVOS = {
    "animacion": "animation.gif",
    "ensamble": "assembly.FCStd",
    "revision": "review.md",
    "mecanismo": "mechanism.json",
    "peticion": "request.md",
    "registro": "run.log",
}


class JobStore:
    def __init__(self, carpeta: Path, comando: list[str]) -> None:
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._comando = comando
        self._procesos: dict[str, subprocess.Popen] = {}

    # --- lanzar y parar -------------------------------------------------------

    def start(self, peticion: str) -> str:
        en_marcha = self.current()
        if en_marcha:
            raise RuntimeError(
                f"ya hay un proyecto en marcha ({en_marcha}); espera a que termine o cancélalo"
            )
        nombre = f"{dt.datetime.now():%Y-%m-%d-%H%M%S}-{slug(peticion.splitlines()[0])[:40]}"
        destino = self.carpeta / nombre
        destino.mkdir(parents=True)
        (destino / "request.md").write_text(peticion + "\n", encoding="utf-8")
        registro = (destino / "run.log").open("w", encoding="utf-8")
        # `start_new_session`: el trabajo tiene su propio grupo de procesos, así
        # se puede cancelar con todo lo que lanza (freecadcmd incluido).
        proceso = subprocess.Popen(
            [*self._comando, str(destino / "request.md"), "--archivo", "--carpeta", str(destino)],
            stdout=registro, stderr=subprocess.STDOUT, start_new_session=True,
        )
        self._procesos[nombre] = proceso
        (destino / "job.json").write_text(
            json.dumps({"pid": proceso.pid, "inicio": dt.datetime.now().isoformat()}), encoding="utf-8")
        return nombre

    def resume(self, job_id: str) -> str:
        """Reintenta un proyecto en su propia carpeta, partiendo de su último
        diseño y del motivo por el que falló, en vez de empezar de cero."""
        destino = self.carpeta / job_id
        if not destino.exists():
            raise KeyError(f"no existe el proyecto {job_id!r}")
        en_marcha = self.current()
        if en_marcha:
            raise RuntimeError(f"ya hay un proyecto en marcha ({en_marcha})")
        registro = (destino / "run.log").open("a", encoding="utf-8")
        proceso = subprocess.Popen(
            [*self._comando, str(destino / "request.md"), "--archivo",
             "--carpeta", str(destino), "--continuar"],
            stdout=registro, stderr=subprocess.STDOUT, start_new_session=True,
        )
        self._procesos[job_id] = proceso
        (destino / "cancelado").unlink(missing_ok=True)
        return job_id

    def cancel(self, job_id: str) -> None:
        proceso = self._procesos.get(job_id)
        if proceso and proceso.poll() is None:
            # El grupo entero: el proceso lanza freecadcmd por su cuenta.
            try:
                import os

                os.killpg(os.getpgid(proceso.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proceso.terminate()
            (self.carpeta / job_id / "cancelado").write_text("", encoding="utf-8")

    # --- consultar ------------------------------------------------------------

    def current(self) -> str | None:
        for nombre, proceso in self._procesos.items():
            if proceso.poll() is None:
                return nombre
        return None

    def status(self, job_id: str, lineas: int = 12) -> dict:
        carpeta = self.carpeta / job_id
        if not carpeta.exists():
            raise KeyError(f"no existe el proyecto {job_id!r}")
        proceso = self._procesos.get(job_id)
        codigo = proceso.poll() if proceso else 0
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
        # Por fecha real y no por nombre: dos proyectos del mismo segundo
        # quedarían ordenados alfabéticamente.
        carpetas = sorted((p for p in self.carpeta.iterdir() if p.is_dir()),
                          key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        return [self.status(p.name, lineas=3) for p in carpetas[:limite]]
