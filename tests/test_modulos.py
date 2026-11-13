"""Los módulos impresos (F10.6 (módulo), ADR-021).

Una reductora no es una pieza ni algo que se compra: son varias piezas
que salen de una fórmula, más lo que hay que comprar para montarlas. El
backlog la ve como un componente —con su ficha, se coloca con
`kit.componente`— y al contar lo que hay que imprimir y comprar se abre en
lo que es de verdad.

El módulo de aquí está hecho a mano para la prueba: un tope de dos piezas
(una base de 30 × 30 × 5 y una tapa de Ø20 × 4) que lleva un rodamiento
608ZZ y dos pasadores.
"""

import json
from pathlib import Path

import pytest
import yaml

from tests.test_generators import _freecadcmd

PERFIL = yaml.safe_load(Path("config/printers/ankermake_m5_plamas.yaml").read_text(encoding="utf-8"))
ID = "tope-de-prueba"


def _tope(lado: float = 30.0):
    from orchestrator.modulos import Modulo
    return Modulo(
        id=ID,
        ficha={
            "id": ID, "nombre": "Tope de prueba", "origen": "modulo", "verificado": False,
            "fuentes": [{"url": "tests/test_modulos.py", "cita": "módulo hecho a mano"}],
            "marco": "Origen en una esquina de la base; la tapa encima, centrada.",
            "mira": "+z",
            "cuerpos": [{"nombre": "tope", "caja": [lado, lado, 9], "en": [0, 0, 0]}],
            "masa_g": 12,
        },
        piezas={
            "base": f"def construir(kit):\n    return kit.caja({lado}, {lado}, 5)\n",
            "tapa": "def construir(kit):\n    return kit.cilindro(20, 4)\n",
        },
        compras={"608zz": 1},
        otros={"Pasador de acero Ø4 × 20": 2},
    )


@pytest.fixture
def con_tope(tmp_path, monkeypatch):
    """Una biblioteca de módulos con el tope, en una carpeta temporal."""
    from orchestrator import modulos
    biblioteca = tmp_path / "modulos"
    biblioteca.mkdir()
    (biblioteca / f"{ID}.yaml").write_text(
        yaml.safe_dump({"id": ID, "generador": "tope", "parametros": {"lado": 30.0}}),
        encoding="utf-8")
    monkeypatch.setitem(modulos.GENERADORES, "tope", _tope)
    monkeypatch.setenv("INTELLIPRINT_MODULOS", str(biblioteca))
    return biblioteca


def test_un_modulo_tiene_ficha_como_cualquier_componente(con_tope):
    """Se ve en la lista de lo que se puede poner en `compra`, y su ficha
    dice lo que ocupa: 30 × 30 × 9."""
    from orchestrator.componentes import cargar, envolvente, ids
    assert ID in ids()
    f = cargar(ID)
    assert f.origen == "modulo" and f.masa_g == 12
    assert envolvente(f) == ([0, 0, 0], [30, 30, 9])


def test_sin_biblioteca_de_modulos_no_hay_ninguno_de_prueba():
    from orchestrator.componentes import ids
    assert ID not in ids()


def test_un_modulo_sin_generador_dice_cual_falta(con_tope):
    from orchestrator import modulos
    (con_tope / "raro.yaml").write_text(
        yaml.safe_dump({"id": "raro", "generador": "no-existe", "parametros": {}}),
        encoding="utf-8")
    with pytest.raises(KeyError, match="no-existe"):
        modulos.cargar("raro")


@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
def test_un_modulo_se_coloca_con_kit_componente(con_tope, tmp_path):
    """Una placa de 60 × 60 × 5 con el tope encima, y un bloque del tamaño
    que el kit dice que ocupa el tope, hundido medio milímetro en la placa
    para que sean una sola pieza: 18 000 + 30 × 30 × 9 − 30 × 30 × 0,5 =
    25 650 mm³, hasta z = 13,5."""
    from orchestrator.build import build_part
    from orchestrator.schemas.programa import Programa
    r = build_part(Programa(part="p", codigo=f'''
def construir(kit):
    pieza = kit.caja(60, 60, 5)
    tope = kit.componente("{ID}", en=(15, 15, 5))
    a, b = tope.envolvente()
    return pieza + kit.caja(b[0] - a[0], b[1] - a[1], b[2] - a[2], en=(a[0], a[1], a[2] - 0.5))
'''), None, tmp_path / "p", _freecadcmd(), perfil=PERFIL)
    [c] = [x for x in r.rasgos if x["tipo"] == "componente"]
    assert c["ficha"] == ID
    assert r.bbox_max[2] == pytest.approx(13.5) and r.volume_mm3 == pytest.approx(26100 - 450)


def _backlog_con_tope(tmp_path):
    from tests.test_conjunto import _obra
    tope = {"nombre": ID, "tipo": "componente", "ficha": ID, "en": [15, 15, 5], "giros": [],
            "entra_por": "+z"}
    carpeta = tmp_path / "projects" / "a"
    carpeta.mkdir(parents=True)
    _obra(carpeta, {"base": ([], [tope], ([0, 0, 0], [60, 60, 5]))})
    plan = json.loads((carpeta / "obra.json").read_text(encoding="utf-8"))
    plan["nodos"][0]["compra"] = [ID]
    (carpeta / "obra.json").write_text(json.dumps(plan), encoding="utf-8")
    return carpeta


def test_en_las_compras_el_modulo_se_abre_en_lo_que_es(con_tope, tmp_path):
    """Nadie compra un «tope de prueba»: se imprimen sus dos piezas y se
    compran un 608ZZ y dos pasadores."""
    from orchestrator.materiales import materiales
    m = materiales(_backlog_con_tope(tmp_path))
    comprado = {c["id"]: c["cuantos"] for c in m["comprado"]}
    assert ID not in comprado
    assert comprado["608zz"] == 1 and comprado["Pasador de acero Ø4 × 20"] == 2
    impresas = {p["id"]: p["nombre"] for p in m["impresas"]}
    assert f"{ID}/base" in impresas and f"{ID}/tapa" in impresas
    assert "Tope de prueba" in impresas[f"{ID}/base"]


@pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")
def test_las_piezas_del_modulo_se_construyen_en_el_proyecto(con_tope, tmp_path):
    """Para que entren en el zip y se puedan abrir en PrusaSlicer. La base
    son 30 × 30 × 5 = 4 500 mm³; se construyen una vez."""
    from orchestrator import modulos
    from orchestrator.web.versiones import piezas_de
    carpeta = _backlog_con_tope(tmp_path)
    hechas = modulos.construir(carpeta, _freecadcmd(), PERFIL)
    assert sorted(p.stem for p in hechas) == ["base", "tapa"]
    assert {p.relative_to(carpeta).as_posix() for p in hechas} == {
        f"modulos/{ID}/base/base.stl", f"modulos/{ID}/tapa/tapa.stl"}
    assert set(hechas) <= set(piezas_de(carpeta))
    informe = json.loads((carpeta / "modulos" / ID / "base" / "envolvente.json").read_text())
    assert informe["max"] == pytest.approx([30, 30, 5])
    assert modulos.construir(carpeta, _freecadcmd(), PERFIL) == []      # ya estaban
