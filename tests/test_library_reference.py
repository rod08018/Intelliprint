"""Pruebas contra modelos de referencia INDEPENDIENTES (library/models/reference).

Si el sistema diseña la pieza y también la referencia con los mismos
números, que encajen no prueba nada: es circular (lo señaló el usuario;
mismo fallo que ADR-011). Estos modelos los dibujó otra persona a partir
del objeto real, así que pueden contradecirnos.
"""

import math
from pathlib import Path

import pytest

from mech_toolkit.geometry import Frame, find_boss, find_holes_on_circle
from mech_toolkit.library_models import import_reference
from mech_toolkit.measure import extract_cylinders
from tests.test_fcstd_output import _visibilidad_gui
from tests.test_generators import _freecadcmd
from tests.test_measure_extract import _nema17

NEMA17_REF = Path("library/models/reference/nema17_40mm_obijuan.step")
CARA_FRONTAL_Z = 40.1  # medida en el propio modelo: fin de los M3, inicio del saliente
EJE_Z = [0, 0, 1]


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_la_referencia_cumple_las_cotas_normalizadas_de_la_cara_nema17():
    """NEMA 17 normaliza SOLO la cara de montaje. La altura del saliente
    (1.6 aquí, 2.0 en otros) y el largo del eje (20 aquí, 24 en otros)
    varían por fabricante; el soporte no debe depender de ellas."""
    caras = extract_cylinders(NEMA17_REF, _freecadcmd())
    cara = Frame(origin=[0, 0, CARA_FRONTAL_Z], axis=EJE_Z)

    assert 2 * find_boss(caras, cara).radius == pytest.approx(22.0)
    agujeros = find_holes_on_circle(caras, cara, pcd_mm=31 * math.sqrt(2))
    assert len(agujeros) == 4


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_soporte_generado_no_se_atraviesa_con_un_motor_que_no_disenamos(tmp_path):
    """Condición NECESARIA, no suficiente: intersección cero = no se
    atraviesan. Tocarse no es encajar: la holgura la comprueba
    tests/test_fit.py (F2.20). Este test solía llamarse "encaja" y daba por
    buena una holgura de cero."""
    import subprocess

    step_soporte = _nema17(tmp_path)
    script = tmp_path / "encaje.py"
    script.write_text(
        "import FreeCAD, Part\n"
        f"s = Part.read({str(step_soporte)!r})\n"
        f"m = Part.read({str(NEMA17_REF.resolve())!r})\n"
        f"m.translate(FreeCAD.Vector(0, 0, -{CARA_FRONTAL_Z}))\n"
        "print('ENCAJE %.6f' % s.common(m).Volume)\n"
    )
    salida = subprocess.run([_freecadcmd(), str(script)], capture_output=True,
                            text=True, timeout=180).stdout
    volumen = float(next(l for l in salida.splitlines() if l.startswith("ENCAJE")).split()[1])

    assert volumen == pytest.approx(0.0, abs=1e-6)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_fcstd_de_referencia_se_ve_y_queda_en_posicion_de_montaje(tmp_path):
    """Insert Component de FreeCAD solo acepta .FCStd, no STEP."""
    fcstd = tmp_path / "nema17.FCStd"
    modelo = import_reference(NEMA17_REF, fcstd, _freecadcmd(), dz=-CARA_FRONTAL_Z)

    assert list(_visibilidad_gui(fcstd).values()) == [True]
    assert modelo.zmin == pytest.approx(-CARA_FRONTAL_Z, abs=0.01)


# --- Integridad del corpus (cambio 4 del plan) -------------------------------

import hashlib  # noqa: E402

import yaml  # noqa: E402

REF = Path("library/models/reference")


def _manifiesto():
    return yaml.safe_load((REF / "manifest.yaml").read_text(encoding="utf-8"))["modelos"]


def test_cada_referencia_esta_sin_modificar():
    """Una referencia que el sistema pudiera regenerar dejaría de ser
    independiente. Un solo byte cambiado hace fallar esto."""
    for m in _manifiesto():
        real = hashlib.sha256((REF / m["archivo"]).read_bytes()).hexdigest()
        assert real == m["sha256"], f"{m['archivo']} ha cambiado desde que se descargó"


def test_no_hay_referencias_sin_procedencia():
    """Todo STEP de la carpeta está en el manifiesto con autor y licencia."""
    declarados = {m["archivo"] for m in _manifiesto()}
    for step in REF.glob("*.step"):
        assert step.name in declarados, f"{step.name} no tiene procedencia declarada"
    assert all(m["autor"] and m["licencia"] for m in _manifiesto())


# --- Lo que las referencias confirman o contradicen ---------------------------


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_608zz_real_tiene_las_cotas_que_usa_el_qa():
    """derive_assertions usa od=22 y width=7 para un asiento de 608. Aquí
    se confirman contra un rodamiento que no dibujamos."""
    caras = extract_cylinders(REF / "bearing_608zz.step", _freecadcmd())
    agujero = max((c for c in caras if c.internal), key=lambda c: c.radius)
    exterior = max((c for c in caras if not c.internal), key=lambda c: c.radius)

    assert 2 * agujero.radius == pytest.approx(8.0)
    assert 2 * exterior.radius == pytest.approx(22.0)
    assert agujero.length == pytest.approx(7.0)  # el ancho: la cara exterior es
    # más corta (6.5) por los chaflanes de los cantos


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_el_agujero_m3_del_perfil_esta_dentro_de_la_iso_273():
    """El M3 pasante del perfil tiene que caer entre el ajuste justo y el
    holgado de la norma. Hoy cae casi en el justo (3.26 < 3.3 < 3.49)."""
    perfil = yaml.safe_load(Path("config/printers/ankermake_m5_petg.yaml").read_text())
    nuestro = perfil["holes"]["M3_through_mm"]

    def diametro(nombre):
        return 2 * extract_cylinders(REF / f"iso273_m3_{nombre}.step", _freecadcmd())[0].radius

    assert diametro("close") <= nuestro <= diametro("loose")


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_un_tornillo_m3_real_pasa_por_el_agujero_del_perfil():
    perfil = yaml.safe_load(Path("config/printers/ankermake_m5_petg.yaml").read_text())
    cana = min(extract_cylinders(REF / "screw_m3x10_iso4762.step", _freecadcmd()),
               key=lambda c: c.radius)

    assert 2 * cana.radius < perfil["holes"]["M3_through_mm"]
