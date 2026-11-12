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


# --- lo que viene lleva un giro: no basta con 20 mm de fondo ------------------------------------
#
# Reanudada la 1112-1359, la plataforma movió los dos M3 a su cara de abajo.
# Había 12 mm libres y la medida de arriba pide 6, así que pasó. Pero lo que
# se atornilla ahí lleva un servo, y el dedo que gira sobre él necesita 40 mm
# libres alrededor del eje: bajo la plataforma quedaban 0.9. El soporte de la
# pinza gastó cinco intentos sin poder salir de ahí. Lo que necesita la pieza
# que viene lo dice el plan, y se le puede pedir a la que taladra primero.
#
# Las cuentas, a mano, en el marco de la base (z hacia arriba):
#
# - el eje de giro (pan) pasa por (19.4, 15) y la base va de (0, 0) a
#   (50, 30): sus esquinas más lejanas quedan a √(30.6² + 15²) = 34.1 mm de
#   ese eje; nada de la base pasa de ahí al girar. Su cara de arriba está en
#   z = 21.6;
# - el eje de inclinación sale del soporte en (13.55, −5.6, 12.2) hacia +x;
#   el soporte está en (19.4, 15, 33.6), así que va a z = 45.8. Un punto a
#   x mm por ese eje queda a √((13.55 + x)² + 5.6²) del eje de giro;
# - HACIA_ABAJO sale por la cara de abajo de la plataforma (z = 0 en su
#   marco: 30.8 en el de la base) en x = 31.1: a √(44.65² + 5.6²) = 45.0 mm
#   del eje de giro, 45.0 − 34.1 = 10.9 mm por fuera de la base. Son más de
#   los 6 que se piden alrededor de un M3, también al inclinar (de lado
#   queda a la altura del eje, 24.2 mm por encima de la base);
# - pero cualquier punto más abajo en esa recta sigue a 10.9 mm de la base
#   en horizontal y, como mucho, 30.8 − 21.6 = 9.2 mm por encima de ella: a
#   √(10.9² + 9.2²) = 14.3 mm cuando una esquina pasa por delante (con el
#   giro de 30 en 30°, 14.5). Y a 30.8 mm está la mesa en la que se apoya
#   la base: sin contarla, 80 mm más abajo «había» 46 mm libres. No hay
#   dónde poner un eje con 40 mm libres;
# - HACIA_FUERA sale por la cara x = 100, en el eje de inclinación: a
#   113.7 mm del eje de giro, 79.6 por fuera de la base en cualquier ángulo,
#   y a 45.8 de la mesa.

HACIA_ABAJO = {**_agujero("pinza_1", (31.1, 0, 30), eje=(0, 0, -1), metrica="M3"),
               "uso": "pasante"}


