"""Requisitos medidos dentro del bucle de diseño (F6.7 (lazo)).

En el banco (2026-11-04) las piezas que se construían fallaban en lo que
pedía el usuario: el patrón de Ø2 del SG90 desviado 4.1 mm, 2 de los 4
agujeros Ø3.3 del NEMA17. Lo medía el banco, después; el diseñador nunca se
enteraba. Aquí se mide con los rasgos con nombre del kit, al construir, y lo
que no cuadra vuelve al diseñador con los números.

Las distancias esperadas están hechas a mano: dos agujeros con entrada en
(0, 0, 5) y (27.8, 0, 5) están a 27.8 mm; si el segundo entra por otra cara,
(27.8, 0, 0) con eje z, la distancia que cuenta es la perpendicular al eje,
27.8, no la de los puntos de entrada.
"""

import json

import pytest
import yaml

from orchestrator.medida import defectos
from orchestrator.schemas.spec import Requisito


def _agujero(nombre, d, x, y, z=5.0, eje=(0, 0, -1)):
    return {"nombre": nombre, "tipo": "agujero", "diametro_mm": d,
            "entrada": [x, y, z], "eje": list(eje)}


def _req(valor, cantidad=None, separaciones=(), id="R1", texto="dos agujeros de 2 mm"):
    return Requisito(id=id, tipo="agujero", texto=texto, valor=valor, origen="usuario",
                     cantidad=cantidad, separaciones_mm=list(separaciones))


def test_agujeros_en_su_sitio_no_dan_defectos():
    rasgos = [_agujero("a", 2, 0, 0), _agujero("b", 2, 27.8, 0)]
    assert defectos([_req(2, 2, [27.8])], rasgos) == []


def test_faltan_agujeros_y_se_dice_cuantos_hay():
    """El NEMA17 del banco: pedía 4 de Ø3.3 y salieron 2."""
    rasgos = [_agujero("a", 3.3, 0, 0), _agujero("b", 3.3, 31, 0), _agujero("c", 22.4, 15, 15)]
    [d] = defectos([_req(3.3, 4, id="R3", texto="cuatro agujeros de 3.3 mm")], rasgos)
    assert "R3" in d and "4" in d and "hay 2" in d


def test_patron_desviado_dice_las_distancias_que_hay():
    """El SG90 del banco: los Ø2 tenían que estar a 27.8 y estaban a 23.7."""
    rasgos = [_agujero("a", 2, 0, 0), _agujero("b", 2, 23.7, 0)]
    [d] = defectos([_req(2, 2, [27.8])], rasgos)
    assert "27.8" in d and "23.7" in d


def test_la_separacion_se_mide_perpendicular_al_eje():
    rasgos = [_agujero("a", 2, 0, 0, z=5), _agujero("b", 2, 27.8, 0, z=0)]
    assert defectos([_req(2, 2, [27.8])], rasgos) == []


def test_un_diametro_que_no_esta_lista_los_que_hay():
    rasgos = [_agujero("a", 4.0, 0, 0)]
    [d] = defectos([_req(4.5, 1, texto="agujeros de 4.5 mm")], rasgos)
    assert "4.5" in d and "Ø4" in d


def test_lo_que_no_es_un_agujero_no_se_mide_aqui():
    """Una cota de fondo o un encaje no se sabe a qué eje va: eso es del
    banco y de F6.12 (techo), no de esta medida."""
    cota = Requisito(id="R1", tipo="cota", texto="200 mm de fondo", valor=200, origen="usuario")
    assert defectos([cota], []) == []


# --- sondas dentro del bucle (F6.12 (techo) llevado a F6.7 (lazo)) ----------------

def test_un_encaje_con_seccion_pide_una_ventana_y_siempre_se_mira_el_acabado():
    """Rejuzgada con las sondas, la corrida del 62 % daba 81 %, y lo que
    fallaba eran las aristas vivas y las ventanas de los servos: cosas que
    el diseñador nunca recibía como motivo, porque el bucle solo medía
    agujeros (2026-11-04)."""
    from orchestrator.banco import AristasVivas, Ventana
    from orchestrator.medida import sondas_de

    servo = Requisito(id="R1", tipo="encaje", texto="el servo mide 40.7 x 19.7 mm",
                      valor=40.7, origen="usuario", seccion_mm=[40.7, 19.7])
    sondas = sondas_de([servo])
    assert any(isinstance(s, AristasVivas) for s in sondas)
    [v] = [s for s in sondas if isinstance(s, Ventana)]
    assert (v.ancho_mm, v.alto_mm) == (40.7, 19.7)


