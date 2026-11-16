"""Los coeficientes aerodinámicos del ala volante para Gazebo (F13.6 (simulación)).

Gazebo mueve el avión con el plugin `AdvancedLiftDrag` (gz-sim 8): toma las
derivadas de estabilidad del avión entero respecto a un punto, como las da
AVL. Él quitó AVL de en medio (2026-11-11: «sin meternos a handoff de avl y
px4»; el 2026-11-16 pidió PX4 y Gazebo, no AVL), así que salen de AeroSandbox
(AeroBuildup con NeuralFoil), el mismo modelo con el que se dimensionó.

Convenciones del plugin, leídas en su código (gz-sim 8,
`AdvancedLiftDrag.cc`): ejes del cuerpo x adelante, y a la derecha, z abajo;
momentos positivos alabeo a la derecha, morro arriba y morro a la derecha;
derivadas de giro respecto a p·b/2V, q·c/2V y r·b/2V; las de alfa y beta por
radián y las de los mandos POR GRADO. Son las de AeroSandbox, salvo las de
los mandos, que AeroSandbox no deriva: se sacan aquí por diferencias,
desviándolos ±5°.

Los mandos son cuatro, uno por servo: el elevón interior y el exterior de
cada lado. AeroSandbox solo desvía un ala simétrica a la vez en simétrico o
en antisimétrico; lo de un solo lado es la media: derecho = (sim + anti) / 2,
izquierdo = (sim − anti) / 2. Desviación positiva = borde de salida abajo.

Lo escribió el asistente a mano: no es nota del sistema. AeroBuildup es un
modelo de capa límite y teoría de líneas, no un túnel: las derivadas de giro
y las de los mandos son las menos fiables.

Uso (en el PC, donde está AeroSandbox):
    .venv\\Scripts\\python.exe scripts\\avion_vtol_aero.py scripts\\avion_vtol.json sim\\aero_vtol.json
"""

import json
import math
import sys
from pathlib import Path

ENTRADA, SALIDA = sys.argv[1], sys.argv[2]
sys.argv = sys.argv[:1]     # el dimensionado lee la carga de argv[2]
sys.path.insert(0, str(Path(__file__).parent))

import aerosandbox as asb  # noqa: E402
import aerosandbox.numpy as np  # noqa: E402

import avion_vtol_dimensionar as D  # noqa: E402

DELTA = 5.0                  # grados, por cada lado de la diferencia
# Para ajustar las rectas de CL, Cm y la polar, alrededor del crucero (4,3°).
# De -2 a 8 la recta de Cm no es recta: equilibraba a 6,9° y no a 4,3.
ALFAS = list(range(0, 9))


def _n(x):
    return float(np.ravel(x)[0])


