"""El ala volante en Gazebo y PX4 (F13.6 (simulación)).

Lo que se le mide al generador (`sim/generar.py`) sin abrir Gazebo: que el
avión del modelo pesa y se equilibra como el del dimensionado, que los rotores
y los elevones están donde el dibujo y giran hacia donde PX4 espera, y que el
plugin de aerodinámica no lleva los mandos al revés. Los valores esperados
salen de cuentas a mano o del convenio de PX4, no del propio generador.
"""

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from sim import generar as G

R = json.loads(Path("scripts/avion_vtol.json").read_text(encoding="utf-8"))
AERO = json.loads(Path("sim/aero_vtol.json").read_text(encoding="utf-8"))
CG = R["equilibrio"]["con_carga"]["cg_mm"]


def _triangulo(*puntos):
    """Una malla de juguete: un triángulo por cada trío de puntos, en mm."""
    return np.array(puntos, dtype=float).reshape(-1, 3, 3)


# Lo impreso de juguete, para no depender de workspace/: un triángulo con su
# centro donde el dimensionado pone el de lo impreso, más las patas, tan
# pequeñas que su parte de la masa (que va con el área) no mueve el CG.
_X, _, _Z = next(c["en"] for c in R["diseno"]["dentro"] if c["id"] == "impreso")
IMPRESO = {"centro-3": _triangulo([_X - 100, -100, _Z], [_X + 100, -100, _Z], [_X, 200, _Z]),
           "pata-d": _triangulo([700, 380, -150], [701, 380, -150], [700, 381, -149]),
           "pata-i": _triangulo([700, -380, -150], [701, -380, -150], [700, -381, -149]),
           "deriva-d": _triangulo([600, 380, -140], [601, 380, -140], [600, 381, -139]),
           "deriva-i": _triangulo([600, -380, -140], [601, -380, -140], [600, -381, -139])}


@pytest.fixture(scope="module")
def modelo():
    return G.Modelo(R, AERO, IMPRESO)


def test_el_morro_va_hacia_delante_y_el_ala_derecha_a_la_derecha_de_ros():
    # Dibujo: x hacia atrás, y a la derecha, z arriba, en mm. ROS y Gazebo:
    # X adelante, Y a la IZQUIERDA, Z arriba, en m, con el origen en el CG.
    p = G.a_flu([CG[0] - 100, 500, CG[2] + 30], CG)
    assert p == pytest.approx([0.1, -0.5, 0.03])


def test_inercia_de_dos_masas_a_mano():
    # 1 kg a cada lado, a 1 m sobre Y: Ixx = Izz = 2·1·1² = 2 kg·m², Iyy = 0.
    masa, cg, tensor = G.inercia([(1.0, (0, 1, 0), np.zeros((3, 3))),
                                  (1.0, (0, -1, 0), np.zeros((3, 3)))])
    assert masa == 2 and cg == pytest.approx([0, 0, 0])
    assert np.diag(tensor) == pytest.approx([2, 0, 2])


def test_la_inercia_de_una_caja_es_la_de_los_libros():
    # Caja de 2 kg y 0,3 × 0,2 × 0,1 m: Ixx = m(b² + c²)/12.
    t = G.caja(2.0, (0.3, 0.2, 0.1))
    assert np.diag(t) == pytest.approx([2 * (0.04 + 0.01) / 12, 2 * (0.09 + 0.01) / 12,
                                        2 * (0.09 + 0.04) / 12])


def test_el_modelo_pesa_lo_del_dimensionado_con_todos_sus_eslabones(modelo):
    sdf = ET.fromstring(modelo.sdf())
    masas = [float(m.text) for m in sdf.iter("mass")]
    # El total del JSON va redondeado al gramo.
    assert sum(masas) == pytest.approx(R["masa_kg"]["total"], abs=1e-3)


def test_ningun_eslabon_tiene_masa_cero(modelo):
    # Con 6 decimales, el 1e-8 de un elevón se escribía «0.000000» y Gazebo
    # avisaba de que podía romperse (visto al arrancar PX4, 2026-11-16).
    sdf = ET.fromstring(modelo.sdf())
    assert all(float(m.text) > 0 for m in sdf.iter("mass"))
    urdf = ET.fromstring(modelo.urdf("file:///m"))
    assert all(float(m.get("value")) > 0 for m in urdf.iter("mass"))