def test_la_seccion_de_un_encaje_cubre_sus_cotas():
    peticion = "el cuerpo del servo mide 40.7 x 19.7 mm"
    servo = Requisito(id="R1", tipo="encaje", texto="el cuerpo del servo mide 40.7 x 19.7 mm",
                      origen="usuario", seccion_mm=[40.7, 19.7])
    from orchestrator.schemas.spec import errores_de_requisitos
    assert errores_de_requisitos([servo], peticion) == []


def test_un_componente_del_concepto_que_el_programa_no_coloca_es_un_defecto():
    """F6.11 (biblioteca): sin `kit.componente` no hay dónde meter el sensor
    para comprobar que cabe; el soporte del HC-SR04 dibujó el suyo con cajas."""
    from orchestrator.medida import componentes_sin_colocar, sondas_de
    colocado = {"nombre": "sensor", "tipo": "componente", "ficha": "hc-sr04",
                "en": [0, 0, 0], "giros": [], "entra_por": "+y"}
    [fallo] = componentes_sin_colocar(["hc-sr04", "raspberry-pi-4"], [colocado])
    assert "raspberry-pi-4" in fallo and "kit.componente" in fallo
    assert [s.tipo for s in sondas_de([], [colocado])] == [
        "aristas_vivas", "componente_cabe", "componente_entra"]


def test_colocar_una_pieza_vecina_no_obliga_a_quitar_su_hueco(monkeypatch):
    """Banco 1110-0128: a la polea del 608ZZ se le pedía colocar el soporte y
    «quita su hueco()», y el 608zz igual. La polea va 4 mm por encima del
    soporte (no hay hueco que quitar), y el 608zz no podía colocarlo: el kit
    lo rechaza porque lo monta el soporte. Cinco intentos, y salió sin colocar
    nada. Lo que monta otra pieza se pide con su mensaje, y una vecina basta
    colocarla."""
    from orchestrator.medida import componentes_sin_colocar
    monkeypatch.setenv("INTELLIPRINT_AJENOS", json.dumps({"608zz": {
        "cuantos": 0, "mensaje": "el 608zz ya lo monta «Soporte» (ficha obra-soporte)"}}))
    rodamiento, soporte = componentes_sin_colocar(["608zz", "obra-soporte"], [])
    assert "ficha obra-soporte" in rodamiento and "hueco" not in rodamiento
    assert "kit.componente(\"obra-soporte\"" in soporte and "solo va al lado" in soporte


@pytest.mark.parametrize("cuerpo", [
    {"nombre": "sg90: cuerpo", "monta": "sg90"},
    # Las fichas de antes no dicen «monta»: su nombre lleva delante el componente.
    {"nombre": "sg90: cuerpo"}])
def test_lo_que_viene_montado_en_la_pieza_vecina_ya_esta_colocado(tmp_path, monkeypatch, cuerpo):
    """La plataforma del pan-tilt (2026-11-09) iba y venía: colocaba el SG90
    del soporte y le faltaba el soporte; colocaba el soporte y le faltaba el
    SG90. El SG90 va montado en la ficha del soporte: colocar el soporte ya
    lo coloca."""
    from orchestrator.medida import componentes_sin_colocar
    (tmp_path / "obra-soporte.yaml").write_text(yaml.safe_dump({
        "id": "obra-soporte", "nombre": "Soporte", "origen": "impreso",
        "fuentes": [{"url": "p", "cita": "construida"}], "marco": "el suyo", "mira": "+z",
        "cuerpos": [{"nombre": "Soporte", "caja": [10, 10, 10], "en": [0, 0, 0]},
                    {**cuerpo, "caja": [22.8, 27.1, 12.4], "en": [-5.8, 0, 18.8]}]}),
        encoding="utf-8")
    monkeypatch.setenv("INTELLIPRINT_FICHAS", str(tmp_path))
    soporte = {"nombre": "soporte", "tipo": "componente", "ficha": "obra-soporte",
               "en": [0, 0, 0], "giros": [], "entra_por": "+y"}
    assert componentes_sin_colocar(["sg90", "obra-soporte"], [soporte]) == []
    assert componentes_sin_colocar(["hc-sr04"], [soporte]) != []