def avion(r, desvio=None):
    """El avión de AeroSandbox con los elevones partidos. `desvio`: (cuál,
    simétrico, antisimétrico) en grados, con cuál "interior" o "exterior"."""
    eq = r["equilibrio"]
    aeronave, _ = D.avion(eq["torsion_punta_grados"], eq["cg_x_m"])
    est = [tuple(e) for e in r["estaciones"]]
    grupos = r["diseno"]["elevones"]
    tramos = []   # los y donde empieza y acaba cada elevón, de los tramos del kit
    y0, y1 = est[2][0], est[3][0]
    n = math.ceil((y1 - y0) * 1000 / 160 - 1e-9)
    cortes = [y0 + (y1 - y0) * k / n for k in range(n + 1)]
    for g in grupos:
        tramos.append((cortes[g[0] - 1], cortes[g[-1]]))
    nombres = ["interior", "exterior"]

    def interp(y):
        for a, b in zip(est, est[1:]):
            if a[0] - 1e-9 <= y <= b[0] + 1e-9:
                t = (y - a[0]) / (b[0] - a[0])
                return tuple(a[k] + (b[k] - a[k]) * t for k in range(5)) + (a[5],)
        raise ValueError(y)

    ys = sorted({e[0] for e in est} | {y for t in tramos for y in t})
    xsecs = []
    for y in ys:
        _, x, z, c, t, p = interp(y)
        cs = []
        for nombre, (a, b) in zip(nombres, tramos):
            if abs(y - a) < 1e-9:     # el mando va en la sección donde empieza
                s, an = (desvio[1], desvio[2]) if desvio and desvio[0] == nombre else (0.0, 0.0)
                cs = [asb.ControlSurface(name=f"{nombre}-s", symmetric=True, deflection=s,
                                         hinge_point=r["diseno"]["elevon"][1]),
                      asb.ControlSurface(name=f"{nombre}-a", symmetric=False, deflection=an,
                                         hinge_point=r["diseno"]["elevon"][1])]
        xsecs.append(asb.WingXSec(xyz_le=[x, y, z], chord=c, twist=t, airfoil=asb.Airfoil(p),
                                  control_surfaces=cs))
    aeronave.wings[0] = asb.Wing(name="ala", symmetric=True, xsecs=xsecs)
    cg = r["equilibrio"]["con_carga"]["cg_mm"]
    aeronave.xyz_ref = [cg[0] / 1000, 0.0, cg[2] / 1000]
    return aeronave


def cl_del_plugin(alfa, cl0, cla, perdida, m=15.0):
    """El CL de AdvancedLiftDrag (gz-sim 8, copiado de su código): la recta y
    la placa plana, mezcladas con una sigmoide de pendiente M = 15 fija."""
    sigma = ((1 + math.exp(-m * (alfa - perdida)) + math.exp(m * (alfa + perdida)))
             / ((1 + math.exp(-m * (alfa - perdida))) * (1 + math.exp(m * (alfa + perdida)))))
    placa = 2 * math.copysign(1, alfa) * math.sin(alfa) ** 2 * math.cos(alfa)
    return (1 - sigma) * (cl0 + cla * alfa) + sigma * placa


def perdida_del_plugin(cl0, cla, clmax):
    """La `alpha_stall` con la que el CL máximo del plugin es `clmax`."""
    def maximo(s):
        return max(cl_del_plugin(math.radians(a / 10), cl0, cla, s) for a in range(1, 600))
    lo, hi = 0.05, 0.6
    for _ in range(40):
        s = (lo + hi) / 2
        lo, hi = (s, hi) if maximo(s) < clmax else (lo, s)
    return (lo + hi) / 2


def correr(aeronave, alfa, **giros):
    return asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(
        velocity=D.V_CRUCERO, alpha=alfa, **giros))


def sin_mandos(r):
    """El avión del dimensionado, tal cual, con la referencia en el CG.

    Las rectas y las derivadas salen de este y no del de los elevones
    partidos: con dos secciones más AeroBuildup discretiza otra ala y el Cm a
    4,3° pasaba de −0,002 a +0,019 (equilibraba a 6,75° y no a 4,3, con o sin
    mandos). Los mandos van como diferencias, y ahí ese desfase se anula."""
    eq = r["equilibrio"]
    aeronave, _ = D.avion(eq["torsion_punta_grados"], eq["cg_x_m"])
    cg = eq["con_carga"]["cg_mm"]
    aeronave.xyz_ref = [cg[0] / 1000, 0.0, cg[2] / 1000]
    return aeronave