def test_el_centro_de_gravedad_del_modelo_es_su_origen(modelo):
    # Las derivadas de la aerodinámica se toman en el CG con la carga: el
    # origen del modelo tiene que ser ese punto, o los momentos salen torcidos.
    assert modelo.cg_flu == pytest.approx([0, 0, 0], abs=0.003)


def test_el_tensor_de_inercia_es_fisico(modelo):
    t = modelo.tensor
    assert np.all(np.linalg.eigvalsh(t) > 0)
    ixx, iyy, izz = np.diag(t)
    # Un ala: alabear cuesta más que cabecear, y guiñar lo que los dos juntos.
    assert ixx > iyy and izz == pytest.approx(ixx + iyy, rel=0.25)


def test_los_rotores_de_px4_van_donde_en_el_dibujo():
    # PX4 los quiere en FRD desde el CG: X adelante, Y a la derecha. Delante
    # están en x = -53,4 mm y el CG en 312: 365,4 mm por delante.
    texto = G.airframe(R)
    d = float(R["rotores"]["x_delante"]) * 1000
    t = float(R["rotores"]["x_detras"]) * 1000
    esperados = {0: (CG[0] - d, 380), 1: (CG[0] - t, -380), 2: (CG[0] - d, -380),
                 3: (CG[0] - t, 380)}
    for n, (px, py) in esperados.items():
        assert f"CA_ROTOR{n}_PX {px / 1000:.4f}" in texto
        assert f"CA_ROTOR{n}_PY {py / 1000:.4f}" in texto


def test_los_rotores_giran_en_x_como_el_cuadricoptero_de_px4(modelo):
    # Delante derecha y detrás izquierda, antihorario (KM > 0); los otros dos,
    # horario. Es el orden de PX4 para un cuadricóptero en X.
    giros = {r["n"]: r["giro"] for r in modelo.rotores if r["n"] < 4}
    assert giros == {0: "ccw", 1: "ccw", 2: "cw", 3: "cw"}
    texto = G.airframe(R)
    for n, signo in ((0, ""), (1, ""), (2, "-"), (3, "-")):
        assert f"CA_ROTOR{n}_KM {signo}0.0" in texto


def test_cada_rotor_empuja_lo_que_dice_el_dimensionado(modelo):
    # Empuje = constante · ω²: a tope, 2,79 kg por rotor de sustentación.
    for r in modelo.rotores[:4]:
        assert r["k"] * r["w_max"] ** 2 == pytest.approx(
            R["vtol"]["empuje_max_por_motor_kg"] * 9.81, rel=0.01)
    texto = G.airframe(R)
    for n in range(1, 5):
        assert f"SIM_GZ_EC_MAX{n} {modelo.rotores[0]['w_max']:.0f}" in texto


def test_la_de_empuje_empuja_hacia_delante_desde_atras(modelo):
    e = modelo.rotores[4]
    assert e["pos"][0] < 0                 # detrás del CG
    assert e["eje"] == pytest.approx([1, 0, 0])
    assert "CA_ROTOR4_AX 1" in G.airframe(R)


def test_un_elevon_positivo_sube_el_borde_de_salida(modelo):
    # El convenio de PX4 (y del standard_vtol): salida positiva = borde de
    # salida arriba. Un punto 3 cm detrás de la bisagra, girado +0,1 rad.
    for b in modelo.bisagras:
        medio = (np.array(b["desde"]) + np.array(b["hasta"])) / 2
        borde = medio + np.array([-0.03, 0, 0])
        girado = G.girar(borde, medio, b["eje"], 0.1)
        assert girado[2] > borde[2], b["servo"]


def test_hay_cuatro_servos_dos_por_lado():
    lados = {b["servo"]: b["lado"] for b in G.Modelo(R, AERO, IMPRESO).bisagras}
    assert lados == {"servo_0": "i", "servo_1": "d", "servo_2": "i", "servo_3": "d"}


