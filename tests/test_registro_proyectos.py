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


def test_colgado_se_mide_por_lo_que_lleva_sin_escribir_no_por_lo_que_lleva_corriendo(tmp_path):
    """Crafty avisó de que el trinquete estaba colgado cuando llevaba 53
    minutos trabajando bien: la regla miraba el tiempo total, no la última
    señal de vida."""
    trabajando = _proyecto(tmp_path, "2026-09-19-1400-trabajando")   # escrito ahora
    parado = _proyecto(tmp_path, "2026-09-19-1300-parado")
    (parado / "job.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    _envejecer(parado, horas=0.5)      # vivo, pero sin escribir nada hace media hora

    filas = {f["id"]: f for f in indice(tmp_path)}

    assert filas[trabajando.name]["parece_colgado"] is False
    assert filas[parado.name]["parece_colgado"] is True
    assert filas[parado.name]["segundos_sin_moverse"] > 12 * 60


def test_un_proceso_zombi_no_cuenta_como_en_marcha(tmp_path):
    """Fallo real: el Geneva drive falló a las 09:42 y seis horas después el
    registro seguía diciendo «en marcha».

    Un proceso que terminó pero que su padre no ha recogido queda como
    zombi, y `os.kill(pid, 0)` le responde que sí existe. Existir no es
    estar trabajando."""
    import subprocess

    hijo = subprocess.Popen(["/usr/bin/true"])   # muere enseguida
    time.sleep(0.2)                              # y nadie lo recoge: zombi
    carpeta = _proyecto(tmp_path, "2026-09-20-0929-ginebra")
    (carpeta / "job.json").write_text(json.dumps({"pid": hijo.pid}), encoding="utf-8")
    _envejecer(carpeta, horas=6)

    fila = indice(tmp_path)[0]

    assert fila["estado"] != "en marcha"
    hijo.wait()


def test_un_hilo_de_quien_pregunta_no_cuenta_como_en_marcha(tmp_path):
    """Fallo real (2026-10-23): la web pintaba tres proyectos «trabajando» y
    no dejaba pedir nada. Sus job.json guardan el pid que tenían en OTRO
    contenedor (8 y 9), y en el de la web esos números eran hilos del propio
    servidor: `os.kill` acepta el id de un hilo, y `ps -p` no lo encuentra y
    no dice nada, que no es «zombi»."""
    import threading

    soltar = threading.Event()
    hilo = threading.Thread(target=soltar.wait)
    hilo.start()
    try:
        carpeta = _proyecto(tmp_path, "2026-09-21-2333-pastillero")
        (carpeta / "job.json").write_text(json.dumps({"pid": hilo.native_id}), encoding="utf-8")
        _envejecer(carpeta, horas=6)

        fila = indice(tmp_path)[0]
    finally:
        soltar.set()
        hilo.join()

    assert fila["estado"] != "en marcha"


def test_lo_que_escribe_la_web_no_hace_parecer_vivo_un_proyecto(tmp_path):
    """Fallo real (2026-10-24): la web guarda la vista de las piezas y el
    .3mf DENTRO del proyecto. Un proyecto sin rondas tocado hace poco cuenta
    como en marcha, así que mirar la pieza de calibración bloqueaba «Diseñar»
    media hora. Eso no es trabajo del proyecto."""
    carpeta = _proyecto(tmp_path, "2026-10-24-1607-calibracion", artefactos=("assembly.FCStd",))
    _envejecer(carpeta, horas=2)
    (carpeta / "vista.png").write_bytes(b"png")
    (carpeta / "imprimir").mkdir()
    (carpeta / "imprimir" / "p.3mf").write_bytes(b"PK")

    assert indice(tmp_path)[0]["estado"] != "en marcha"


def test_con_job_json_manda_el_proceso_y_no_lo_reciente(tmp_path):
    """La regla de «tocado hace poco» es para lo lanzado a mano, que no deja
    job.json. Si lo hay, el proceso dice si trabaja: una pieza recién
    construida cuyo proceso ya terminó no sigue «en marcha»."""
    import subprocess

    hijo = subprocess.Popen(["true"])
    hijo.wait()
    carpeta = _proyecto(tmp_path, "2026-10-24-1607-calibracion", artefactos=("assembly.FCStd",))
    (carpeta / "job.json").write_text(json.dumps({"pid": hijo.pid}), encoding="utf-8")

    assert indice(tmp_path)[0]["estado"] != "en marcha"


def test_un_pid_reutilizado_por_otro_trabajo_no_resucita_un_proyecto_viejo(tmp_path):
    """Fallo real (2026-10-24): el brazo robótico corría como pid 8 en el
    contenedor de la web, y tres proyectos de hacía un mes guardaban
    `"pid": 8` en su job.json —su número en otro contenedor—. La página
    pintaba «4 trabajando». El pid solo vale si el proceso arrancó cuando
    arrancó ese trabajo."""
    import datetime as dt
    import subprocess

    vivo = subprocess.Popen(["sleep", "30"])
    try:
        viejo = _proyecto(tmp_path, "2026-09-21-2107-pastillero", rondas=[{"feedback": ""}])
        (viejo / "job.json").write_text(json.dumps(
            {"pid": vivo.pid, "inicio": "2026-09-21T21:07:06.328746"}), encoding="utf-8")
        _envejecer(viejo, horas=6)
        nuevo = _proyecto(tmp_path, "2026-10-24-0231-brazo", rondas=[{"feedback": "- choca"}])
        (nuevo / "job.json").write_text(json.dumps(
            {"pid": vivo.pid, "inicio": dt.datetime.now().isoformat()}), encoding="utf-8")

        filas = {f["id"]: f for f in indice(tmp_path)}
    finally:
        vivo.kill()
        vivo.wait()

    assert filas[viejo.name]["estado"] == "aprobado"
    # El que de verdad lleva ese pid sigue en marcha.
    assert filas[nuevo.name]["estado"] == "en marcha"


def _de_otro_contenedor(carpeta):
    """El job.json que deja el JobStore del contenedor del MCP: un pid que
    aquí no existe, lanzado ahora mismo."""
    import datetime as dt

    (carpeta / "job.json").write_text(json.dumps(
        {"pid": 999999, "inicio": dt.datetime.now().isoformat()}), encoding="utf-8")


def test_un_proyecto_que_corre_en_otro_contenedor_sale_en_marcha_si_late(tmp_path):
    """Fallo real (2026-10-26): Crafty lanzó el sargento en el contenedor
    del MCP y la web, que busca el pid en el SUYO, lo pintaba «⚠️ incompleto»
    mientras el razonador pensaba su primera ronda. El pid de otro contenedor
    no se puede comprobar; el latido que el proceso deja en su carpeta sí."""
    from orchestrator.registry import latir

    carpeta = _proyecto(tmp_path, "2026-10-27-035747-mini_sargento")
    _de_otro_contenedor(carpeta)

    with latir(carpeta):
        dentro = indice(tmp_path)[0]["estado"]
    fuera = indice(tmp_path)[0]["estado"]

    assert dentro == "en marcha"
    assert fuera == "incompleto"


def test_un_latido_viejo_es_un_proceso_muerto(tmp_path):
    """Un proceso que muere de golpe (SIGKILL, el contenedor reiniciado) no
    llega a quitar su latido. Que el archivo exista no basta: tiene que ser
    reciente."""
    carpeta = _proyecto(tmp_path, "2026-10-27-035747-mini_sargento")
    _de_otro_contenedor(carpeta)
    (carpeta / "latido").write_text("", encoding="utf-8")
    _envejecer(carpeta, horas=0.5)

    assert indice(tmp_path)[0]["estado"] == "incompleto"


def test_el_latido_no_esconde_un_proyecto_colgado(tmp_path):
    """El latido dice que el proceso existe, no que avance: si contara como
    «tocado hace poco», un proyecto atascado nunca saldría colgado."""
    carpeta = _proyecto(tmp_path, "2026-10-27-035747-mini_sargento")
    _de_otro_contenedor(carpeta)
    _envejecer(carpeta, horas=0.5)
    (carpeta / "latido").write_text("", encoding="utf-8")   # recién latido

    fila = indice(tmp_path)[0]

    assert fila["estado"] == "en marcha"
    assert fila["parece_colgado"] is True


def _revisado(carpeta, **veredictos):
    items = [{"requirement": f"{v} {i}", "verdict": v, "comment": "c"}
             for v, n in veredictos.items() for i in range(n)]
    (carpeta / "review.json").write_text(
        json.dumps({"summary": "s", "items": items}), encoding="utf-8")
    return carpeta


def test_lo_que_el_revisor_suspende_no_sale_aprobado(tmp_path):
    """Fallo real (2026-10-26): el sargento salía ✅ «aprobado» y «★ la
    mejor» con 11 requisitos del usuario sin cumplir. El revisor solo puede
    devolver el diseño unas pocas veces; agotadas, la última ronda sin
    choques se daba por buena y el registro no miraba review.json. Sin
    choques es que funciona, no que sea lo que se pidió."""
    carpeta = _revisado(_envejecer(_resuelto(tmp_path, "2026-10-27-035747-sargento")),
                        cumple=7, no_cumple=11, no_verificable=9)

    fila = indice(tmp_path)[0]

    assert fila["estado"] == "con reparos"
    assert "11" in fila["motivo"]


def test_lo_que_el_revisor_no_suspende_sigue_aprobado(tmp_path):
    """«No verificable» no es un suspenso: nadie lo comprueba, ni a favor ni
    en contra."""
    _revisado(_envejecer(_resuelto(tmp_path, "2026-09-21-1611-trinquete")),
              cumple=5, no_verificable=3)

    assert indice(tmp_path)[0]["estado"] == "aprobado"


def test_lo_que_tiene_reparos_no_se_archiva(tmp_path):
    """Funciona y tiene piezas: es obra, no un intento fallido."""
    proyectos = tmp_path / "projects"
    _revisado(_envejecer(_resuelto(proyectos, "2026-10-27-035747-sargento")), no_cumple=2)

    assert archivar(proyectos, tmp_path / "archivo") == []
