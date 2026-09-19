"""Trabajos en segundo plano (F5.6 (telegram)).

Crafty, el agente de OpenClaw, no puede quedarse esperando: diseñar un
mecanismo tarda minutos. Lanza el trabajo, le devuelven un identificador y
pregunta el estado cuando quiere.
"""

import time
from pathlib import Path

import pytest

from orchestrator.jobs import JobStore


def _esperar(store, job_id, estado, segundos=10):
    limite = time.time() + segundos
    while time.time() < limite:
        if store.status(job_id)["estado"] == estado:
            return store.status(job_id)
        time.sleep(0.05)
    raise AssertionError(f"{job_id} sigue en {store.status(job_id)['estado']}")


def test_lanzar_devuelve_un_id_al_momento_y_el_trabajo_sigue_por_su_cuenta(tmp_path):
    store = JobStore(tmp_path, comando=["/bin/sh", "-c", "sleep 0.2; echo '  ronda 1: hola'"])

    job = store.start("una bisagra")

    assert store.status(job)["estado"] == "trabajando"
    assert (tmp_path / job / "request.md").read_text().startswith("una bisagra")
    estado = _esperar(store, job, "terminado")
    assert "ronda 1: hola" in estado["ultimo"]


def test_el_estado_dice_en_que_va_sin_esperar_a_que_acabe(tmp_path):
    store = JobStore(tmp_path, comando=["/bin/sh", "-c",
                                        "echo '  ronda 1: pensando'; sleep 2; echo fin"])
    job = store.start("algo")

    limite = time.time() + 5
    while "ronda 1" not in store.status(job)["ultimo"] and time.time() < limite:
        time.sleep(0.05)

    estado = store.status(job)
    assert estado["estado"] == "trabajando"
    assert "ronda 1: pensando" in estado["ultimo"]
    store.cancel(job)
    assert _esperar(store, job, "cancelado")["estado"] == "cancelado"


def test_un_fallo_se_ve_en_el_estado(tmp_path):
    store = JobStore(tmp_path, comando=["/bin/sh", "-c", "echo 'se rompió' >&2; exit 3"])
    job = store.start("algo")

    estado = _esperar(store, job, "fallido")

    assert "se rompió" in estado["ultimo"]


def test_no_se_lanzan_dos_trabajos_a_la_vez(tmp_path):
    store = JobStore(tmp_path, comando=["/bin/sh", "-c", "sleep 3"])
    store.start("uno")

    with pytest.raises(RuntimeError, match="ya hay un proyecto"):
        store.start("dos")


def test_los_archivos_del_proyecto_se_encuentran_por_su_nombre(tmp_path):
    store = JobStore(tmp_path, comando=["/bin/sh", "-c", "true"])
    job = store.start("algo")
    carpeta = tmp_path / job
    (carpeta / "animation.gif").write_bytes(b"GIF89a")
    (carpeta / "assembly.FCStd").write_bytes(b"zip")
    (carpeta / "review.md").write_text("# revisión")

    archivos = store.artifacts(job)

    assert Path(archivos["animacion"]).name == "animation.gif"
    assert Path(archivos["ensamble"]).name == "assembly.FCStd"
    assert "revisión" in Path(archivos["revision"]).read_text()


def test_listar_muestra_los_proyectos_mas_recientes_primero(tmp_path):
    store = JobStore(tmp_path, comando=["/bin/sh", "-c", "true"])
    primero = store.start("uno")
    _esperar(store, primero, "terminado")
    segundo = store.start("dos")

    ids = [p["id"] for p in store.list()]

    assert ids[:2] == [segundo, primero]
