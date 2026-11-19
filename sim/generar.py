"""El ala volante para Gazebo, ROS 2 y PX4 (F13.6 (simulación)).

Del dimensionado (`scripts/avion_vtol.json`), de su aerodinámica
(`sim/aero_vtol.json`, de `scripts/avion_vtol_aero.py`) y de las piezas
construidas, escribe:

- `sim/modelos/intelliprint_vtol/`: el modelo de Gazebo (SDF), con sus mallas;
- `sim/urdf/intelliprint_vtol.urdf`: el mismo avión para ROS 2 (RViz,
  robot_state_publisher);
- `sim/px4/4100_gz_intelliprint_vtol`: la aeronave de PX4 (SITL).

Lo escribió el asistente a mano (2026-11-16), con el `standard_vtol` y el
`advanced_plane` de PX4 v1.17.0 como referencia: no es nota del sistema.

Ejes. El dibujo va con x hacia atrás, y a la derecha y z arriba, en mm. Gazebo
y ROS, con X adelante, Y a la izquierda y Z arriba (FLU), en m; el origen del
modelo es el CG con la carga, que es donde AeroSandbox toma los momentos. Es
un giro de 180° alrededor de z. PX4 quiere las posiciones de los rotores en FRD
(X adelante, Y a la derecha) desde el CG.

Uso, desde el repo (en el PC o en la suite):
    python -m sim.generar workspace/projects/<carpeta> sim
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

G0 = 9.81
NOMBRE = "intelliprint_vtol"
AERONAVE = "4100_gz_intelliprint_vtol"

# Rotores. Lo que empuja cada uno sale del dimensionado; las vueltas a las que
# lo hace no, y son supuestos del asistente: una hélice de 13" a 6000 rpm y la
# de empuje de 10" a 9500 rpm. Solo reparten el empuje entre constante y ω².
W_SUSTENTACION = 628.0        # rad/s
W_EMPUJE = 1000.0             # rad/s
EMPUJE_DE_EMPUJE_KG = 2.5     # un motor 28xx con 10" en 6S; el crucero pide 0,45
# Par de la hélice contra empuje: el del x500 de PX4 (0,016 en Gazebo y 0,05
# para el reparto de PX4); no hay hoja de una hélice concreta.
PAR_GZ, KM_PX4 = 0.016, 0.05
MASA_ROTOR = 0.005            # la hélice como eslabón; el motor va en base_link
# Los elevones no tienen masa propia en el modelo: la suya va en base_link,
# como en el standard_vtol. Con masa, el control de posición de Gazebo los
# hace temblar.
MASA_ELEVON = 1e-8
LIMITE_ELEVON = 0.78          # rad: ±45°, el SIM_GZ_SV_MAXA de PX4


def limite_elevon(r):
    """Rad que puede ir cada elevón a cada lado: lo que dejan las piezas
    (`mandos.recorrido`, medido por `avion.recorrido_elevon` al dimensionar),
    sin pasar de ±45°. Con el corte recto de la versión 9 la esquina del
    elevón tocaba el ala a los 10,6° y Gazebo lo dejaba ir a 45 (comparado
    con el Stallion el 2026-11-18, F13.10 (mandos))."""
    libre = r["diseno"].get("mandos", {}).get("recorrido")
    return LIMITE_ELEVON if libre is None else math.radians(min(libre, 45.0))
TRAMO_MM = 160                # los tramos del ala en el kit (mech_toolkit/avion.py)
LARGO_VIGAS = 0.9             # m, las vigas compradas
DISCO_SOBRE_MOTOR = 30        # mm, del centro del motor al plano de la hélice
RADIO_PATA = 0.01             # m, la esfera de contacto en el pie de cada pata


# ------------------------------------------------------------------ geometría

def a_flu(p_mm, cg_mm):
    """Un punto del dibujo (mm, x atrás, y derecha, z arriba) en FLU (m) desde el CG."""
    return [-(p_mm[0] - cg_mm[0]) / 1000, -p_mm[1] / 1000, (p_mm[2] - cg_mm[2]) / 1000]


def girar(p, origen, eje, angulo):
    """Rodrigues: p girado `angulo` rad alrededor del eje que pasa por `origen`."""
    k = np.asarray(eje, float) / np.linalg.norm(eje)
    v = np.asarray(p, float) - np.asarray(origen, float)
    v = (v * math.cos(angulo) + np.cross(k, v) * math.sin(angulo)
         + k * np.dot(k, v) * (1 - math.cos(angulo)))
    return v + np.asarray(origen, float)


# ------------------------------------------------------------------- inercia

def caja(masa, lados):
    a, b, c = lados
    return np.diag([masa * (b * b + c * c) / 12, masa * (a * a + c * c) / 12,
                    masa * (a * a + b * b) / 12])


def barra(masa, largo, eje):
    """Una barra fina a lo largo del eje 0, 1 o 2."""
    t = np.zeros((3, 3))
    for i in range(3):
        if i != eje:
            t[i, i] = masa * largo ** 2 / 12
    return t


def inercia(cuerpos):
    """(masa, punto, tensor propio) → masa total, CG y tensor en el CG (Steiner)."""
    masa = sum(m for m, _, _ in cuerpos)
    cg = sum(m * np.asarray(p, float) for m, p, _ in cuerpos) / masa
    t = np.zeros((3, 3))
    for m, p, propio in cuerpos:
        r = np.asarray(p, float) - cg
        t += propio + m * (np.dot(r, r) * np.eye(3) - np.outer(r, r))
    return masa, cg, t


def _piel(masa, triangulos_m):
    """Lo impreso es piel fina: su masa va con la superficie, no con el volumen."""
    v = triangulos_m
    area = 0.5 * np.linalg.norm(np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), axis=1)
    c = v.mean(axis=1)
    m = masa * area / area.sum()
    cg = (m[:, None] * c).sum(0) / masa
    r = c - cg
    t = (m * (r ** 2).sum(1)).sum() * np.eye(3) - (m[:, None, None] * r[:, :, None]
                                                   * r[:, None, :]).sum(0)
    return masa, cg, t


def _impreso(masa, mallas, pesos=None):
    """La masa de lo impreso repartida pieza a pieza: cada una con lo que
    pesó (`masas.json` del proyecto), por su superficie. Sin pesos, toda por
    la superficie: así era cuando todo se contaba como piel de LW-PLA, pero
    las derivas y las patas llevan relleno y el cuerpo es de PETG: pesan más
    por cm² que un tramo de ala (pesado el 2026-11-16). Escalado para que sume `masa`, la del
    dimensionado."""
    if not pesos:
        return [_piel(masa, np.concatenate(list(mallas.values())))]
    total = sum(pesos[k] for k in mallas)
    return [_piel(masa * pesos[k] / total, t) for k, t in mallas.items()]


# -------------------------------------------------------------------- modelo

class Modelo:
    """El avión de la simulación: masas, rotores, bisagras y patas, en FLU."""

    def __init__(self, r, aero, impreso, pesos=None):
        self.r, self.aero = r, aero
        self.cg_mm = r["equilibrio"]["con_carga"]["cg_mm"]
        self.dentro = {c["id"]: c for c in r["diseno"]["dentro"]}
        self.impreso = impreso
        self.pesos = pesos
        self.masa, self.cg_flu, self.tensor = inercia(self._cuerpos())
        self.rotores = self._rotores()
        self.bisagras = self._bisagras()
        self.patas = self._patas()

    def _flu(self, p_mm):
        return a_flu(p_mm, self.cg_mm)

    def _cuerpos(self):
        cuerpos = []
        y_ala = self.r["estaciones"][3][0]       # los largueros llegan al último elevón
        for c in self.dentro.values():
            m, p = c["masa_kg"], self._flu(c["en"])
            if c["id"] == "impreso" and self.impreso:
                cuerpos += _impreso(m, {k: self._tri_flu(t) for k, t in self.impreso.items()},
                                    self.pesos)
            elif c["id"].startswith("larguero"):
                cuerpos.append((m, p, barra(m, 2 * y_ala, 1)))
            elif c["id"] == "vigas":
                y = self.r["rotores"]["y_viga"] * 1000
                for s in (1, -1):
                    q = self._flu([c["en"][0], s * y, c["en"][2]])
                    cuerpos.append((m / 2, q, barra(m / 2, LARGO_VIGAS, 0)))
            elif "caja" in c:
                cuerpos.append((m, p, caja(m, [x / 1000 for x in c["caja"]])))
            else:
                cuerpos.append((m, p, np.zeros((3, 3))))
        return cuerpos

    def _tri_flu(self, t):
        t = np.asarray(t, float)
        out = np.empty_like(t)
        out[..., 0] = -(t[..., 0] - self.cg_mm[0]) / 1000
        out[..., 1] = -t[..., 1] / 1000
        out[..., 2] = (t[..., 2] - self.cg_mm[2]) / 1000
        return out

    def _rotores(self):
        empuje = self.r["vtol"]["empuje_max_por_motor_kg"] * G0
        helice = self.r["diseno"]["rotores"]["helice"] / 2000
        rotores = []
        # El orden y el giro del cuadricóptero en X de PX4: 1 delante derecha
        # (antihorario), 2 detrás izquierda (antihorario), 3 delante izquierda
        # y 4 detrás derecha (horarios).
        orden = (("d", "delante", "ccw"), ("i", "detras", "ccw"), ("i", "delante", "cw"),
                 ("d", "detras", "cw"))
        for n, (lado, donde, giro) in enumerate(orden):
            c = self.dentro[f"motor-{lado}-{donde}"]["en"]
            rotores.append({"n": n, "nombre": f"rotor_{n}", "giro": giro, "eje": [0, 0, 1],
                            "pos": self._flu([c[0], c[1], c[2] + DISCO_SOBRE_MOTOR]),
                            "w_max": W_SUSTENTACION, "k": empuje / W_SUSTENTACION ** 2,
                            "km": KM_PX4 if giro == "ccw" else -KM_PX4, "radio": helice})
        c = self.dentro["motor-empuje"]["en"]
        rotores.append({"n": 4, "nombre": "rotor_empuje", "giro": "cw", "eje": [1, 0, 0],
                        "pos": self._flu(c), "w_max": W_EMPUJE,
                        "k": EMPUJE_DE_EMPUJE_KG * G0 / W_EMPUJE ** 2, "km": KM_PX4,
                        "radio": self.r["diseno"]["empuje"]["helice"] / 2000})
        return rotores

    def _estacion(self, y):
        """El borde de ataque, la altura y la cuerda del ala en |y| (m)."""
        est = self.r["estaciones"]
        y = abs(y)
        for a, b in zip(est, est[1:]):
            if a[0] - 1e-9 <= y <= b[0] + 1e-9:
                t = (y - a[0]) / (b[0] - a[0])
                return [a[k] + (b[k] - a[k]) * t for k in (1, 2, 3)]
        raise ValueError(y)

    def _bisagras(self):
        """Las cuatro bisagras, con los cortes de los tramos del kit."""
        est = self.r["estaciones"]
        y0, y1 = est[2][0], est[3][0]
        n = math.ceil((y1 - y0) * 1000 / TRAMO_MM - 1e-9)
        cortes = [y0 + (y1 - y0) * k / n for k in range(n + 1)]
        grupos = dict(zip(("interior", "exterior"), self.r["diseno"]["elevones"]))
        fraccion = self.r["diseno"]["elevon"][1]

        def punto(y, s):
            x, z, c = self._estacion(y)
            return self._flu([(x + fraccion * c) * 1000, s * y * 1000, z * 1000])

        bisagras = []
        # servo_0 y servo_2 a la izquierda (PX4: elevón izquierdo, tipo 5).
        for k, (cual, lado) in enumerate((("interior", "i"), ("interior", "d"),
                                          ("exterior", "i"), ("exterior", "d"))):
            g, s = grupos[cual], (1 if lado == "d" else -1)
            desde = punto(cortes[g[0] - 1], s)
            hasta = punto(cortes[g[-1]], s)
            eje = np.subtract(hasta, desde)
            eje = eje / np.linalg.norm(eje)
            # Positivo = borde de salida arriba, como en PX4: el eje mira a la
            # izquierda (+Y) y la regla de la mano derecha sube lo de detrás.
            if eje[1] < 0:
                eje = -eje
            bisagras.append({"servo": f"servo_{k}", "cual": cual, "lado": lado,
                             "mando": f"{cual}-{lado}", "desde": desde, "hasta": hasta,
                             "eje": list(eje), "piezas": [f"elevon-{lado}-{j}" for j in g]})
        return bisagras

    def _patas(self):
        """El punto más bajo de cada pata y cada deriva: el tren de aterrizaje.
        Desde el 2026-11-18 van pegadas bajo su góndola (`aletas`), y lo más
        bajo de la góndola es su pie."""
        patas = []
        aletas = self.r["diseno"]["rotores"].get("aletas")
        for id_, t in sorted(self.impreso.items()):
            if id_.startswith(("pata", "deriva")) or (aletas and id_.startswith("gondola")):
                v = self._tri_flu(t).reshape(-1, 3)
                patas.append(list(v[np.argmin(v[:, 2])]))
        return patas

    @property
    def altura(self):
        """A qué altura va el CG con el avión de pie en el suelo."""
        return -min(p[2] for p in self.patas) if self.patas else 0.3

    # -------------------------------------------------------------- escritura

    def _inercia_xml(self, masa, t, etiqueta="sdf"):
        if etiqueta == "urdf":
            return (f'<mass value="{masa:.6g}"/><inertia ixx="{t[0, 0]:.6f}" '
                    f'ixy="{t[0, 1]:.6f}" ixz="{t[0, 2]:.6f}" iyy="{t[1, 1]:.6f}" '
                    f'iyz="{t[1, 2]:.6f}" izz="{t[2, 2]:.6f}"/>')
        return (f"<mass>{masa:.6g}</mass><inertia><ixx>{t[0, 0]:.6f}</ixx>"
                f"<ixy>{t[0, 1]:.6f}</ixy><ixz>{t[0, 2]:.6f}</ixz><iyy>{t[1, 1]:.6f}</iyy>"
                f"<iyz>{t[1, 2]:.6f}</iyz><izz>{t[2, 2]:.6f}</izz></inertia>")

    @property
    def masa_base(self):
        return self.masa - MASA_ROTOR * len(self.rotores) - MASA_ELEVON * len(self.bisagras)

    def sdf(self):
        x = " ".join
        f = lambda v: x(f"{a:.5f}" for a in v)  # noqa: E731
        sensores = (Path(__file__).parent / "plantillas" / "sensores.xml").read_text(
            encoding="utf-8")
        superficie = ("<surface><contact><ode><kp>100000</kp><kd>1.0</kd><max_vel>0.1</max_vel>"
                      "<min_depth>0.001</min_depth></ode></contact><friction><ode><mu>0.8</mu>"
                      "<mu2>0.8</mu2></ode></friction></surface>")
        patas = "".join(
            f'<collision name="pata_{i}"><pose>{f([p[0], p[1], p[2] + RADIO_PATA])} 0 0 0</pose>'
            f"<geometry><sphere><radius>{RADIO_PATA}</radius></sphere></geometry>{superficie}"
            "</collision>" for i, p in enumerate(self.patas))
        partes = [
            f'<?xml version="1.0"?>\n<!-- Generado por sim/generar.py: no editar a mano. -->\n'
            f'<sdf version="1.10"><model name="{NOMBRE}">',
            f"<pose>0 0 {self.altura:.4f} 0 0 0</pose>",
            '<link name="base_link"><inertial>'
            f"<pose>{f(self.cg_flu)} 0 0 0</pose>{self._inercia_xml(self.masa_base, self.tensor)}"
            "</inertial>", patas,
            f'<visual name="cuerpo"><geometry><mesh><uri>model://{NOMBRE}/meshes/cuerpo.stl</uri>'
            "</mesh></geometry><material><ambient>0.85 0.85 0.8 1</ambient>"
            "<diffuse>0.85 0.85 0.8 1</diffuse></material></visual>",
            sensores, "</link>"]
        for ro in self.rotores:
            giro = "0 1.5707963 0" if ro["eje"][0] else "0 0 0"
            partes.append(
                f'<link name="{ro["nombre"]}"><pose>{f(ro["pos"])} {giro}</pose><inertial>'
                f'{self._inercia_xml(MASA_ROTOR, np.diag([1e-6, 1.7e-4, 1.7e-4]))}</inertial>'
                f'<visual name="{ro["nombre"]}_disco"><geometry><cylinder>'
                f'<radius>{ro["radio"]:.4f}</radius><length>0.004</length></cylinder></geometry>'
                "<material><ambient>0.1 0.1 0.1 1</ambient><diffuse>0.1 0.1 0.1 1</diffuse>"
                "</material><transparency>0.6</transparency></visual></link>"
                f'<joint name="{ro["nombre"]}_joint" type="revolute"><parent>base_link</parent>'
                f'<child>{ro["nombre"]}</child><axis><xyz>0 0 1</xyz><limit><lower>-1e16</lower>'
                "<upper>1e16</upper></limit></axis></joint>")
        for b in self.bisagras:
            medio = (np.array(b["desde"]) + np.array(b["hasta"])) / 2
            partes.append(
                f'<link name="elevon_{b["mando"]}"><inertial><pose>{f(medio)} 0 0 0</pose>'
                f'{self._inercia_xml(MASA_ELEVON, np.eye(3) * 1e-6)}</inertial>'
                f'<visual name="elevon_{b["mando"]}"><geometry><mesh>'
                f'<uri>model://{NOMBRE}/meshes/{b["servo"]}.stl</uri></mesh></geometry>'
                "<material><ambient>0.9 0.45 0.1 1</ambient><diffuse>0.9 0.45 0.1 1</diffuse>"
                "</material></visual></link>"
                f'<joint name="{b["servo"]}" type="revolute"><pose>{f(medio)} 0 0 0</pose>'
                f'<parent>base_link</parent><child>elevon_{b["mando"]}</child>'
                f'<axis><xyz>{f(b["eje"])}</xyz><limit><lower>{-limite_elevon(self.r)}</lower>'
                f"<upper>{limite_elevon(self.r)}</upper></limit><dynamics><damping>1.0</damping>"
                "</dynamics></axis><physics><ode><implicit_spring_damper>1"
                "</implicit_spring_damper></ode></physics></joint>"
                '<plugin filename="gz-sim-joint-position-controller-system" '
                'name="gz::sim::systems::JointPositionController">'
                f'<joint_name>{b["servo"]}</joint_name><sub_topic>{b["servo"]}</sub_topic>'
                "</plugin>")
        partes.append(self._aerodinamica())
        for ro in self.rotores:
            partes.append(
                '<plugin filename="gz-sim-multicopter-motor-model-system" '
                'name="gz::sim::systems::MulticopterMotorModel">'
                f'<jointName>{ro["nombre"]}_joint</jointName><linkName>{ro["nombre"]}</linkName>'
                f'<turningDirection>{ro["giro"]}</turningDirection>'
                "<timeConstantUp>0.0125</timeConstantUp><timeConstantDown>0.025</timeConstantDown>"
                f'<maxRotVelocity>{ro["w_max"]:.0f}</maxRotVelocity>'
                f'<motorConstant>{ro["k"]:.6e}</motorConstant>'
                f"<momentConstant>{PAR_GZ}</momentConstant>"
                "<commandSubTopic>command/motor_speed</commandSubTopic>"
                f'<motorNumber>{ro["n"]}</motorNumber>'
                "<rotorDragCoefficient>0.000106428</rotorDragCoefficient>"
                "<rollingMomentCoefficient>1e-06</rollingMomentCoefficient>"
                "<rotorVelocitySlowdownSim>20</rotorVelocitySlowdownSim>"
                "<motorType>velocity</motorType></plugin>")
        partes.append("</model></sdf>\n")
        return "\n".join(partes)

    def _aerodinamica(self):
        """AdvancedLiftDrag con las derivadas de AeroSandbox, en el CG.

        Los mandos: AeroSandbox los da por grado de borde de salida ABAJO y la
        articulación de Gazebo es positiva con el borde ARRIBA (la de PX4):
        dirección −1."""
        a = self.aero
        claves = ["CL0", "AR", "eff", "CLa", "CD0", "Cem0", "Cema", "CYb", "Cellb", "Cenb",
                  "CDp", "CYp", "CLp", "Cellp", "Cemp", "Cenp", "CDq", "CYq", "CLq", "Cellq",
                  "Cemq", "Cenq", "CDr", "CYr", "CLr", "Cellr", "Cemr", "Cenr", "alpha_stall",
                  "CLa_stall", "CDa_stall", "Cema_stall", "area", "mac"]
        xml = ['<plugin filename="gz-sim-advanced-lift-drag-system" '
               'name="gz::sim::systems::AdvancedLiftDrag"><a0>0.0</a0>']
        xml += [f"<{c}>{a[c]:.6g}</{c}>" for c in claves]
        xml.append("<cp>0 0 0</cp><air_density>1.2041</air_density><forward>1 0 0</forward>"
                   "<upward>0 0 1</upward><link_name>base_link</link_name>"
                   f"<num_ctrl_surfaces>{len(self.bisagras)}</num_ctrl_surfaces>")
        for i, b in enumerate(self.bisagras):
            d = a["mandos_por_grado_borde_abajo"][b["mando"]]
            xml.append(f'<control_surface><name>{b["servo"]}</name><index>{i}</index>'
                       "<direction>-1</direction>"
                       + "".join(f"<{c}>{d[c]:.6g}</{c}>" for c in
                                 ("CD_ctrl", "CY_ctrl", "CL_ctrl", "Cell_ctrl", "Cem_ctrl",
                                  "Cen_ctrl")) + "</control_surface>")
        xml.append("</plugin>")
        return "".join(xml)

    def urdf(self, mallas):
        """El mismo avión para ROS 2: `mallas` es la carpeta de las mallas (una URI)."""
        f = lambda v: " ".join(f"{a:.5f}" for a in v)  # noqa: E731
        partes = [
            '<?xml version="1.0"?>\n<!-- Generado por sim/generar.py: no editar a mano. -->\n'
            f'<robot name="{NOMBRE}">',
            f'<link name="base_link"><inertial><origin xyz="{f(self.cg_flu)}" rpy="0 0 0"/>'
            f'{self._inercia_xml(self.masa_base, self.tensor, "urdf")}</inertial>'
            f'<visual><geometry><mesh filename="{mallas}/cuerpo.stl"/></geometry></visual>'
            "</link>"]
        for ro in self.rotores:
            rpy = "0 1.5707963 0" if ro["eje"][0] else "0 0 0"
            partes.append(
                f'<link name="{ro["nombre"]}"><inertial><origin xyz="0 0 0"/>'
                f'{self._inercia_xml(MASA_ROTOR, np.diag([1e-6, 1.7e-4, 1.7e-4]), "urdf")}'
                f'</inertial><visual><geometry><cylinder radius="{ro["radio"]:.4f}" '
                'length="0.004"/></geometry></visual></link>'
                f'<joint name="{ro["nombre"]}_joint" type="continuous"><parent link="base_link"/>'
                f'<child link="{ro["nombre"]}"/><origin xyz="{f(ro["pos"])}" rpy="{rpy}"/>'
                '<axis xyz="0 0 1"/></joint>')
        for b in self.bisagras:
            medio = (np.array(b["desde"]) + np.array(b["hasta"])) / 2
            partes.append(
                f'<link name="elevon_{b["mando"]}"><inertial><origin xyz="0 0 0"/>'
                f'{self._inercia_xml(MASA_ELEVON, np.eye(3) * 1e-6, "urdf")}</inertial>'
                f'<visual><origin xyz="{f(-medio)}" rpy="0 0 0"/><geometry>'
                f'<mesh filename="{mallas}/{b["servo"]}.stl"/></geometry></visual></link>'
                f'<joint name="{b["servo"]}" type="revolute"><parent link="base_link"/>'
                f'<child link="elevon_{b["mando"]}"/><origin xyz="{f(medio)}" rpy="0 0 0"/>'
                f'<axis xyz="{f(b["eje"])}"/><limit lower="{-limite_elevon(self.r)}" '
                f'upper="{limite_elevon(self.r)}" effort="1" velocity="10"/></joint>')
        partes.append("</robot>\n")
        return "\n".join(partes)

    # ----------------------------------------------------------------- mallas

    def mallas(self):
        """Las mallas en FLU: el cuerpo y un elevón por servo (con el origen del modelo)."""
        de_elevon = {p: b["servo"] for b in self.bisagras for p in b["piezas"]}
        grupos = {"cuerpo": []}
        for id_, t in sorted(self.impreso.items()):
            grupos.setdefault(de_elevon.get(id_, "cuerpo"), []).append(self._tri_flu(t))
        return {k: np.concatenate(v) for k, v in grupos.items() if v}


def airframe(r):
    """La aeronave de PX4 (SITL con Gazebo), sobre la 4004 (standard_vtol)."""
    m = Modelo(r, {}, {})
    lineas = [
        "#!/bin/sh",
        "#",
        "# @name Intelliprint: ala volante VTOL (F13.6 (simulación))",
        "#",
        "# @type Standard VTOL",
        "#",
        "# Generado por sim/generar.py: no editar a mano. Sobre la 4004 de PX4",
        "# v1.17.0 (standard_vtol). Cuatro rotores de sustentación en X, uno de",
        "# empuje y cuatro elevones, dos por lado.",
        "",
        ". ${R}etc/init.d/rc.vtol_defaults",
        "",
        "PX4_SIMULATOR=${PX4_SIMULATOR:=gz}",
        "PX4_GZ_WORLD=${PX4_GZ_WORLD:=default}",
        f"PX4_SIM_MODEL=${{PX4_SIM_MODEL:={NOMBRE}}}",
        "",
        "param set-default SIM_GZ_EN 1",
        "param set-default SENS_EN_ARSPDSIM 1",
        # La declinación del mundo de PX4 (default.sdf: campo fijo, en ENU,
        # 6e-6 2.3e-5 -4.2e-5 T), no la de Zúrich que PX4 busca por la
        # posición (unos 3°). Con la de Zúrich el rumbo iba 11° torcido y en
        # la primera esquina del sexto vuelo saltó 150°: velocidad del aire
        # negativa (se calcula con ese rumbo), gas a tope y picado de 14°.
        "param set-default EKF2_DECL_TYPE 0",
        f"param set-default EKF2_MAG_DECL {math.degrees(math.atan2(6e-06, 2.3e-05)):.1f}",
        "param set-default FD_ACT_EN 0",
        "param set-default FD_ACT_MOT_TOUT 500",
        "param set-default FD_ESCS_EN 0",
        "param set-default CA_AIRFRAME 2",
        "param set-default COM_PREARM_MODE 2",
        "param set-default COM_RC_IN_MODE 1",
        "",
        f"param set-default CA_ROTOR_COUNT {len(m.rotores)}",
    ]
    for ro in m.rotores:
        n, p = ro["n"], ro["pos"]
        # FRD desde el CG: X como FLU, Y al revés.
        lineas += [f"param set-default CA_ROTOR{n}_PX {p[0]:.4f}",
                   f"param set-default CA_ROTOR{n}_PY {-p[1]:.4f}",
                   f"param set-default CA_ROTOR{n}_KM {ro['km']}"]
        if ro["eje"][0]:
            lineas += [f"param set-default CA_ROTOR{n}_AX 1",
                       f"param set-default CA_ROTOR{n}_AZ 0"]
        lineas += [f"param set-default SIM_GZ_EC_FUNC{n + 1} {101 + n}",
                   f"param set-default SIM_GZ_EC_MIN{n + 1} 0",
                   f"param set-default SIM_GZ_EC_MAX{n + 1} {ro['w_max']:.0f}"]
    lineas += ["", f"param set-default CA_SV_CS_COUNT {len(m.bisagras)}"]
    for n, b in enumerate(m.bisagras):
        # Elevón izquierdo (5) y derecho (6). Salida positiva = borde arriba:
        # morro arriba los dos; alabear a la derecha baja el borde izquierdo.
        izq = b["lado"] == "i"
        lineas += [f"param set-default CA_SV_CS{n}_TYPE {5 if izq else 6}",
                   f"param set-default CA_SV_CS{n}_TRQ_R {'-0.5' if izq else '0.5'}",
                   f"param set-default CA_SV_CS{n}_TRQ_P 0.5",
                   f"param set-default SIM_GZ_SV_FUNC{n + 1} {201 + n}"]
    perdida = r["perdida_m_s"]
    crucero = r["crucero"]["velocidad_m_s"]
    # El crucero pide su resistencia a la hélice de empuje; ω va con la raíz.
    trim = math.sqrt(r["crucero"]["resistencia_N"] / (EMPUJE_DE_EMPUJE_KG * G0))
    # Colgado: empuje/peso de los motores comprados (antes era un supuesto
    # del dimensionado, 1,8), también con la raíz.
    hover = math.sqrt(1 / r["vtol"]["empuje_sobre_peso"])
    lineas += [
        "",
        "param set-default VT_TYPE 2",
        "param set-default VT_FWD_THRUST_EN 4",
        # Con 0,8 de gas la de empuje daba 2,5 m/s² y a los 6 s de lazo
        # abierto de PX4 no llegaba a la mezcla: abortó la transición en el
        # primer vuelo en Gazebo (2026-11-16). A tope son 3,7 m/s² y 3,2 s.
        "param set-default VT_F_TRANS_THR 1.0",
        "param set-default VT_F_TR_OL_TM 8",
        "param set-default VT_TRANS_TIMEOUT 15",
        # Los rotores se apagaban a 15,7 m/s con el morro a 0°: el ala pedía
        # 8° y el avión cayó 13 m y entró en pérdida al levantarlo (tercer
        # vuelo en Gazebo, 2026-11-16). Ahora se apagan a la velocidad de
        # crucero, con el cabeceo del crucero y un grado más.
        f"param set-default VT_ARSP_TRANS {crucero:.0f}",
        f"param set-default VT_ARSP_BLEND {perdida + 1:.0f}",
        f"param set-default FW_PSP_OFF {round(r['crucero']['alfa_grados']) + 1}",
        f"param set-default FW_AIRSPD_STALL {perdida:.0f}",
        f"param set-default FW_AIRSPD_MIN {perdida + 2:.0f}",
        # Con los 50° del standard_vtol la pérdida subía a 17,5 m/s: en el
        # primer giro se pasó a 60°, perdió la velocidad y cayó de 47 m
        # (cuarto vuelo en Gazebo, 2026-11-16). Con 30°, 15 m/s.
        "param set-default FW_R_LIM 30",
        f"param set-default FW_AIRSPD_TRIM {crucero:.0f}",
        f"param set-default FW_AIRSPD_MAX {crucero + 8:.0f}",
        f"param set-default FW_THR_TRIM {trim:.2f}",
        "param set-default FW_THR_MAX 1.0",
        "param set-default FW_THR_MIN 0.05",
        f"param set-default MPC_THR_HOVER {hover:.2f}",
        "",
        "# Lo demás, del standard_vtol de PX4 tal cual: sin ajustar a este avión.",
        "param set-default NPFG_PERIOD 12",
        "param set-default FW_PR_FF 0.2",
        "param set-default FW_PR_P 0.9",
        "param set-default FW_P_LIM_MIN -15",
        "param set-default FW_RR_FF 0.1",
        "param set-default FW_RR_P 0.3",
        "param set-default FW_T_CLMB_MAX 8",
        "param set-default FW_T_SINK_MAX 2.7",
        "param set-default FW_T_SINK_MIN 2.2",
        "param set-default MC_AIRMODE 1",
        "param set-default MC_ROLLRATE_P 0.3",
        "param set-default MC_YAW_P 1.6",
        "param set-default MIS_TAKEOFF_ALT 10",
        "param set-default MPC_XY_P 0.8",
        "param set-default MPC_XY_VEL_P_ACC 3",
        "param set-default MPC_XY_VEL_I_ACC 4",
        "param set-default MPC_XY_VEL_D_ACC 0.1",
        "param set-default NAV_ACC_RAD 5",
        "param set-default NAV_DLL_ACT 2",
        "",
    ]
    return "\n".join(lineas)


# -------------------------------------------------------------- archivos STL

def leer_stl(ruta):
    b = Path(ruta).read_bytes()
    n = int.from_bytes(b[80:84], "little")
    tipo = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    return np.frombuffer(b[84:84 + 50 * n], dtype=tipo)["v"].astype(float)


def escribir_stl(ruta, tri):
    tipo = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    datos = np.zeros(len(tri), dtype=tipo)
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    largo = np.linalg.norm(normal, axis=1)
    largo[largo == 0] = 1
    datos["n"] = normal / largo[:, None]
    datos["v"] = tri
    Path(ruta).write_bytes(b"Intelliprint".ljust(80, b" ") + len(tri).to_bytes(4, "little")
                           + datos.tobytes())


def piezas_de(proyecto):
    """Los STL de un proyecto, por pieza; lo archivado no cuenta."""
    impreso = {}
    for stl in sorted(Path(proyecto).glob("nodos/*/parts/*/*.stl")):
        if "archivo" not in stl.parts:
            impreso[stl.parent.parent.parent.name] = leer_stl(stl)
    return impreso


def generar(proyecto, salida):
    salida = Path(salida)
    raiz = Path(__file__).resolve().parent.parent
    r = json.loads((raiz / "scripts" / "avion_vtol.json").read_text(encoding="utf-8"))
    aero = json.loads((raiz / "sim" / "aero_vtol.json").read_text(encoding="utf-8"))
    pesado = Path(proyecto) / "masas.json"
    pesos = ({k: p["masa_kg"] for k, p in json.loads(pesado.read_text(encoding="utf-8"))
              ["piezas"].items()} if pesado.exists() else None)
    m = Modelo(r, aero, piezas_de(proyecto), pesos)
    carpeta = salida / "modelos" / NOMBRE
    (carpeta / "meshes").mkdir(parents=True, exist_ok=True)
    for nombre, tri in m.mallas().items():
        escribir_stl(carpeta / "meshes" / f"{nombre}.stl", tri)
    (carpeta / "model.sdf").write_text(m.sdf(), encoding="utf-8")
    (carpeta / "model.config").write_text(
        '<?xml version="1.0"?>\n<model><name>Intelliprint VTOL</name><version>1.0</version>'
        '<sdf version="1.10">model.sdf</sdf><description>Ala volante VTOL de Intelliprint, '
        "dibujada a mano por el asistente (F13.6 (simulación)).</description></model>\n",
        encoding="utf-8")
    (salida / "urdf").mkdir(exist_ok=True)
    (salida / "urdf" / f"{NOMBRE}.urdf").write_text(
        m.urdf(f"file:///sim/modelos/{NOMBRE}/meshes"), encoding="utf-8")
    (salida / "px4").mkdir(exist_ok=True)
    (salida / "px4" / AERONAVE).write_text(airframe(r), encoding="utf-8", newline="\n")
    return m


if __name__ == "__main__":
    m = generar(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "sim")
    print(f"masa {m.masa:.3f} kg; CG del modelo respecto al del dimensionado: "
          f"{np.round(np.array(m.cg_flu) * 1000, 1)} mm (FLU)")
    print("inercia (kg·m²):", np.round(np.diag(m.tensor), 4), "productos:",
          np.round([m.tensor[0, 1], m.tensor[0, 2], m.tensor[1, 2]], 4))
    print(f"de pie, el CG a {m.altura * 1000:.0f} mm del suelo; patas: {len(m.patas)}")
