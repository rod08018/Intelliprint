"""El brazo mediano (F10.9 (mediano), ADR-021): la meta de la Fase 10.

Cuatro ejes con NEMA 17: la base por correa, el hombro y el codo por
cicloidal y la muñeca por correa; 350 mm de alcance y 300 g. Aquí está el
plan escrito a mano —el que tendría que salir del desglosador con la
petición del encargo 15— y sus cuentas de par, hechas a mano en gramos por
milímetro (1 N·m son 101 972 g·mm):

- Muñeca (a 80 mm de la punta): 300 × 80 + 16 g de tramo a 40 = 24 640.
- Codo (a 200): 300 × 200 + 24 g a 60 + el motor y el rodamiento de la
  muñeca, 288 g a 120 + 16 g a 160 = 98 560.
- Hombro (a 350): 300 × 350 + 30 g a 75 + el motor y la reductora del codo,
  335 g a 150 + 24 g a 210 + los 288 g de la muñeca a 270 + 16 g a 310 =
  245 260.
"""

from pathlib import Path

import pytest

from orchestrator.plan import validar_plan
from orchestrator.schemas.obra import Obra
from tests.test_plan_mecanico import AGUJEROS

G = 9.80665e-6
PLAN = {
    "titulo": "Brazo mediano de cuatro ejes", "carga_g": 300,
    "nodos": [
        {"id": "base", "nombre": "Base", "que_hace": "se atornilla al tablero y gira el brazo",
         "compra": ["608zz", "nema17"]},
        {"id": "torreta", "nombre": "Torreta", "que_hace": "gira sobre la base y aloja el hombro",
         "compra": ["nema17", "cicloidal-nema17-28"], "depende_de": ["base"]},
        {"id": "brazo", "nombre": "Brazo", "que_hace": "del hombro al codo, 150 mm",
         "compra": ["nema17", "cicloidal-nema17-10"], "depende_de": ["torreta"]},
        {"id": "antebrazo", "nombre": "Antebrazo", "que_hace": "del codo a la muñeca, 120 mm",
         "compra": ["608zz", "nema17"], "depende_de": ["brazo"]},
        {"id": "mano", "nombre": "Mano", "que_hace": "de la muñeca a la punta, 80 mm",
         "depende_de": ["antebrazo"]},
        {"id": "todo", "nombre": "El brazo", "tipo": "conjunto", "que_hace": "se mueve",
         "depende_de": ["base", "torreta", "brazo", "antebrazo", "mano"]},
    ],
    "uniones": [
        {"tipo": "fija", "id": "u1", "cabeza": "base", "agarra": "exterior", "metrica": "M3",
         "cantidad": 4},
        {"tipo": "gira", "id": "u2", "gira": "torreta", "sobre": "base", "componente": "608zz",
         "recorrido_grados": 180, "eje": "vertical",
         "movido_por": {"motor": "nema17", "tipo": "correa", "relacion": 4}},
        {"tipo": "gira", "id": "u3", "gira": "brazo", "sobre": "torreta",
         "componente": "cicloidal-nema17-28", "recorrido_grados": 180, "radio_libre_mm": 360,
         "eje": "horizontal", "brazo_mm": 350,
         "movido_por": {"motor": "nema17", "tipo": "reductora", "relacion": 28}},
        {"tipo": "gira", "id": "u4", "gira": "antebrazo", "sobre": "brazo",
         "componente": "cicloidal-nema17-10", "recorrido_grados": 180, "radio_libre_mm": 210,
         "eje": "horizontal", "brazo_mm": 200,
         "movido_por": {"motor": "nema17", "tipo": "reductora", "relacion": 10}},
        {"tipo": "gira", "id": "u5", "gira": "mano", "sobre": "antebrazo", "componente": "608zz",
         "recorrido_grados": 180, "eje": "horizontal", "brazo_mm": 80,
         "movido_por": {"motor": "nema17", "tipo": "correa", "relacion": 4}},
    ],
}


def test_el_plan_del_brazo_mediano_escrito_a_mano_vale():
    assert validar_plan(Obra(**PLAN), AGUJEROS) == ([], [])