def test_con_el_minimo_del_perfil_el_bucle_mide_la_pared_mas_fina():
    """Banco `1105-2120`: una pared de 0.15 mm que solo vio el banco."""
    from orchestrator.banco import ParedMinima
    from orchestrator.medida import sondas_de
    [p] = [s for s in sondas_de([], [], pared_min_mm=0.8) if isinstance(s, ParedMinima)]
    assert p.min_mm == 0.8


# Los rasgos de la base del pan-tilt (2026-11-09), copiados de su rasgos.json.
# La pared fina de verdad, medida en FreeCAD, es de 0.25 mm en (5.7, 17.2, 13.1):
# la cara exterior de la brida (y = 17.2) contra el plano de la tuerca, cuyo
# eje va por y = 14, z = 13 con entrecaras 5.9 → 14 + 2.95 = 16.95. El
# agujero del tornillo, en el mismo eje, tiene radio 1.65: su superficie
# queda a 3.2 - 1.65 = 1.55 mm del punto, y no es lo que adelgaza la pared.
BASE_PAN_TILT = [
    {"nombre": "alojamiento_sg90", "tipo": "hueco", "desde": [-16.2, -6.3, 4.9],
     "hasta": [16.2, 6.3, 2031.8]},
    {"nombre": "brida_ranura", "tipo": "hueco", "desde": [-1.0, 5.7, 5.0],
     "hasta": [1.0, 17.7, 20.0]},
    {"nombre": "apriete", "tipo": "agujero", "diametro_mm": 3.3, "entrada": [-8.0, 14.0, 13.0],
     "eje": [1.0, 0.0, 0.0], "profundidad_mm": None, "tornillo": "M3"},
    {"nombre": "apriete_tuerca", "tipo": "tuerca", "entrecaras_mm": 5.9,
     "entrada": [8.0, 14.0, 13.0], "eje": [-1.0, 0.0, 0.0], "profundidad_mm": 3.0},
]


def test_la_pared_fina_dice_que_rasgo_la_adelgaza():
    """Con solo «(en 5.7, 17.2, 13.1)» el diseñador tiene que adivinar qué
    hueco es; el kit sabe dónde puso cada uno."""
    from orchestrator.medida import mensaje_de_pared
    m = mensaje_de_pared("la pared más fina mide 0.25 mm (en 5.7, 17.2, 13.1); se exige 0.8",
                         BASE_PAN_TILT, 0.8)
    assert "«apriete_tuerca»" in m
    assert "«apriete»" not in m and "brida_ranura" not in m and "alojamiento_sg90" not in m


def test_una_pared_fina_lejos_de_todo_rasgo_no_nombra_ninguno():
    from orchestrator.medida import mensaje_de_pared
    m = mensaje_de_pared("la pared más fina mide 0.5 mm (en 25.0, -20.0, 1.0); se exige 0.8",
                         BASE_PAN_TILT, 0.8)
    assert "«" not in m and "0.5 mm" in m


# --- «M5» es un tornillo, no un diámetro --------------------------------------------
# Proyecto del 608ZZ (2026-11-08): «dos tornillos M5 separados 20 mm» salió
# como requisito `agujero` de valor 5, y el bucle exigía un agujero de Ø5 por
# el que un M5 no pasa (un agujero FDM sale aún más pequeño). El agujero para
# un M5 es el pasante del perfil; la ISO 273 da 5.5 en la serie media.
AGUJEROS = {"M3_through_mm": 3.3, "M3_selftap_mm": 2.8, "M5_through_mm": 5.5}


def _m5(**kw):
    return _req(5.0, 2, [20.0], id="R4", texto="dos tornillos M5 separados 20 mm", **kw)


def test_el_agujero_de_un_m5_es_el_pasante_del_perfil():
    rasgos = [_agujero("a", 5.5, -10, 0), _agujero("b", 5.5, 10, 0)]
    assert defectos([_m5()], rasgos, AGUJEROS) == []


def test_un_agujero_de_5_para_un_m5_es_un_defecto_y_dice_como_hacerlo():
    rasgos = [_agujero("a", 5.0, -10, 0), _agujero("b", 5.0, 10, 0)]
    [d] = defectos([_m5()], rasgos, AGUJEROS)
    assert "Ø5.5" in d and 'tornillo("M5"' in d


def test_la_rosca_directa_tambien_vale_para_un_tornillo():
    rasgos = [_agujero("a", 2.8, 0, 0), _agujero("b", 2.8, 20, 0)]
    req = _req(3.0, 2, [20.0], texto="dos tornillos M3 a 20 mm")
    assert defectos([req], rasgos, AGUJEROS) == []


