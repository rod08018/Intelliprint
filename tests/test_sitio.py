"""Lo que se atornilla después necesita sitio al otro lado de sus tornillos
(F9.10 (ampliar)).

En el banco 1112-1359 se le añadió una pinza al pan-tilt. La plataforma, ya
hecha, ganó los dos M3 que la sujetan y los puso en la cara del acople: la
que da al servo que la inclina. El soporte de la pinza se alineó con ellos,
quedó construido encima de ese servo y ya no tenía arreglo. A la plataforma
nadie le había dicho hacia dónde hay sitio, ni se midió; y al reanudar se
habría corregido el soporte de la pinza, que no podía salir de ahí.

Las piezas son las de `tests/test_giro.py`. Las cuentas, a mano:

- la plataforma coloca el soporte en (−13.55, 5.6, 2.8). La caja del
  soporte, de (−18, −18, 0) a (16, 18, 20), queda en el marco de la
  plataforma de x = −31.55 a 2.45, de y = −12.4 a 23.6 y de z = 2.8 a 22.8;
- el eje de inclinación pasa, en ese marco, por (0, 0, 15) hacia +x, y la
  caja de la plataforma va de x = 2.5 a 100. Un tornillo en ese eje no
  cambia de sitio al inclinar;
- hacia −x sale de la plataforma en x = 2.5, a 0.05 mm del soporte, y lo
  que siga está dentro de su caja: 0.0 mm;
- hacia +x sale en x = 100 y sigue por el eje de inclinación, que queda a
  12.7 mm del SG90 de la base (la cifra de `test_giro`): más de los 6 mm
  que se piden alrededor de un M3.
"""

import json

import pytest

from orchestrator.medida import sin_sitio_para_lo_nuevo
from tests.test_giro import BASE, PLATAFORMA, SOPORTE, _plan
from tests.test_conjunto import _obra, _sobre
from tests.test_tornilleria import _agujero

HACIA_EL_SERVO = {**_agujero("pinza_1", (10, 0, 15), eje=(-1, 0, 0), metrica="M3"),
                  "uso": "pasante"}
HACIA_FUERA = {**_agujero("pinza_1", (90, 0, 15), eje=(1, 0, 0), metrica="M3"),
               "uso": "pasante"}


