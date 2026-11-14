"""La lista de materiales de un invento (F7.8 (inventario)).

Un robot es piezas impresas más lo que se compra. La web enseñaba cada pieza
suelta y nadie decía «esto lleva dos SG90». Lo esperado está contado a mano
en cada test, sobre una obra como el pan-tilt del 9 de noviembre.
"""

import json

from orchestrator.materiales import materiales
from tests.test_conjunto import _obra, _sg90, _sobre


def _agujero(nombre, en, metrica=None, d=3.3, profundidad=None, avellanado=None):
    r = {"nombre": nombre, "tipo": "agujero", "diametro_mm": d, "entrada": list(en),
         "eje": [0, 0, -1], "profundidad_mm": profundidad, "avellanado_mm": avellanado}
    return {**r, "tornillo": metrica} if metrica else r


def _pan_tilt(tmp_path):
    """La base y el soporte montan un SG90 cada uno. La plataforma vuelve a
    colocar el SG90 del soporte, en su mismo sitio, para dejarle hueco: no
    es un tercero."""
    girado = ((-5.8, 27.1, 18.8), [("x", 90)])
    return _obra(tmp_path, {
        "base": ([], [_sg90((23.6, 6, 0)),
                      _agujero("fijacion_1", (8, 28, 18.5), "M4", 4.5, avellanado=8),
                      _agujero("fijacion_2", (62, 28, 18.5), "M4", 4.5, avellanado=8),
                      _agujero("guia_oreja", (20.65, 12.2, 15.6), d=1.7, profundidad=8)],
                 ([0, 0, 0], [70, 34, 18.5])),
        "soporte": (["base"], [_sg90(*girado), _sobre("base", (-29.4, -12.2, -27.6))],
                    ([-28, -17, 0], [28, 17.5, 31.5])),
        "plataforma": (["soporte"], [_sg90(*girado), _sobre("soporte", (0, 0, 0)),
                                     _agujero("camara_1", (-15, -57, 3), "M3"),
                                     _agujero("camara_2", (15, -57, 3), "M3")],
                       ([-25, -70, 0], [25, -1, 31])),
    })


def test_lo_comprado_se_cuenta_una_vez_por_pieza_que_lo_monta(tmp_path):
    m = materiales(_pan_tilt(tmp_path))
    assert [(c["id"], c["cuantos"]) for c in m["comprado"]][0] == ("sg90", 2)
    assert "SG90" in m["comprado"][0]["nombre"]


def test_lo_comprado_lleva_cada_tornillo_contado_y_con_su_largo(tmp_path):
    """«En el BOM deben ir todas las cosas que no imprimo» (el usuario,
    2026-11-10). Hasta entonces decía «M3, M4», sin cuántos ni de qué largo.
    Contado a mano: dos M4 avellanados que fijan la base a la mesa (la base
    da 18.5 mm, el resto es de la mesa), dos M3 para la cámara (la
    plataforma da 3 mm en su caja: de z = 3 a z = 0), y el tornillo de la
    oreja del SG90, que viene con él: de 18.5 a 15.6 − 8, 10.9 mm."""
    m = materiales(_pan_tilt(tmp_path))
    assert [(c["nombre"], c["cuantos"]) for c in m["comprado"]] == [
        ("Micro servo SG90 (9 g)", 2),
        ("Tornillo M3 · 3 mm de pieza + lo que entre donde se fije", 2),
        ("Tornillo avellanado M4 · 18.5 mm de pieza + lo que entre donde se fije", 2),
    ]
    assert [(c["nombre"], c["cuantos"], c["viene_con"]) for c in m["incluido"]] == [
        ("Tornillo M2 de 10.9 mm", 1, "Micro servo SG90 (9 g)")]


def test_las_piezas_impresas_en_el_orden_de_la_obra_y_si_ya_se_imprimieron(tmp_path):
    carpeta = _pan_tilt(tmp_path)
    (carpeta / "nodos" / "base" / "lista.json").write_text(
        json.dumps({"impresa": True}), encoding="utf-8")
    m = materiales(carpeta)
    assert [(p["id"], p["impresa"]) for p in m["impresas"]] == [
        ("base", True), ("soporte", False), ("plataforma", False)]
    assert m["impresas"][0]["nombre"] == "Pieza base"


def test_una_pieza_suelta_tambien_tiene_materiales(tmp_path):
    """Un soporte de un MG996R lleva un MG996R, aunque no sea una obra."""
    parte = tmp_path / "parts" / "soporte"
    parte.mkdir(parents=True)
    (parte / "rasgos.json").write_text(json.dumps([
        {"nombre": "mg996r", "tipo": "componente", "ficha": "mg996r", "en": [0, 0, 0]},
        _agujero("perfil_1", (10, 0, 6), "M5", 5.5)]), encoding="utf-8")
    (parte / "envolvente.json").write_text(
        json.dumps({"min": [-30, -10, 0], "max": [30, 40, 6]}), encoding="utf-8")
    (tmp_path / "pieza.json").write_text(json.dumps({"title": "Soporte"}), encoding="utf-8")
    m = materiales(tmp_path)
    assert [(c["id"], c["cuantos"]) for c in m["comprado"]][0] == ("mg996r", 1)
    assert [c["nombre"] for c in m["comprado"]][1:] == [
        "Tornillo M5 · 6 mm de pieza + lo que entre donde se fije"]
    assert m["impresas"] == [{"id": "soporte", "nombre": "Soporte", "impresa": False}]


def test_lo_comprado_dice_donde_se_compra_si_su_ficha_lo_sabe(tmp_path):
    """«En los BOM agrega el link de compra de la reductora» (el usuario,
    2026-11-14). El enlace es el de la tienda donde se leyó su hoja, escrito
    aquí tal cual; lo que no tiene uno en su ficha (el MG996R) no lo inventa."""
    parte = tmp_path / "parts" / "hombro"
    parte.mkdir(parents=True)
    (parte / "rasgos.json").write_text(json.dumps([
        {"nombre": "reductora", "tipo": "componente", "ficha": "nema23-pg47-76", "en": [0, 0, 0]},
        {"nombre": "mg996r", "tipo": "componente", "ficha": "mg996r", "en": [80, 0, 0]},
    ]), encoding="utf-8")
    (parte / "envolvente.json").write_text(
        json.dumps({"min": [-40, -40, 0], "max": [120, 40, 8]}), encoding="utf-8")
    (tmp_path / "pieza.json").write_text(json.dumps({"title": "Hombro"}), encoding="utf-8")
    comprado = {c["id"]: c for c in materiales(tmp_path)["comprado"]}
    assert comprado["nema23-pg47-76"]["enlace"] == (
        "https://www.oyostepper.com/goods-311-Nema-23-Stepper-Motor-Bipolar-L%3D76mm-"
        "w-Gear-Ratio-47-1-Planetary-Gearbox.html")
    assert "enlace" not in comprado["mg996r"]