def test_un_diametro_que_no_es_la_metrica_se_sigue_midiendo_literal():
    """«agujeros de 3.3 para M3»: el 3.3 lo escribió el usuario."""
    rasgos = [_agujero("a", 3.3, 0, 0)]
    req = _req(3.3, 1, texto="agujero de 3.3 mm para un M3")
    assert defectos([req], rasgos, AGUJEROS) == []


def test_cada_tornillo_lleva_su_sonda_de_acceso_con_la_cabeza_iso_4762():
    """La cabeza Allen de un M5 mide Ø8.5 (ISO 4762, dk máx.); la de un M3,
    Ø5.5. Con avellanado, la cabeza es el avellanado."""
    from orchestrator.banco import AccesoTornillo
    from orchestrator.medida import sondas_de
    rasgos = [{**_agujero("m5", 5.5, 0, 4), "tornillo": "M5"},
              {**_agujero("m3", 3.3, 9, 4), "tornillo": "M3", "avellanado_mm": 6.5},
              _agujero("suelto", 2, 20, 4)]
    acceso = {s.nombre: s.diametro_mm for s in sondas_de([], rasgos)
              if isinstance(s, AccesoTornillo)}
    assert acceso == {"m5": 8.5, "m3": 6.5}


# --- una brida tiene que apretar algo ----------------------------------------------------
# Las dos bases del pan-tilt (2026-11-09) salieron «resueltas» con una brida
# que no apretaba el servo, y ninguna sonda lo veía. Rasgos copiados de sus
# rasgos.json; la cabeza del M3 entra por y = 34 hacia -y y la tuerca está
# en y = 21.8–24.2, en x = 35, z = 10. El alojamiento del servo llega a y = 18.5.
_SERVO = {"nombre": "alojamiento_sg90", "tipo": "hueco", "desde": [18.8, 5.9, -0.1],
          "hasta": [51.2, 18.5, 2026.8]}
_TUERCA = {"nombre": "tuerca_brida_m3", "tipo": "tuerca", "entrecaras_mm": 5.9,
           "entrada": [35.0, 21.8, 10.0], "eje": [0.0, 1.0, 0.0], "profundidad_mm": 2.4}
_RANURA_TUERCA = {"nombre": "ranura_tuerca_m3", "tipo": "hueco", "desde": [31.5, 21.8, 10.0],
                  "hasta": [38.5, 24.2, 19.5]}
_ALIVIO = {"nombre": "alivio_cable_atras", "tipo": "hueco", "desde": [28.0, 17.0, -1.0],
           "hasta": [36.0, 35.0, 4.5]}


def _tornillo(profundidad):
    return {"nombre": "pasante_brida_m3", "tipo": "agujero", "diametro_mm": 3.3,
            "entrada": [35.0, 34.0, 10.0], "eje": [0.0, -1.0, 0.0],
            "profundidad_mm": profundidad, "tornillo": "M3"}


def _ranura(y0):
    return {"nombre": "ranura_brida", "tipo": "hueco", "desde": [24.0, y0, 6.0],
            "hasta": [46.0, y0 + 2.0, 19.5]}


def test_una_brida_cuya_ranura_no_da_al_servo_no_aprieta():
    """La segunda base: el tornillo (y 34 → 19.8) cruza la ranura (26.8–28.8),
    pero entre la ranura y el servo (18.5) quedan 8.3 mm de bloque macizo."""
    from orchestrator.medida import bridas_que_no_aprietan
    [d] = bridas_que_no_aprietan([_SERVO, _TUERCA, _RANURA_TUERCA, _tornillo(14.2),
                                  _ranura(26.8), _ALIVIO])
    assert "«ranura_brida»" in d and "no da a ningún hueco" in d


def test_una_brida_cuyo_tornillo_no_cruza_la_ranura_no_aprieta():
    """La base corregida: la ranura (17.6–19.6) da al servo, pero el
    tornillo acaba en y = 20.4; cabeza y tuerca quedan del mismo lado."""
    from orchestrator.medida import bridas_que_no_aprietan
    [d] = bridas_que_no_aprietan([_SERVO, _TUERCA, _RANURA_TUERCA, _tornillo(13.6),
                                  _ranura(17.6), _ALIVIO])
    assert "«pasante_brida_m3»" in d and "cruzar" in d.casefold()


