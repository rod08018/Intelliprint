"""El ala volante vuela una misión en PX4 con Gazebo (F13.6 (simulación)).

Despega en vertical, pasa a avión, da una vuelta de casi 3 km, vuelve a
helicóptero y aterriza donde salió. Lo que se mide sale del dimensionado
(`scripts/avion_vtol.json`), no de la propia simulación: la pérdida, la
velocidad de crucero y la altura de la misión.

Corre dentro del contenedor de simulación, con el modelo ya generado:
    docker compose --profile sim run --rm sim pytest sim/pruebas -s

Volar en Gazebo no es volar: la aerodinámica es la de AeroSandbox metida en un
plugin lineal, las masas son estimaciones y los ajustes de PX4 son los del
standard_vtol. Que pase dice que el modelo es coherente y que PX4 sabe
llevarlo, no que el avión impreso vuele.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mision import ALTURA, DESPEGUE, EN_TIERRA, FW, MC, conectar, distancia, volar  # noqa: E402

SIM = Path(os.environ.get("INTELLIPRINT_SIM", "/sim"))
R = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))
REGISTROS = SIM / "registros"


@pytest.fixture(scope="module")
def vuelo():
    REGISTROS.mkdir(exist_ok=True)
    salida = open(REGISTROS / "px4.txt", "w", encoding="utf-8")
    px4 = subprocess.Popen(["bash", str(SIM / "volar.sh")], stdout=salida,
                           stderr=subprocess.STDOUT, start_new_session=True)
    try:
        v = conectar()
        volar(v)
        yield v
    finally:
        os.killpg(px4.pid, signal.SIGTERM)
        try:
            px4.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(px4.pid, signal.SIGKILL)
        salida.close()
        # El log de PX4 (ULog): es lo que dice por qué hizo lo que hizo.
        logs = sorted(Path(os.environ.get("PX4_DIR", "/opt/PX4-Autopilot")).glob(
            "build/px4_sitl_default/rootfs/log/*/*.ulg"), key=lambda p: p.stat().st_mtime)
        if logs:
            shutil.copy(logs[-1], REGISTROS / "vuelo.ulg")
        if "v" in locals():
            v.guardar(REGISTROS)


def _en(v, estado):
    return [s for s in v.muestras if s["vtol"] == estado and s["armado"]]


def test_despega_en_vertical(vuelo):
    subida = [s for s in _en(vuelo, MC) if s["item"] <= 0]
    assert max(s["alt"] for s in subida) > DESPEGUE * 0.8


def test_pasa_a_avion_y_vuela_como_avion_un_minuto_largo(vuelo):
    avion = _en(vuelo, FW)
    assert avion, f"nunca pasó a avión; PX4 dijo: {vuelo.textos[-10:]}"
    assert avion[-1]["t"] - avion[0]["t"] > 60


def test_como_avion_no_baja_de_la_mision_ni_entra_en_perdida(vuelo):
    # Fuera del primer medio minuto tras la transición, que es la subida a 50.
    avion = _en(vuelo, FW)
    crucero = [s for s in avion if s["t"] > avion[0]["t"] + 30]
    assert min(s["alt"] for s in crucero) > ALTURA - 15
    assert min(s["aire"] for s in crucero) > R["perdida_m_s"]


def test_no_se_estrella(vuelo):
    assert not [s for s in _en(vuelo, FW) if s["alt"] < 2], "se estrelló en modo avión"


def test_vuelve_y_aterriza_donde_salio(vuelo):
    final = vuelo.muestras[-1]
    assert final["suelo"] == EN_TIERRA
    assert distancia(vuelo.casa, (final["lat"], final["lon"])) < 10