def _con_pinza(tmp_path, agujeros, pinza=None, cabeza="plataforma", agarre="inserto"):
    """El pan-tilt de `test_giro` con una pinza que el plan atornilla a la
    plataforma con un M3. La pinza, construida solo si se pasa."""
    piezas = {"base": BASE, "soporte": SOPORTE,
              "plataforma": (PLATAFORMA[0], [*PLATAFORMA[1], *agujeros], PLATAFORMA[2])}
    if pinza is not None:
        piezas["pinza"] = pinza
    _obra(tmp_path, piezas)
    plan = _plan(radio_inclinar=40.0)
    plan["nodos"].insert(3, {"id": "pinza", "nombre": "Pinza", "que_hace": "x",
                             "depende_de": ["plataforma"]})
    plan["nodos"][-1]["depende_de"].append("pinza")
    otra = "pinza" if cabeza == "plataforma" else "plataforma"
    plan["uniones"].append({"tipo": "fija", "id": "u4", "cabeza": cabeza, "agarra": otra,
                            "metrica": "M3", "cantidad": 1, "agarre": agarre})
    (tmp_path / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    return tmp_path


def test_el_tornillo_que_da_al_servo_no_deja_sitio_a_lo_que_sujeta(tmp_path):
    """El defecto es de la plataforma, en su propio bucle, y dice qué
    estorba, cuánto queda y qué hacer."""
    [defecto] = sin_sitio_para_lo_nuevo(_con_pinza(tmp_path, [HACIA_EL_SERVO]), "plataforma")
    assert "«Pinza»" in defecto and "unión u4" in defecto
    assert "«pinza_1»" in defecto and "«Soporte»" in defecto and "0.0 mm" in defecto
    assert "6 mm" in defecto, "lo que se pide alrededor de un M3: dos diámetros"
    assert "otra cara" in defecto


def test_el_tornillo_que_da_hacia_fuera_deja_sitio(tmp_path):
    assert sin_sitio_para_lo_nuevo(_con_pinza(tmp_path, [HACIA_FUERA]), "plataforma") == []


@pytest.mark.parametrize("entrada, eje, estorba", [((2.5, 0, 15), (1, 0, 0), True),
                                                   ((100, 0, 15), (-1, 0, 0), False)])
def test_si_la_pieza_hecha_es_donde_agarra_lo_nuevo_va_delante_de_la_boca(
        tmp_path, entrada, eje, estorba):
    """Con el inserto en la plataforma, la cabeza es de la pinza: la pinza
    queda delante de la boca del agujero, al revés de por donde avanza el
    tornillo. Un inserto en la cara x = 2.5 mira al soporte; uno en la cara
    x = 100, hacia fuera."""
    inserto = {**_agujero("pinza_1", entrada, eje=eje, d=4.1, metrica="M3", profundidad=6),
               "uso": "inserto"}
    carpeta = _con_pinza(tmp_path, [inserto], cabeza="pinza")
    assert bool(sin_sitio_para_lo_nuevo(carpeta, "plataforma")) is estorba


def test_sin_agujeros_todavia_no_hay_sitio_que_medir(tmp_path):
    """Que falten los tornillos ya lo dice `uniones_sin_hacer`."""
    assert sin_sitio_para_lo_nuevo(_con_pinza(tmp_path, []), "plataforma") == []


def test_con_la_otra_pieza_construida_se_mide_como_si_faltara(tmp_path):
    """Es lo que pregunta el banco al reanudar: la pinza ya está construida
    —mal, encima del servo— y sus agujeros comparten recta con los de la
    plataforma, así que el tornillo ya no está «libre». Quitándola de la
    cuenta se ve que la plataforma no le dejó sitio."""
    inserto = {**_agujero("m3", (-2, 0, 0), eje=(-1, 0, 0), d=4.1, metrica="M3", profundidad=6),
               "uso": "inserto"}
    pinza = (["plataforma"], [_sobre("plataforma", (-4.5, 0, -15)), inserto],
             ([-20, -10, -10], [-2, 10, 10]))
    carpeta = _con_pinza(tmp_path, [HACIA_EL_SERVO], pinza=pinza)
    assert sin_sitio_para_lo_nuevo(carpeta, "plataforma") == []
    [defecto] = sin_sitio_para_lo_nuevo(carpeta, "plataforma", como_si_faltara={"pinza"})
    assert "«Soporte»" in defecto and "0.0 mm" in defecto


def test_un_tramo_no_es_una_semirrecta():
    """El sitio de un giro se mide por toda la semirrecta del eje; el de lo
    que se atornilla, solo en el fondo que se pide. Una caja de 10 de lado
    a 50 mm por delante de la punta, en línea: la semirrecta la atraviesa
    (0 mm) y a un tramo de 20 mm le quedan 50 − 20 = 30."""
    from orchestrator.conjunto import _semirrecta_a_la_caja
    caja = ([50, -5, -5], [60, 5, 5])
    assert _semirrecta_a_la_caja(caja, [0, 0, 0], [1, 0, 0]) == pytest.approx(0, abs=1e-6)
    assert _semirrecta_a_la_caja(caja, [0, 0, 0], [1, 0, 0], largo=20) == pytest.approx(30)


# --- a quien diseña se le dice antes ------------------------------------------------------------

def test_a_la_pieza_hecha_se_le_dice_que_lo_nuevo_necesita_sitio(tmp_path):
    """En el texto de la unión, para la pieza que se diseña antes que la
    otra: es la que decide dónde caen los tornillos."""
    from orchestrator import obra as O
    carpeta = _con_pinza(tmp_path, [])
    [u4] = [u for u in O.uniones_del_nodo(carpeta, "plataforma") if u["id"] == "u4"]
    assert "al otro lado de esos agujeros" in u4["texto"] and "se mide" in u4["texto"]
    [de_la_pinza] = [u for u in O.uniones_del_nodo(carpeta, "pinza") if u["id"] == "u4"]
    assert "al otro lado" not in de_la_pinza["texto"], "la pinza se alinea con los que hay"


# --- al reanudar, la culpa vuelve a quien no dejó el sitio --------------------------------------

def _corrida_con_pinza(tmp_path):
    """Una corrida del banco con ese backlog: todo dado por listo por el
    banco, la pinza con defectos y un dedo encima que tampoco salió."""
    inserto = {**_agujero("m3", (-2, 0, 0), eje=(-1, 0, 0), d=4.1, metrica="M3", profundidad=6),
               "uso": "inserto"}
    pinza = (["plataforma"], [_sobre("plataforma", (-4.5, 0, -15)), inserto],
             ([-20, -10, -10], [-2, 10, 10]))
    p = tmp_path / "corrida" / "01" / "projects" / "a"
    p.mkdir(parents=True)
    _con_pinza(p, [HACIA_EL_SERVO], pinza=pinza)
    plan = json.loads((p / "obra.json").read_text(encoding="utf-8"))
    plan["nodos"].insert(4, {"id": "dedo", "nombre": "Dedo", "que_hace": "x",
                             "depende_de": ["pinza"]})
    plan["nodos"][-1]["depende_de"].append("dedo")
    (p / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    dedo = p / "nodos" / "dedo" / "parts" / "dedo"
    dedo.mkdir(parents=True)
    (dedo / "rasgos.json").write_text(json.dumps([_sobre("pinza", (0, 0, 0))]), encoding="utf-8")
    (dedo / "envolvente.json").write_text('{"min": [0, 0, 0], "max": [1, 1, 1]}')
    (dedo / "dedo.step").write_text("STEP", encoding="utf-8")
    for i, resuelto in {"base": True, "soporte": True, "plataforma": True, "pinza": False,
                        "dedo": False}.items():
        nodo = p / "nodos" / i
        (nodo / "lista.json").write_text('{"por": "banco"}', encoding="utf-8")
        (nodo / "pieza_report.json").write_text(
            json.dumps({"titulo": i, "resuelto": resuelto}), encoding="utf-8")
        (nodo / "concepto_aprobado").write_text("{}", encoding="utf-8")
        (nodo / "parts" / i / "programa.py").write_text(f"PROGRAMA DE {i}", encoding="utf-8")
    return tmp_path / "corrida", p


def test_el_banco_sabe_que_pieza_no_dejo_sitio_a_la_que_fallo(tmp_path):
    from orchestrator.banco import la_que_no_deja_sitio
    _, p = _corrida_con_pinza(tmp_path)
    abajo, falta = la_que_no_deja_sitio(p, "pinza")
    assert abajo == "plataforma" and "«Soporte»" in falta
    assert la_que_no_deja_sitio(p, "plataforma") is None, "no va atornillada a nada de abajo"


def test_reanudar_corrige_la_pieza_que_no_dejo_sitio_y_rehace_las_de_encima(
        tmp_path, monkeypatch):
    """Corregir la pinza no la saca de encima del servo: los agujeros a los
    que se ata son de la plataforma. Se corrige la plataforma con lo medido,
    y la pinza y el dedo, que nunca salieron bien, se hacen de nuevo contra
    ella en vez de retocarse. Lo demás no se toca, y nada se borra."""
    from orchestrator import banco
    corrida, p = _corrida_con_pinza(tmp_path)

    class Hecho:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr(banco.subprocess, "run", lambda orden, **k: Hecho())
    monkeypatch.setattr(banco, "rejuzgar", lambda *a, **k: ({"x": []}, {}))
    e = banco.Encargo(nombre="x", categoria="robots", peticion="un pan-tilt", obra=True,
                      oraculo=[{"tipo": "conjunto_libre"}])
    banco.reanudar([e], corrida, ["intelliprint", "obra", "--banco"], "fc", {})

    retoque = json.loads((p / "nodos" / "plataforma" / "retoque.json")
                         .read_text(encoding="utf-8"))
    assert retoque["programa"] == "PROGRAMA DE plataforma"
    assert "«Soporte»" in retoque["cambio"] and "otra cara" in retoque["cambio"]
    for i in ("pinza", "dedo"):
        assert not (p / "nodos" / i / "parts").exists(), f"«{i}» se hace de nuevo"
        assert not (p / "nodos" / i / "retoque.json").exists()
        assert next(p.glob(f"archivo/*/nodos/{i}/parts/{i}/programa.py"), None) is not None
    assert "«Plataforma»" in (p / "nodos" / "pinza" / "cambios.md").read_text(encoding="utf-8")
    for i in ("base", "soporte"):
        assert (p / "nodos" / i / "lista.json").is_file()