def coeficientes(r):
    base = sin_mandos(r)
    ala = base.wings[0]
    s, b, mac = ala.area(), ala.span(), ala.mean_aerodynamic_chord()
    ar = b ** 2 / s
    filas = [correr(base, a).run() for a in ALFAS]
    cl = np.array([_n(f["CL"]) for f in filas])
    cd = np.array([_n(f["CD"]) for f in filas])
    cm = np.array([_n(f["Cm"]) for f in filas])
    rad = np.radians(np.array(ALFAS, dtype=float))
    cla, cl0 = np.polyfit(rad, cl, 1)
    cma, cm0 = np.polyfit(rad, cm, 1)
    k, cd0 = np.polyfit(cl ** 2, cd, 1)
    # Las hélices paradas, sus motores y las vigas: AeroSandbox no los ve.
    cd0 += D.CDA_ROTORES_M2 / s
    alfa = r["crucero"]["alfa_grados"]
    est = correr(base, alfa).run_with_stability_derivatives(alpha=True, beta=True, p=True,
                                                            q=True, r=True)
    co = {
        "a0": 0.0, "CL0": cl0, "AR": ar, "eff": 1 / (math.pi * ar * k), "CLa": cla, "CD0": cd0,
        "Cem0": cm0, "Cema": cma,
        "CYb": _n(est["CYb"]), "Cellb": _n(est["Clb"]), "Cenb": _n(est["Cnb"]),
        "CDp": _n(est["CDp"]), "CYp": _n(est["CYp"]), "CLp": _n(est["CLp"]),
        "Cellp": _n(est["Clp"]), "Cemp": _n(est["Cmp"]), "Cenp": _n(est["Cnp"]),
        "CDq": _n(est["CDq"]), "CYq": _n(est["CYq"]), "CLq": _n(est["CLq"]),
        "Cellq": _n(est["Clq"]), "Cemq": _n(est["Cmq"]), "Cenq": _n(est["Cnq"]),
        "CDr": _n(est["CDr"]), "CYr": _n(est["CYr"]), "CLr": _n(est["CLr"]),
        "Cellr": _n(est["Clr"]), "Cemr": _n(est["Cmr"]), "Cenr": _n(est["Cnr"]),
        # La pérdida: la que hace que el CL máximo DEL PLUGIN sea el del
        # dimensionado (el MH 60 sin flaps). No es donde la recta llega a ese
        # CL: el plugin mezcla con una sigmoide de pendiente fija, y con esa
        # pérdida (10,2°) restaba desde 0°: en crucero daba 0,39 de 0,49 y no
        # pasaba de 0,63; en el quinto vuelo en Gazebo entró en pérdida al
        # alabear 30° y cayó (2026-11-16).
        "alpha_stall": perdida_del_plugin(cl0, cla, r["supuestos"]["clmax"]),
        "CLa_stall": -3.85, "CDa_stall": -0.9233984055, "Cema_stall": 0.0,
        "area": s, "mac": mac, "span": b,
    }
    nombres = {"CL": "CL_ctrl", "CD": "CD_ctrl", "CY": "CY_ctrl", "Cl": "Cell_ctrl",
               "Cm": "Cem_ctrl", "Cn": "Cen_ctrl"}
    mandos = {}
    for cual in ("interior", "exterior"):
        def delta(sim, anti):
            mas = correr(avion(r, (cual, sim * DELTA, anti * DELTA)), alfa).run()
            menos = correr(avion(r, (cual, -sim * DELTA, -anti * DELTA)), alfa).run()
            return {c: (_n(mas[c]) - _n(menos[c])) / (2 * DELTA) for c in nombres}
        sim, anti = delta(1, 0), delta(0, 1)
        for lado, signo in (("d", 1), ("i", -1)):
            mandos[f"{cual}-{lado}"] = {nombres[c]: (sim[c] + signo * anti[c]) / 2 for c in nombres}
    co["mandos_por_grado_borde_abajo"] = mandos
    co["crucero"] = {"alfa_grados": alfa, "CL": _n(correr(base, alfa).run()["CL"]),
                     "velocidad_m_s": D.V_CRUCERO}
    return co


if __name__ == "__main__":
    r = json.loads(Path(ENTRADA).read_text(encoding="utf-8"))
    co = coeficientes(r)
    Path(SALIDA).parent.mkdir(parents=True, exist_ok=True)
    Path(SALIDA).write_text(json.dumps(co, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(co, ensure_ascii=False, indent=1))