def test_una_brida_que_se_cierra_lejos_del_servo_no_aprieta():
    """La tercera base: la ranura en U (y 26.4–28.4, con dos brazos hasta el
    servo) deja entre ella y el servo una lengüeta con la tuerca; el tornillo
    (cabeza en y = 34) cruza la ranura y tira de la lengüeta hacia la cabeza,
    es decir, la APARTA del servo: el alojamiento se abre en vez de cerrarse.
    Lo que se cierra (y 24.3–28.4) no corta el servo (y 5.9–18.5)."""
    from orchestrator.medida import bridas_que_no_aprietan
    en_u = {"nombre": "ranura_brida", "tipo": "hueco", "desde": [24.0, 18.0, 6.0],
            "hasta": [46.0, 28.4, 19.5]}
    [d] = bridas_que_no_aprietan([_SERVO, _TUERCA, _RANURA_TUERCA, _tornillo(12.2), en_u,
                                  _ALIVIO])
    assert "«ranura_brida»" in d and "«alojamiento_sg90»" in d and "aparta" in d


def test_una_brida_que_corta_la_pared_y_cruza_el_tornillo_si_aprieta():
    """Una brida de verdad: la ranura corta la pared de detrás del servo en
    x = 39–41, de y = 18.5 (el alojamiento) a 34; el tornillo va en x, con
    la cabeza en x = 46 y la tuerca en x = 34, y la cruza."""
    from orchestrator.medida import bridas_que_no_aprietan
    ranura = {"nombre": "corte", "tipo": "hueco", "desde": [39.0, 18.5, 6.0],
              "hasta": [41.0, 34.0, 19.5]}
    tornillo = {"nombre": "apriete", "tipo": "agujero", "diametro_mm": 3.3,
                "entrada": [46.0, 26.0, 10.0], "eje": [-1.0, 0.0, 0.0],
                "profundidad_mm": 14.0, "tornillo": "M3"}
    tuerca = {"nombre": "tuerca", "tipo": "tuerca", "entrecaras_mm": 5.9,
              "entrada": [34.0, 26.0, 10.0], "eje": [-1.0, 0.0, 0.0], "profundidad_mm": 2.4}
    assert bridas_que_no_aprietan([_SERVO, ranura, tornillo, tuerca]) == []


def test_un_tornillo_sin_tuerca_en_la_pieza_no_es_una_brida():
    """Los M4 que fijan la base a la mesa no aprietan nada de la pieza."""
    from orchestrator.medida import bridas_que_no_aprietan
    m4 = {"nombre": "fijacion", "tipo": "agujero", "diametro_mm": 4.5,
          "entrada": [8.0, 28.0, 18.5], "eje": [0.0, 0.0, -1.0], "profundidad_mm": None,
          "tornillo": "M4"}
    assert bridas_que_no_aprietan([_SERVO, m4]) == []


# --- que quepa en la impresora (banco 1113-1330) ------------------------------------------------

CAMA = (235, 235, 250)   # la AnkerMake M5 de `config/printers/`


def test_una_torre_de_430_mm_no_cabe_en_una_impresora_de_250():
    """La torreta del brazo mediano salió de 126 × 90 × 430 y se dio por
    buena: nadie medía que cupiera. De pie pide 430 de alto y hay 250;
    tumbada, 430 de largo y hay 235."""
    from orchestrator.medida import no_cabe_en_la_impresora
    [defecto] = no_cabe_en_la_impresora([126.0, 90.0, 430.0], CAMA)
    assert "430" in defecto and "250" in defecto and "126 × 90 × 430" in defecto


@pytest.mark.parametrize("caja", [
    [225.0, 90.0, 20.0],     # el brazo superior de esa corrida, tumbado
    [100.0, 240.0, 20.0],    # 240 no cabe en la cama (235), pero sí de pie (250)
    [235.0, 250.0, 235.0],   # justa, girada
])
def test_lo_que_cabe_en_alguna_postura_cabe(caja):
    from orchestrator.medida import no_cabe_en_la_impresora
    assert no_cabe_en_la_impresora(caja, CAMA) == []


def test_dos_lados_que_solo_caben_de_pie_no_caben_a_la_vez():
    """240 × 240 × 20: de pie solo cabe uno de los dos lados de 240."""
    from orchestrator.medida import no_cabe_en_la_impresora
    assert len(no_cabe_en_la_impresora([240.0, 240.0, 20.0], CAMA)) == 1


