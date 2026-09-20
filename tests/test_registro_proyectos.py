"""Registro de proyectos (F5.1 (registro)).

`workspace/projects` acabó con 25 carpetas mezcladas —pruebas, intentos
fallidos y proyectos buenos— sin forma de saber cuál era cuál. El registro
las clasifica por lo que hay DENTRO de cada una, no por su nombre, y deja
en `projects/` solo lo aprobado. Lo demás se MUEVE a `archivo/`: nunca se
borra nada (memoria del usuario).
"""

import json
import os
import time

from orchestrator.registry import archivar, escribir_indice, indice


def _proyecto(raiz, nombre, *, rondas=None, coste=None, artefactos=(), peticion="una bisagra"):
    carpeta = raiz / nombre
    carpeta.mkdir(parents=True)
    (carpeta / "request.md").write_text(peticion + "\n", encoding="utf-8")
    if rondas is not None:
        (carpeta / "rounds.json").write_text(json.dumps(rondas), encoding="utf-8")
        (carpeta / "mechanism.json").write_text(
            json.dumps({"title": "Bisagra", "summary": "s"}), encoding="utf-8")
    if coste is not None:
        (carpeta / "design_cost.json").write_text(
            json.dumps({"resumen": {"total_usd": coste, "llamadas": 3}}), encoding="utf-8")
    for a in artefactos:
        (carpeta / a).write_bytes(b"x")
    return carpeta


def _envejecer(carpeta, horas=2):
    """Una carpeta tocada hace poco cuenta como en marcha: para probar el
    archivado hay que simular que es vieja."""
    viejo = time.time() - horas * 3600
    for f in [carpeta, *carpeta.rglob("*")]:
        os.utime(f, (viejo, viejo))
    return carpeta


def _resuelto(raiz, nombre, **kw):
    return _proyecto(raiz, nombre, rondas=[{"number": 1, "title": "Bisagra", "feedback": ""}],
                     artefactos=("assembly.FCStd", "animation.gif"), **kw)


def _fallido(raiz, nombre, **kw):
    return _proyecto(raiz, nombre,
                     rondas=[{"number": 1, "title": "Gato", "feedback": "- se solapan"}],
                     artefactos=("assembly.FCStd",), **kw)


def test_clasifica_cada_proyecto_por_lo_que_hay_dentro(tmp_path):
    _envejecer(_resuelto(tmp_path, "2026-09-19-1000-bisagra", coste=0.42))
    _envejecer(_fallido(tmp_path, "2026-09-19-1100-gato", coste=1.90))
    _envejecer(_proyecto(tmp_path, "2026-09-19-1200-a_medias"))   # sin rounds: no terminó

    filas = {f["id"]: f for f in indice(tmp_path)}

    assert filas["2026-09-19-1000-bisagra"]["estado"] == "aprobado"
    assert filas["2026-09-19-1000-bisagra"]["usd"] == 0.42
    assert filas["2026-09-19-1100-gato"]["estado"] == "fallido"
    assert "se solapan" in filas["2026-09-19-1100-gato"]["motivo"]
    assert filas["2026-09-19-1200-a_medias"]["estado"] == "incompleto"


def test_un_proyecto_en_marcha_no_se_confunde_con_uno_fallido(tmp_path):
    carpeta = _proyecto(tmp_path, "2026-09-19-1300-en_marcha")
    (carpeta / "job.json").write_text(json.dumps({"pid": 999999}), encoding="utf-8")
    (carpeta / "run.log").write_text("ronda 3\n", encoding="utf-8")

    fila = indice(tmp_path)[0]

    assert fila["estado"] in {"en marcha", "incompleto"}


def test_el_indice_se_escribe_legible_y_ordenado_por_fecha(tmp_path):
    _envejecer(_resuelto(tmp_path, "2026-09-19-1000-bisagra", coste=0.42), horas=3)
    _envejecer(_fallido(tmp_path, "2026-09-19-1100-gato", coste=1.90), horas=2)

    escribir_indice(tmp_path)

    texto = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert texto.index("gato") < texto.index("bisagra")     # lo más reciente primero
    assert "aprobado" in texto and "fallido" in texto
    assert "0.42" in texto and "2.32" in texto              # coste y total


def test_archivar_mueve_lo_no_aprobado_y_no_borra_nada(tmp_path):
    proyectos = tmp_path / "projects"
    proyectos.mkdir()
    _envejecer(_resuelto(proyectos, "2026-09-19-1000-bisagra"))
    _envejecer(_fallido(proyectos, "2026-09-19-1100-gato"))
    _envejecer(_proyecto(proyectos, "2026-09-19-1200-a_medias"))

    movidos = archivar(proyectos, tmp_path / "archivo")

    assert sorted(p.name for p in proyectos.iterdir()) == ["2026-09-19-1000-bisagra", "INDEX.md"]
    # El archivo lleva su propio índice: también tiene que ser navegable.
    assert sorted(p.name for p in (tmp_path / "archivo").iterdir()) == [
        "2026-09-19-1100-gato", "2026-09-19-1200-a_medias", "INDEX.md"]
    assert len(movidos) == 2
    # Lo movido conserva todo: archivar no es borrar.
    assert (tmp_path / "archivo" / "2026-09-19-1100-gato" / "assembly.FCStd").exists()


def test_archivar_respeta_lo_que_esta_en_marcha(tmp_path):
    proyectos = tmp_path / "projects"
    proyectos.mkdir()
    carpeta = _proyecto(proyectos, "2026-09-19-1300-en_marcha")
    (carpeta / "job.json").write_text(json.dumps({"pid": 1}), encoding="utf-8")

    archivar(proyectos, tmp_path / "archivo", proteger={"2026-09-19-1300-en_marcha"})

    assert (proyectos / "2026-09-19-1300-en_marcha").exists()


def test_un_proyecto_anterior_al_registro_con_obra_hecha_no_se_archiva(tmp_path):
    """Los primeros proyectos (el soporte NEMA17, las biela-manivela) no
    tienen rounds.json, pero dejaron piezas y ensamble: son trabajo bueno."""
    proyectos = tmp_path / "projects"
    proyectos.mkdir()
    viejo = _proyecto(proyectos, "2026-09-19-soporte_nema17", artefactos=("assembly.FCStd",))
    (viejo / "parts" / "soporte").mkdir(parents=True)
    (viejo / "parts" / "soporte" / "soporte.step").write_bytes(b"x")
    _envejecer(viejo)
    _envejecer(_proyecto(proyectos, "2026-09-19-vacio"))   # sin nada dentro: ese sí

    movidos = archivar(proyectos, tmp_path / "archivo")

    assert movidos == ["2026-09-19-vacio"]
    assert (proyectos / "2026-09-19-soporte_nema17").exists()
    assert indice(proyectos)[0]["estado"] == "antiguo"


def test_una_carpeta_tocada_hace_poco_cuenta_como_en_marcha(tmp_path):
    """Fallo real: se archivó la leva mientras la estaba diseñando, porque
    se lanzó a mano y no tenía job.json. El proceso se quedó sin carpeta."""
    proyectos = tmp_path / "projects"
    proyectos.mkdir()
    _proyecto(proyectos, "2026-09-19-1400-recien_lanzado")   # escrito ahora mismo

    movidos = archivar(proyectos, tmp_path / "archivo")

    assert movidos == []
    assert indice(proyectos)[0]["estado"] == "en marcha"