def test_bajar_el_elevon_izquierdo_alabea_a_la_derecha(modelo):
    # Física, no convenio: borde abajo en el ala izquierda, más sustentación a
    # ese lado, alabeo a la derecha (Cl > 0). En el plugin el ángulo entra en
    # grados por la dirección: borde abajo es ángulo negativo.
    sdf = ET.fromstring(modelo.sdf())
    for cs in sdf.iter("control_surface"):
        servo = cs.find("name").text
        lado = {b["servo"]: b["lado"] for b in modelo.bisagras}[servo]
        cl = -1.0 * float(cs.find("Cell_ctrl").text) * float(cs.find("direction").text)
        sube = -1.0 * float(cs.find("CL_ctrl").text) * float(cs.find("direction").text)
        assert (cl > 0) == (lado == "i"), servo
        assert sube > 0, servo        # borde abajo, más sustentación


def test_la_aerodinamica_equilibra_a_la_alfa_del_crucero():
    # La recta de Cm del plugin cruza el cero donde el dimensionado vuela.
    a = math.radians(R["crucero"]["alfa_grados"])
    assert AERO["Cem0"] + AERO["Cema"] * a == pytest.approx(0, abs=0.006)
    assert AERO["CL0"] + AERO["CLa"] * a == pytest.approx(R["crucero"]["CL"], rel=0.04)


def _param(texto, nombre):
    for linea in texto.splitlines():
        if linea.startswith(f"param set-default {nombre} "):
            return float(linea.split()[-1])
    raise AssertionError(f"{nombre} no está en la aeronave")


def test_px4_cree_la_misma_declinacion_que_el_mundo_de_gazebo():
    # Sexto vuelo (2026-11-16): en la primera esquina el rumbo de PX4 saltó
    # 150° durante un segundo («Compass 0 fault»), su velocidad del aire salió
    # negativa y metió gas a tope picando 14°; en vuelo recto iba 3° torcido
    # y en el quinto, 11° (lo que parecía un derrape). El mundo de PX4
    # (Tools/simulation/gz/worlds/default.sdf, v1.17.0) tiene un campo fijo,
    # en ENU, de 6e-6 2.3e-5 -4.2e-5 T: 14,6° de declinación. PX4 tomaba la
    # de Zúrich de su modelo terrestre (unos 3°). Oráculo: ese vector.
    texto = G.airframe(R)
    este, norte = 6e-06, 2.3e-05
    assert _param(texto, "EKF2_DECL_TYPE") == 0      # no buscarla por la posición
    assert _param(texto, "EKF2_MAG_DECL") == pytest.approx(
        math.degrees(math.atan2(este, norte)), abs=0.1)


def test_la_transicion_llega_a_la_velocidad_de_mezcla_antes_de_que_px4_la_aborte(modelo):
    # Primer vuelo en Gazebo (2026-11-16): con el 80 % de gas la hélice de
    # empuje daba 2,5 m/s² y a los 6 s de lazo abierto iba a 10,8 m/s de los
    # 12 de mezcla: PX4 abortó la transición («quad-chute»). A mano: el empuje
    # va con ω², y ω con el gas; la resistencia, la del crucero a esa velocidad.
    texto = G.airframe(R)
    e = modelo.rotores[4]
    gas = _param(texto, "VT_F_TRANS_THR")
    empuje = e["k"] * (gas * e["w_max"]) ** 2
    mezcla = _param(texto, "VT_ARSP_BLEND")
    resistencia = R["crucero"]["resistencia_N"] * (mezcla / R["crucero"]["velocidad_m_s"]) ** 2
    a = (empuje - resistencia) / R["masa_kg"]["total"]
    # Con la mitad de margen: el morro levantado, el viento y los rotores.
    assert 1.5 * mezcla / a < _param(texto, "VT_F_TR_OL_TM")
    assert _param(texto, "VT_F_TR_OL_TM") < _param(texto, "VT_TRANS_TIMEOUT")


def test_al_apagar_los_rotores_el_ala_ya_sostiene_el_avion():
    # Tercer vuelo en Gazebo (2026-11-16): los rotores se apagaron a 15,7 m/s
    # con el morro a 0°; el ala pedía 8° y el avión cayó 13 m y entró en
    # pérdida al levantarlo. A mano: sustentación = ½ρV²S·(CL0 + CLa·α) con la
    # velocidad de fin de transición y el cabeceo de PX4 en vuelo nivelado.
    texto = G.airframe(R)
    v = _param(texto, "VT_ARSP_TRANS")
    alfa = math.radians(_param(texto, "FW_PSP_OFF"))
    sustentacion = 0.5 * 1.2041 * v ** 2 * AERO["area"] * (AERO["CL0"] + AERO["CLa"] * alfa)
    assert sustentacion > R["masa_kg"]["total"] * 9.81
    assert alfa < AERO["alpha_stall"] / 2