def test_los_tres_motores_que_levantan_pueden_con_lo_suyo():
    """Lo que da cada uno, al 50 % de los 0,400 N·m del NEMA 17: la muñeca
    por correa 4:1 con 0,9 de rendimiento, 0,72; el codo por cicloidal 10:1
    con 0,65, 1,30; el hombro por cicloidal 28:1, 3,64. La base, de eje
    vertical, no carga peso y no sale."""
    from orchestrator.dimensionar import pares
    hombro, codo, muneca = pares(Obra(**PLAN))
    assert [p["union"] for p in (hombro, codo, muneca)] == ["u3", "u4", "u5"]
    assert muneca["pide_Nm"] == pytest.approx(24640 * G) and muneca["da_Nm"] == pytest.approx(0.72)
    assert codo["pide_Nm"] == pytest.approx(98560 * G) and codo["da_Nm"] == pytest.approx(1.30)
    assert hombro["pide_Nm"] == pytest.approx(245260 * G)
    assert hombro["da_Nm"] == pytest.approx(3.64)


def test_con_la_cicloidal_de_20_el_hombro_no_tiene_margen_para_lo_que_no_se_ha_pesado():
    """2,405 N·m de 2,60: un 7 %. Lo impreso está estimado en 0,2 g/mm, y un
    brazo para NEMA 17 pesará más: por eso el encargo pide la de 28."""
    from orchestrator.dimensionar import pares
    import copy
    plan = copy.deepcopy(PLAN)
    plan["nodos"][1]["compra"] = ["nema17", "cicloidal-nema17-20"]
    plan["uniones"][2].update(componente="cicloidal-nema17-20")
    plan["uniones"][2]["movido_por"]["relacion"] = 20
    hombro = pares(Obra(**plan))[0]
    assert 0.05 < 1 - hombro["pide_Nm"] / hombro["da_Nm"] < 0.10


def test_el_encargo_15_pide_lo_que_dice_su_peticion():
    from orchestrator.banco import cargar_encargos
    from orchestrator.componentes import mencionados
    [e] = [e for e in cargar_encargos(Path("tests/banco/encargos"))
           if e.nombre == "brazo_mediano_nema17"]
    assert sorted(a.relacion for a in e.oraculo if a.tipo == "reduccion") == [4, 10, 28]
    por_tipo = {a.tipo: a for a in e.oraculo}
    assert por_tipo["alcance"].minimo_mm == 350 == 150 + 120 + 80
    assert por_tipo["carga"].minimo_g == 300
    assert por_tipo["articulaciones"].ejes == ["vertical", "horizontal", "horizontal",
                                              "horizontal"]
    assert {"608zz", "nema17", "cicloidal-nema17-10", "cicloidal-nema17-28"} <= set(
        mencionados(e.peticion))
    assert "cicloidal-nema17-20" not in mencionados(e.peticion)


def test_las_cifras_de_la_pieza_vecina_y_de_lo_comprado_no_son_cotas_del_antebrazo(tmp_path):
    """Banco 1113-1330, la primera corrida del brazo mediano: el antebrazo
    (120 mm entre ejes) no pasó de los requisitos, tres veces: «la petición
    dice 150 mm y ningún requisito lleva ese valor». Los 150 son del brazo
    superior, que su petición nombra como pieza a la que se une. Y al brazo
    superior se le fue un intento en «40 mm», que es parte del nombre de la
    ficha del motor: «NEMA 17 (17HS4401, 40 mm)».

    De su petición, la única cota del antebrazo es la suya: 120."""
    from orchestrator import obra as O
    from orchestrator.traceability import requested_dimensions
    (tmp_path / "request.md").write_text("un brazo de cuatro ejes\n", encoding="utf-8")
    O.guardar(tmp_path, Obra(**PLAN), por="prueba")
    texto = O.peticion_del_nodo(tmp_path, "antebrazo")
    # Se le sigue contando a qué se une y qué lleva: lo lee el diseñador.
    assert "150 mm" in texto and "40 mm" in texto and "8 × 22 × 7" in texto
    assert requested_dimensions(texto) == [120]


def test_con_correas_y_reductoras_cada_reduccion_se_busca_donde_toca(tmp_path, monkeypatch):
    """El brazo mediano lleva correas de 4:1 y cicloidales de 28:1 y 10:1.
    Al pedir «4:1», que ninguna reductora sea de 4 no es un fallo: la correa
    lo es. Aquí, la articulación con correa de `test_correa`, haciendo como
    que además hay una reductora de 10 que no casa."""
    from orchestrator import banco
    from orchestrator.banco import Resultado
    from tests.test_banco import _juzgar_brazo
    from tests.test_correa import _con_correa
    monkeypatch.setattr(banco, "_por_reductora", lambda *a, **k: Resultado(
        estado="no_cumple", detalle="«Brazo» gira sobre una de 10:1, y se pide 4:1"))
    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "reduccion", "relacion": 4}],
                        "un brazo con una correa 4:1", brazo=_con_correa)
    assert r.estado == "cumple", r.detalle
    assert "80 dientes" in r.detalle
