"""Las formas de un brazo industrial que genera el kit (F12.6 (forma), ADR-023).

Las siete piezas del brazo del encargo 18, cada una con una llamada, y
construidas en cadena: cada una contra la ficha de la anterior, como en un
backlog.

Lo esperado está contado a mano, con las hojas de lo comprado y con lo que se
le pide a cada llamada, no con lo que sale de construirlas:

- el tramo del hombro al codo son dos tambores a 190 mm: uno de 50 de radio
  (la reductora del hombro, de Ø56, más 22) y otro de 44 (la del codo más
  16), así que mide 50 + 190 + 44 = 284 de punta a punta y va de 135 a 419
  con el hombro a 185;
- la cara de la brida donde va la herramienta queda a lo que suman los
  tramos: 185 + 190 + 145 + 140 + 125 = 785 mm de la mesa;
- los tornillos son los de las hojas: cuatro M4 en el NEMA 23, cuatro M5 en
  cada motor con reductora y cuatro M3 en cada NEMA 17, más cuatro del
  tablero y cuatro en cada plato.
"""

import json
import os
from pathlib import Path

import pytest

from orchestrator.build import ConstruccionFallida, build_part
from orchestrator.schemas.programa import Programa
from tests.test_generators import _freecadcmd
from tests.test_sondas import PERFIL

pytestmark = pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")

PIEZAS = [
    ("base", "", "", "return kit.brazo_base(81.0)"),
    ("columna", "base", "-z", 'return kit.brazo_columna(abajo, "nema23-pg47-76", altura=185)'),
    ("tramo", "columna", "-y", 'return kit.brazo_tramo(abajo, 190, "nema23-pg47-56")'),
    ("antebrazo", "tramo", "+y", "return kit.brazo_antebrazo(abajo, 145)"),
    ("muneca", "antebrazo", "-z", "return kit.brazo_muneca(abajo, 140)"),
    ("mano", "muneca", "-y", "return kit.brazo_mano(abajo, 125)"),
    ("brida", "mano", "-z", "return kit.brazo_brida(abajo)"),
]
"""(pieza, la de abajo, por dónde le entra la de abajo, lo que devuelve)."""


def _programa(abajo, entra, devuelve):
    coloca = (f'    abajo = kit.componente("obra-{abajo}", en=(0, 0, 0), entra_por="{entra}")\n'
              if abajo else "")
    return f"def construir(kit):\n{coloca}    {devuelve}\n"


@pytest.fixture(scope="module")
def brazo(tmp_path_factory):
    """{pieza: su carpeta}, con las siete construidas una sobre otra."""
    from orchestrator.obra import fichar
    raiz = tmp_path_factory.mktemp("brazo")
    antes = os.environ.get("INTELLIPRINT_FICHAS")
    os.environ["INTELLIPRINT_FICHAS"] = str(raiz / "fichas")
    carpetas = {}
    try:
        for nombre, abajo, entra, devuelve in PIEZAS:
            carpeta = raiz / nombre
            build_part(Programa(part=nombre, codigo=_programa(abajo, entra, devuelve)), None,
                       carpeta, _freecadcmd(), perfil=PERFIL)
            fichar(carpeta, f"obra-{nombre}", nombre, raiz / "fichas", proyecto="prueba")
            carpetas[nombre] = carpeta
        yield carpetas
    finally:
        if antes is None:
            os.environ.pop("INTELLIPRINT_FICHAS", None)
        else:
            os.environ["INTELLIPRINT_FICHAS"] = antes


def _caja(carpeta):
    e = json.loads((carpeta / "envolvente.json").read_text(encoding="utf-8"))
    return e["min"], e["max"]


def test_el_tramo_mide_lo_que_sus_dos_tambores_y_la_distancia_entre_ejes(brazo):
    lo, hi = _caja(brazo["tramo"])
    assert lo[2] == pytest.approx(185 - 50, abs=0.1) and hi[2] == pytest.approx(185 + 190 + 44,
                                                                              abs=0.1)
    assert hi[0] - lo[0] == pytest.approx(100, abs=0.1)     # el tambor mayor, de 50 de radio
    assert hi[1] - lo[1] == pytest.approx(50, abs=0.1)      # su grosor


def test_la_cara_de_la_brida_queda_a_lo_que_suman_los_tramos(brazo):
    _, hi = _caja(brazo["brida"])
    assert hi[2] == pytest.approx(185 + 190 + 145 + 140 + 125, abs=0.1)


def test_las_siete_piezas_se_imprimen_sin_soportes(brazo):
    """Es lo que el modelo no conseguía: tres de sus siete piezas pedían
    soportes en el banco 1115-0523."""
    from orchestrator.voladizos import como_imprimir
    piden = {}
    for nombre, carpeta in brazo.items():
        postura, zonas = como_imprimir(carpeta / f"{nombre}.stl", PERFIL["overhang_max_deg"],
                                       PERFIL["bridge_max_mm"])
        if postura is None:
            piden[nombre] = min(len(z) for z in zonas.values())
    assert piden == {}


def test_cada_motor_y_cada_plato_lleva_sus_tornillos(brazo):
    cuenta = {}
    for carpeta in brazo.values():
        for r in json.loads((carpeta / "rasgos.json").read_text(encoding="utf-8")):
            if r.get("tornillo"):
                cuenta[r["tornillo"]] = cuenta.get(r["tornillo"], 0) + 1
    # M4: el NEMA 23 y el tablero. M5: hombro y codo. M3: tres NEMA 17, tres
    # platos (muñeca, mano y brida) y los cuatro de la herramienta.
    assert cuenta == {"M4": 8, "M5": 8, "M3": 12 + 12 + 4}


def test_lo_comprado_lo_coloca_la_forma_y_no_el_programa(brazo):
    """El programa no coloca el motor: si lo hiciera, la pieza llevaría dos."""
    def puestos(pieza):
        return sorted(r["ficha"] for r in json.loads(
            (brazo[pieza] / "rasgos.json").read_text(encoding="utf-8"))
            if r["tipo"] == "componente" and not r["ficha"].startswith("obra-"))
    assert puestos("base") == ["6810-2rs", "nema23"]
    assert puestos("tramo") == ["nema23-pg47-56"]
    assert puestos("mano") == ["cicloidal-nema17-10", "nema17"]


def test_un_hombro_demasiado_bajo_se_dice_con_la_altura_que_hace_falta(brazo, tmp_path):
    """La columna acaba 20 mm sobre la base (98) y el tambor del hombro, de
    100 de diámetro, necesita tener debajo los 10 en que la columna se abre
    y 5 más: 98 + 10 + 5 + 50 = 163 es poco, y con 120 no cabe."""
    os.environ["INTELLIPRINT_FICHAS"] = str(brazo["base"].parent / "fichas")
    codigo = _programa("base", "-z", 'return kit.brazo_columna(abajo, "nema23-pg47-76", altura=120)')
    with pytest.raises(ConstruccionFallida, match="queda bajo"):
        build_part(Programa(part="baja", codigo=codigo), None, tmp_path, _freecadcmd(),
                   perfil=PERFIL)
