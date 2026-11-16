"""Lo que hizo PX4 en un vuelo de la simulación, de su registro (F13.6 (simulación)).

Cabeceo y alabeo (los medidos y los pedidos), velocidad, altura, lo que manda
a los elevones y a los motores, cada medio segundo entre dos instantes.

Dentro del contenedor:
    python3 sim/leer_registro.py /sim/registros/vuelo.ulg [desde_s] [hasta_s]
"""

import math
import sys

import numpy as np
from pyulog import ULog


def _serie(log, tema, campo, i=0):
    for d in log.data_list:
        if d.name == tema and d.multi_id == i and campo in d.data:
            return d.data["timestamp"] / 1e6, d.data[campo]
    return None


def _euler(q0, q1, q2, q3):
    alabeo = math.atan2(2 * (q0 * q1 + q2 * q3), 1 - 2 * (q1 * q1 + q2 * q2))
    cabeceo = math.asin(max(-1, min(1, 2 * (q0 * q2 - q3 * q1))))
    return math.degrees(alabeo), math.degrees(cabeceo)


def main(ruta, desde=0.0, hasta=1e9):
    log = ULog(ruta)
    t0 = log.start_timestamp / 1e6
    series = {}
    for nombre, tema, campos in (
            ("act", "vehicle_attitude", ["q[0]", "q[1]", "q[2]", "q[3]"]),
            ("sp", "vehicle_attitude_setpoint", ["q_d[0]", "q_d[1]", "q_d[2]", "q_d[3]"])):
        cols = [_serie(log, tema, c) for c in campos]
        if all(cols):
            series[nombre] = (cols[0][0], np.array([c[1] for c in cols]).T)
    simples = {"aire": ("airspeed_validated", "calibrated_airspeed_m_s"),
               "alt": ("vehicle_local_position", "z"), "vz": ("vehicle_local_position", "vz")}
    for k in range(4):
        simples[f"sv{k}"] = ("actuator_servos", f"control[{k}]")
    for k in range(5):
        simples[f"m{k}"] = ("actuator_motors", f"control[{k}]")
    s = {n: _serie(log, *tc) for n, tc in simples.items()}
    print("t\talab\tcab\talab*\tcab*\taire\talt\tvz\tsv0..3\t\t\tm0..4")
    t = desde
    while t <= hasta:
        def v(n):
            x = s.get(n)
            if not x:
                return float("nan")
            j = np.searchsorted(x[0] - t0, t)
            return float(x[1][min(j, len(x[1]) - 1)])

        def e(n):
            if n not in series:
                return (float("nan"),) * 2
            tt, q = series[n]
            j = min(np.searchsorted(tt - t0, t), len(q) - 1)
            return _euler(*q[j])
        a, c = e("act")
        a2, c2 = e("sp")
        print(f"{t:.1f}\t{a:.0f}\t{c:.0f}\t{a2:.0f}\t{c2:.0f}\t{v('aire'):.1f}\t{-v('alt'):.1f}"
              f"\t{v('vz'):.1f}\t" + " ".join(f"{v(f'sv{k}'):+.2f}" for k in range(4)) + "\t"
              + " ".join(f"{v(f'm{k}'):.2f}" for k in range(5)))
        t += 0.5


if __name__ == "__main__":
    main(sys.argv[1], *(float(x) for x in sys.argv[2:4]))