# --- lo que el plan pide no puede ser un defecto -----------------------------------------
# Encargo 16, corrida 1114-0535 (2026-11-14): el soporte gastó sus cinco
# intentos entre dos avisos que se contradecían. Rasgos y requisitos copiados
# de su `rasgos.json` y su `spec.yaml`.
_TUERCA_DE_LA_CARCASA = {"nombre": "tuerca_carcasa_sup_izq", "tipo": "tuerca",
                         "entrecaras_mm": 5.9, "entrada": [-28.0, 68.0, 6.0],
                         "eje": [0.0, 0.0, -1.0], "profundidad_mm": 2.4, "metrica": "M3"}
_PASANTE_DE_LA_CARCASA = {"nombre": "pasante_tuerca_carcasa_sup_izq", "tipo": "agujero",
                          "diametro_mm": 3.3, "entrada": [-28.0, 68.0, 0.0],
                          "eje": [0.0, 0.0, 1.0], "profundidad_mm": None}


def test_la_tuerca_cautiva_que_pide_el_plan_no_es_una_brida():
    """El plan decía «Carcasa se atornilla a Soporte con 4 M3, con tuerca
    cautiva en Soporte», y a la pieza se le pedía `tuerca(...)` «y su agujero
    pasante en línea». Lo hizo, y volvió cinco veces «brida: aprietan
    material macizo»: un tornillo con su tuerca en la misma pieza se tomaba
    siempre por una brida. Esa tuerca espera el tornillo de otra pieza."""
    from orchestrator.medida import bridas_que_no_aprietan
    rasgos = [_PASANTE_DE_LA_CARCASA, _TUERCA_DE_LA_CARCASA]
    assert bridas_que_no_aprietan(rasgos, tuercas_del_plan=4) == []
    # Sin plan que la pida, sigue siendo una brida que no aprieta nada.
    [d] = bridas_que_no_aprietan(rasgos)
    assert "aprietan material macizo" in d


def test_las_tuercas_que_pide_el_plan_salen_de_las_uniones_de_la_pieza(tmp_path, monkeypatch):
    """Cuatro, las de la unión u2 del soporte: las que agarran AQUÍ con
    tuerca. Las de fuera (u1) y las que agarran en la otra pieza no cuentan."""
    from orchestrator.medida import tuercas_del_plan
    nodo = tmp_path / "nodos" / "soporte"
    nodo.mkdir(parents=True)
    (nodo / "uniones.json").write_text(json.dumps([
        {"tipo": "fija", "id": "u1", "cabeza": "soporte", "agarra": "exterior", "metrica": "M3",
         "cantidad": 4, "agarre": None, "papel": "cabeza", "otro": None},
        {"tipo": "fija", "id": "u2", "cabeza": "carcasa", "agarra": "soporte", "metrica": "M3",
         "cantidad": 4, "agarre": "tuerca", "papel": "agarra", "otro": "carcasa"},
        {"tipo": "fija", "id": "u3", "cabeza": "soporte", "agarra": "tapa", "metrica": "M3",
         "cantidad": 2, "agarre": "tuerca", "papel": "cabeza", "otro": "tapa"},
        {"tipo": "sujeta", "id": "nema17", "metrica": "M3", "cantidad": 4}]), encoding="utf-8")
    monkeypatch.setenv("INTELLIPRINT_UNIONES", str(nodo / "uniones.json"))
    assert tuercas_del_plan() == 4
    monkeypatch.delenv("INTELLIPRINT_UNIONES")
    assert tuercas_del_plan() == 0


def test_el_diametro_que_el_modelo_supuso_para_un_m3_es_el_del_perfil():
    """«sus cuatro tornillos M3» salió como requisito `agujero` de valor 3.2
    (origen: catálogo): un diámetro de memoria. En esta impresora el pasante
    de un M3 es 3.3, que es lo que pone `tornillo("M3")`. Con `tornillo` volvía
    «pide 4 agujeros de Ø3.2 y hay 0»; con `taladrar(3.2)`, «el plan pide 4
    tornillos M3 y no hay ninguno». El 3.2 no lo dijo nadie."""
    req = Requisito(id="R2", tipo="agujero", texto="sus cuatro tornillos M3", valor=3.2,
                    origen="catalogo", cantidad=4, separaciones_mm=[31.0])
    del_perfil = [_agujero(f"motor_{i}", 3.3, x, y)
                  for i, (x, y) in enumerate([(0, 0), (31, 0), (0, 31), (31, 31)])]
    assert defectos([req], del_perfil, AGUJEROS) == []
    de_memoria = [{**a, "diametro_mm": 3.2} for a in del_perfil]
    [d] = defectos([req], de_memoria, AGUJEROS)
    assert "Ø3.3" in d and 'tornillo("M3"' in d
