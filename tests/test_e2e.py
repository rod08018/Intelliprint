"""`intelliprint pieza` de extremo a extremo (F1.17 (verificación), marcador `llm`).

Llama a un modelo real y cuesta unos céntimos. Aislado con
INTELLIPRINT_WORKSPACE: nunca toca el workspace/ de verdad.

Hasta el 2026-11-11 esto pedía con `intelliprint new`, el grafo de LangGraph
que ya no usaba nadie —la web, Crafty y el banco piden con `pieza`—, y
exigía una línea de laminado que el diseño dejó de producir a propósito
(el usuario, 2026-11-09: se lamina al abrir PrusaSlicer). La prueba
obligatoria antes de cerrar una tarea medía un camino muerto. Ahora pide
como el banco: el flujo de pieza entero, con el concepto aprobado tal cual.

Lo esperado sale A MANO de la petición: un oráculo independiente del
sistema, no una salida suya. Se mide la pieza construida —envolvente,
alojamientos y patrón de agujeros— con el juez del banco (F6.1 (evaluación)).

Hasta el kit (F5.18 (kit)) se comparaba el volumen exacto de una placa
desnuda. Con el kit, el diseñador redondea las aristas y achaflana la base
a propósito (acabado de producto, contra la pata de elefante), y la placa
NEMA17 salió 44 mm³ por debajo de la cuenta: 30 del chaflán de 0.5 en el
perímetro y 20 de los redondeos. El volumen dejó de ser lo que se pidió;
los agujeros y la envolvente no.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.banco import Agujeros, Cilindro, Envolvente, extraer_hechos, juzgar
from orchestrator.config import load_env
from tests.test_fcstd_output import _visibilidad_gui
from tests.test_generators import _freecadcmd

INTELLIPRINT = str(Path(sys.executable).parent / "intelliprint")
_env = load_env(Path(".env"))


def _caja(x, y, z):
    return Envolvente(tipo="envolvente", min_mm=[x - 0.1, y - 0.1, z - 0.1],
                      max_mm=[x + 0.1, y + 0.1, z + 0.1])


def _cuadro(d, lado):
    return Agujeros(tipo="agujeros", diametro_mm=d,
                    patron_mm=[[0, 0], [lado, 0], [0, lado], [lado, lado]])


def _central(d):
    return Cilindro(tipo="cilindro", interior=True, nominal_mm=d,
                    diametro_min_mm=d - 0.1, diametro_max_mm=d + 0.1)


CASOS = [
    ("soporte para NEMA17: placa de 60x60x6 mm con taladro central de 22.4 mm "
     "y cuatro agujeros de 3.3 mm en cuadro de 31 mm",
     [_caja(60, 60, 6), _central(22.4), _cuadro(3.3, 31)]),
    ("placa de 40x40x5 mm con taladro central de 25 mm",
     [_caja(40, 40, 5), _central(25)]),
    ("placa de 80x50x4 mm con cuatro agujeros de 4.3 mm en cuadro de 40 mm",
     [_caja(80, 50, 4), _cuadro(4.3, 40)]),
]


@pytest.fixture
def workspace_corto():
    """Un workspace con la ruta más corta que da el sistema. Con `tmp_path`
    (`pytest-of-…/pytest-N/test_de_la_frase_a_la_pieza_pl1/`, 58 caracteres)
    la placa de 80 × 50 cayó cinco veces seguidas el 2026-11-11: el modelo
    tituló la pieza «placa_de_montaje_80x50x4_mm», y entre la carpeta del
    proyecto, la de la pieza y el temporal con el que FreeCAD guarda el
    `.FCStd`, la ruta pasó de los 260 caracteres de Windows («Failed to open
    file»). Con un título más corto, la misma prueba pasaba. En el contenedor
    no ocurre; esto solo corre en el host, que es donde se abre la ventana."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ip", ignore_cleanup_errors=True) as carpeta:
        yield Path(carpeta)


@pytest.mark.llm
@pytest.mark.skipif(not _env.get("DEEPSEEK_API_KEY"), reason="sin DEEPSEEK_API_KEY")
@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
@pytest.mark.parametrize("peticion,oraculo", CASOS)
def test_de_la_frase_a_la_pieza(workspace_corto, peticion, oraculo):
    tmp_path = workspace_corto
    proceso = subprocess.run(
        [INTELLIPRINT, "pieza", "--aprobar-concepto", peticion],
        capture_output=True, text=True, timeout=1800,
        env={**os.environ, "INTELLIPRINT_WORKSPACE": str(tmp_path)},
    )
    salida = proceso.stdout

    # Sin la línea de «✓», que se vea por qué, con el error del proceso: un
    # AttributeError de None no decía nada (2026-10-27).
    assert proceso.returncode == 0 and re.search(r"✓ .+ mm", salida), \
        f"{salida}\n--- stderr ---\n{proceso.stderr[-4000:]}"
    proyecto = next((tmp_path / "projects").iterdir())
    hechos = extraer_hechos(next(proyecto.glob("parts/*/*.step")), _freecadcmd(), None)
    fallos = [r.detalle for r in (juzgar(a, hechos) for a in oraculo) if r.estado != "cumple"]
    assert not fallos, f"{fallos}\n{salida}"

    assert "NO aparecen en la pieza" not in salida  # trazabilidad (F1.16 (trazabilidad))

    fcstd = next(proyecto.glob("parts/*/*.FCStd"))
    assert sum(_visibilidad_gui(fcstd).values()) == 1  # se verá al abrirlo