def _con_dedo(carpeta, radio=40.0):
    """A la pinza del plan se le pone un SG90 y un dedo que gira sobre él."""
    plan = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    [pinza] = [n for n in plan["nodos"] if n["id"] == "pinza"]
    pinza["compra"] = ["sg90"]
    plan["nodos"].insert(-1, {"id": "dedo", "nombre": "Dedo", "que_hace": "x",
                              "depende_de": ["pinza"]})
    plan["nodos"][-1]["depende_de"].append("dedo")
    plan["uniones"].append({"tipo": "gira", "id": "u5", "gira": "dedo", "sobre": "pinza",
                            "componente": "sg90", "recorrido_grados": 60,
                            "radio_libre_mm": radio})
    (carpeta / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    return carpeta


def test_sin_giro_en_lo_que_viene_bastan_los_20_mm_de_fondo(tmp_path):
    """La cara de abajo, a 10.9 mm de la base: para una escuadra vale."""
    assert sin_sitio_para_lo_nuevo(_con_pinza(tmp_path, [HACIA_ABAJO]), "plataforma") == []


def test_si_lo_que_viene_lleva_un_giro_tiene_que_caber_su_eje(tmp_path):
    """Con el dedo en el plan, la misma cara ya no vale: el defecto dice
    qué gira, cuánto necesita, cuánto hay y por qué caras sí cabe."""
    carpeta = _con_dedo(_con_pinza(tmp_path, [HACIA_ABAJO]))
    [defecto] = sin_sitio_para_lo_nuevo(carpeta, "plataforma")
    assert "«Pinza»" in defecto and "unión u4" in defecto
    assert "«Dedo»" in defecto and "unión u5" in defecto and "40 mm" in defecto
    hay = float(defecto.split("lo más que queda libre son ")[1].split(" mm")[0])
    assert 10.9 <= hay <= 14.5, "entre lo que hay en horizontal y la cuenta de arriba"
    caras = defecto.split("saliendo por la cara ")[1].split(" de esta pieza")[0]
    assert "+x" in caras, "por el eje de inclinación, hacia fuera: 79.6 mm"
    assert "-x" not in caras, "ahí está el soporte"
    assert "-z" not in caras, "es la cara de ahora"


def test_por_la_cara_de_fuera_cabe_el_eje_de_lo_que_viene(tmp_path):
    carpeta = _con_dedo(_con_pinza(tmp_path, [HACIA_FUERA]))
    assert sin_sitio_para_lo_nuevo(carpeta, "plataforma") == []


def test_un_giro_que_pide_poco_cabe_bajo_la_plataforma(tmp_path):
    """10 mm libres sí los hay: justo donde sale el tornillo quedan 14.3."""
    carpeta = _con_dedo(_con_pinza(tmp_path, [HACIA_ABAJO]), radio=10.0)
    assert sin_sitio_para_lo_nuevo(carpeta, "plataforma") == []


def test_a_la_pieza_hecha_se_le_dice_que_lo_que_viene_lleva_un_giro(tmp_path):
    from orchestrator import obra as O
    carpeta = _con_dedo(_con_pinza(tmp_path, []))
    [u4] = [u for u in O.uniones_del_nodo(carpeta, "plataforma") if u["id"] == "u4"]
    assert "«Dedo»" in u4["texto"] and "40 mm" in u4["texto"]
    sin_dedo = tmp_path / "otro"
    sin_dedo.mkdir()
    [u4] = [u for u in O.uniones_del_nodo(_con_pinza(sin_dedo, []), "plataforma")
            if u["id"] == "u4"]
    assert "girará" not in u4["texto"]


# --- de qué lado de los agujeros va la pieza que agarra -----------------------------------------
#
# En esa misma reanudación el soporte de la pinza se alineó con los agujeros
# de la plataforma (`punto()` da por dónde entra la cabeza) y se puso de ese
# lado. El recuento lee entonces el tornillo al revés: la cabeza en el fondo
# del inserto y la punta en el pasante, «sin agarrar en nada». Cinco intentos
# con ese mensaje no lo movieron: nadie le había dicho de qué lado iba.

def test_a_la_que_agarra_se_le_dice_por_donde_sale_el_tornillo(tmp_path):
    """HACIA_FUERA entra en x = 90 y la plataforma acaba en x = 100: el
    tornillo atraviesa 10 mm y sale por ahí. La pinza va de ese lado."""
    from orchestrator import obra as O
    carpeta = _con_pinza(tmp_path, [HACIA_FUERA])
    [u4] = [u for u in O.uniones_del_nodo(carpeta, "pinza") if u["id"] == "u4"]
    assert "10 mm" in u4["texto"] and "donde sale" in u4["texto"]
    assert "la cabeza" in u4["texto"]


def _pinza_puesta(lado):
    """La pinza con su inserto en línea con HACIA_EL_SERVO, que entra en la
    plataforma por x = 10 y sale por x = 2.5. La pinza coloca la plataforma
    en (−4.5, 0, −15): en su marco, entra por x = 5.5 y sale por x = −2.
    «salida»: el inserto empieza donde sale el tornillo y sigue. «cabeza»:
    empieza donde entra la cabeza y va hacia el otro lado."""
    en, eje = {"salida": ((-2, 0, 0), (-1, 0, 0)), "cabeza": ((5.5, 0, 0), (1, 0, 0))}[lado]
    inserto = {**_agujero("m3", en, eje=eje, d=4.1, metrica="M3", profundidad=6),
               "uso": "inserto"}
    return (["plataforma"], [_sobre("plataforma", (-4.5, 0, -15)), inserto],
            ([-20, -10, -10], [12, 10, 10]))


def test_la_pinza_puesta_donde_sale_el_tornillo_lleva_su_union(tmp_path):
    from orchestrator.medida import uniones_sin_hacer
    carpeta = _con_pinza(tmp_path, [HACIA_EL_SERVO], pinza=_pinza_puesta("salida"))
    assert uniones_sin_hacer(carpeta, "pinza") == []


def test_a_la_pinza_puesta_del_lado_de_la_cabeza_se_le_dice_que_esta_al_reves(tmp_path):
    from orchestrator.medida import uniones_sin_hacer
    carpeta = _con_pinza(tmp_path, [HACIA_EL_SERVO], pinza=_pinza_puesta("cabeza"))
    [defecto] = uniones_sin_hacer(carpeta, "pinza")
    assert "unión u4" in defecto and "al revés" in defecto
    assert "«Plataforma»" in defecto and "donde sale" in defecto


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