def test_en_el_giro_mas_cerrado_no_entra_en_perdida():
    # Cuarto vuelo en Gazebo (2026-11-16): en el primer giro de 90° PX4 pidió
    # 50° de alabeo (el de su standard_vtol), se pasó a 60°, perdió la
    # velocidad y cayó de 47 m. A mano: alabeado φ, el ala sostiene 1/cos φ
    # veces el peso y la pérdida sube con la raíz.
    texto = G.airframe(R)
    phi = math.radians(_param(texto, "FW_R_LIM"))
    assert R["perdida_m_s"] / math.sqrt(math.cos(phi)) < _param(texto, "FW_AIRSPD_MIN")


def _cl_del_plugin(alfa, co):
    """El CL de AdvancedLiftDrag, copiado de su código (gz-sim 8): la recta y
    la placa plana después de la pérdida, mezcladas con una sigmoide de
    pendiente fija M = 15 que el SDF no deja cambiar."""
    m, s = 15.0, co["alpha_stall"]
    sigma = ((1 + math.exp(-m * (alfa - s)) + math.exp(m * (alfa + s)))
             / ((1 + math.exp(-m * (alfa - s))) * (1 + math.exp(m * (alfa + s)))))
    placa = 2 * math.copysign(1, alfa) * math.sin(alfa) ** 2 * math.cos(alfa)
    return (1 - sigma) * (co["CL0"] + co["CLa"] * alfa) + sigma * placa


def test_el_plugin_sustenta_como_el_dimensionado():
    # Quinto vuelo en Gazebo (2026-11-16): con la pérdida a 10,2° la sigmoide
    # del plugin restaba sustentación desde 0°: en crucero daba CL 0,39 en vez
    # de 0,49 (volaba recto a 8°) y no pasaba de 0,63. Con 30° de alabeo hacía
    # falta 0,56: entró en pérdida y cayó. El CL de crucero y el máximo son
    # los del dimensionado (AeroSandbox y el MH 60).
    crucero = _cl_del_plugin(math.radians(R["crucero"]["alfa_grados"]), AERO)
    assert crucero == pytest.approx(R["crucero"]["CL"], rel=0.06)
    maximo = max(_cl_del_plugin(math.radians(a / 10), AERO) for a in range(1, 400))
    assert maximo == pytest.approx(R["supuestos"]["clmax"], rel=0.05)


def test_el_airframe_mezcla_los_cuatro_elevones():
    texto = G.airframe(R)
    assert "CA_SV_CS_COUNT 4" in texto
    for n, (tipo, alabeo) in enumerate(((5, "-0.5"), (6, "0.5"), (5, "-0.5"), (6, "0.5"))):
        assert f"CA_SV_CS{n}_TYPE {tipo}" in texto
        assert f"CA_SV_CS{n}_TRQ_R {alabeo}" in texto
        assert f"CA_SV_CS{n}_TRQ_P 0.5" in texto
        assert f"SIM_GZ_SV_FUNC{n + 1} {201 + n}" in texto


def test_el_avion_aparece_apoyado_en_sus_patas(modelo):
    sdf = ET.fromstring(modelo.sdf())
    z = float(sdf.find("model/pose").text.split()[2])
    # Lo más bajo de las patas de juguete: z = -150 mm, con el CG a -29,6.
    assert z == pytest.approx((CG[2] - (-150)) / 1000, abs=0.002)


def test_el_urdf_tiene_un_eslabon_por_lo_que_se_mueve(modelo):
    urdf = ET.fromstring(modelo.urdf("file:///sim/modelos/intelliprint_vtol/meshes"))
    eslabones = {e.get("name") for e in urdf.iter("link")}
    articulaciones = {a.get("name"): a.get("type") for a in urdf.iter("joint")}
    assert len(eslabones) == 1 + 5 + 4
    assert sorted(t for t in articulaciones.values()) == ["continuous"] * 5 + ["revolute"] * 4
    masas = [float(m.get("value")) for m in urdf.iter("mass")]
    assert sum(masas) == pytest.approx(R["masa_kg"]["total"], abs=1e-3)
