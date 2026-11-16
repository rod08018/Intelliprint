"""La misión de prueba del ala volante, hablando MAVLink con PX4 (F13.6 (simulación)).

Despega en vertical, pasa a avión, da una vuelta de casi 3 km a 50 m, vuelve
a helicóptero y aterriza donde salió. La usan la prueba de vuelo
(`sim/pruebas/test_vuelo.py`) y la pantalla del navegador (`sim/ver.sh`).

Con PX4 ya en marcha, dentro del contenedor:
    python3 sim/mision.py
"""

import csv
import math
import sys
import time
from pathlib import Path

from pymavlink import mavutil

ALTURA = 50.0                   # m sobre la casa, la de la misión
DESPEGUE = 30.0
TOPE_S = 900                    # el vuelo entero, en tiempo de simulación ~ real
MC, FW = 3, 4                   # MAV_VTOL_STATE
EN_TIERRA = 1                   # MAV_LANDED_STATE_ON_GROUND
M = mavutil.mavlink


def punto(casa, norte, este):
    lat, lon = casa
    dlat = norte / 6378137.0
    dlon = este / (6378137.0 * math.cos(math.radians(lat)))
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


def distancia(a, b):
    n = math.radians(b[0] - a[0]) * 6378137.0
    e = math.radians(b[1] - a[1]) * 6378137.0 * math.cos(math.radians(a[0]))
    return math.hypot(n, e)


class Vuelo:
    """La conexión con PX4 y lo que va pasando, con el latido de la estación."""

    def __init__(self, enlace):
        self.m = enlace
        self.estado = {"alt": 0.0, "vtol": 0, "suelo": 0, "aire": 0.0, "gas": 0.0,
                       "armado": False, "lat": None, "lon": None, "item": -1}
        self.muestras = []
        self.textos = []
        self.casa = None
        self._latido = 0.0
        self._muestra = 0.0
        self.t0 = time.time()

    def leer(self, espera=0.2):
        if time.time() - self._latido > 1:
            self.m.mav.heartbeat_send(M.MAV_TYPE_GCS, M.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            self._latido = time.time()
        msg = self.m.recv_match(blocking=True, timeout=espera)
        e = self.estado
        if msg is not None:
            t = msg.get_type()
            if t == "GLOBAL_POSITION_INT":
                e["alt"], e["lat"], e["lon"] = msg.relative_alt / 1000, msg.lat / 1e7, msg.lon / 1e7
            elif t == "EXTENDED_SYS_STATE":
                e["vtol"], e["suelo"] = msg.vtol_state, msg.landed_state
            elif t == "VFR_HUD":
                e["aire"], e["gas"] = msg.airspeed, msg.throttle
            elif t == "HEARTBEAT" and msg.get_srcSystem() == self.m.target_system:
                e["armado"] = bool(msg.base_mode & M.MAV_MODE_FLAG_SAFETY_ARMED)
            elif t == "MISSION_CURRENT":
                e["item"] = msg.seq
            elif t == "STATUSTEXT":
                self.textos.append((round(time.time() - self.t0, 1), msg.text))
        if time.time() - self._muestra > 0.5 and e["lat"] is not None:
            self.muestras.append(dict(e, t=round(time.time() - self.t0, 1)))
            self._muestra = time.time()
        return msg

    def esperar(self, condicion, tope, que):
        fin = time.time() + tope
        while time.time() < fin:
            self.leer()
            if condicion(self.estado):
                return
        raise AssertionError(f"{que}: no pasó en {tope} s; último estado {self.estado}; "
                             f"PX4 dijo: {self.textos[-6:]}")

    def orden(self, comando, *p, tope=5):
        p = list(p) + [0] * (7 - len(p))
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component, comando,
                                     0, *p)
        fin = time.time() + tope
        while time.time() < fin:
            msg = self.leer()
            if msg is not None and msg.get_type() == "COMMAND_ACK" and msg.command == comando:
                return msg.result
        return None

    def mision(self, puntos):
        ts, tc = self.m.target_system, self.m.target_component
        self.m.mav.mission_count_send(ts, tc, len(puntos), M.MAV_MISSION_TYPE_MISSION)
        fin = time.time() + 30
        while time.time() < fin:
            msg = self.leer()
            if msg is None:
                continue
            if msg.get_type() in ("MISSION_REQUEST_INT", "MISSION_REQUEST"):
                cmd, (lat, lon), alt = puntos[msg.seq]
                self.m.mav.mission_item_int_send(
                    ts, tc, msg.seq, M.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, cmd,
                    0, 1, 0, 0, 0, math.nan, int(lat * 1e7), int(lon * 1e7), alt,
                    M.MAV_MISSION_TYPE_MISSION)
            elif msg.get_type() == "MISSION_ACK":
                assert msg.type == M.MAV_MISSION_ACCEPTED, f"misión rechazada: {msg.type}"
                return
        raise AssertionError("la misión no se subió")

    def guardar(self, carpeta):
        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        with open(carpeta / "vuelo.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["t", "alt", "vtol", "suelo", "aire", "gas",
                                              "armado", "lat", "lon", "item"])
            w.writeheader()
            w.writerows(self.muestras)
        (carpeta / "px4_dijo.txt").write_text(
            "\n".join(f"{t}\t{x}" for t, x in self.textos), encoding="utf-8")


def conectar(conexion="udpin:0.0.0.0:14550"):
    return Vuelo(mavutil.mavlink_connection(conexion, source_system=255))


def volar(v):
    """Espera a PX4, sube la misión, arma y vuelve cuando aterriza o se estrella.

    `v` viene de fuera para que, si falla a medias, lo grabado no se pierda."""
    assert v.m.wait_heartbeat(timeout=180), "PX4 no arrancó"
    v.esperar(lambda e: e["lat"] is not None and e["lat"] != 0, 120, "posición")
    casa = (v.estado["lat"], v.estado["lon"])
    v.casa = casa
    v.mision([
        (M.MAV_CMD_NAV_VTOL_TAKEOFF, punto(casa, 300, 0), DESPEGUE),
        (M.MAV_CMD_NAV_WAYPOINT, punto(casa, 800, 0), ALTURA),
        (M.MAV_CMD_NAV_WAYPOINT, punto(casa, 800, 600), ALTURA),
        (M.MAV_CMD_NAV_WAYPOINT, punto(casa, 0, 600), ALTURA),
        (M.MAV_CMD_NAV_WAYPOINT, punto(casa, 0, 300), ALTURA),
        (M.MAV_CMD_NAV_VTOL_LAND, casa, 0),
    ])
    # Modo misión (PX4: AUTO = 4, MISSION = 4) y armar, hasta que los
    # chequeos de antes de volar (EKF, GPS) lo dejen.
    fin = time.time() + 180
    while True:
        v.orden(M.MAV_CMD_DO_SET_MODE, M.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4, 4)
        if v.orden(M.MAV_CMD_COMPONENT_ARM_DISARM, 1) == M.MAV_RESULT_ACCEPTED:
            break
        assert time.time() < fin, f"no se dejó armar: {v.textos[-6:]}"
        for _ in range(10):
            v.leer()
    v.esperar(lambda e: e["armado"], 10, "armado")
    # Hasta que aterrice y se desarme solo, o se estrelle: en modo avión a
    # ras de suelo (el cuarto vuelo se quedó 15 min así, con el gas a tope,
    # hasta el tope de la prueba).
    v.esperar(lambda e: not e["armado"] or (e["vtol"] == FW and e["alt"] < 2),
              TOPE_S, "vuelta a tierra")
    # Tras desarmar, hasta que PX4 diga «en tierra», y esa muestra se guarda:
    # en el sexto vuelo la última era de medio segundo antes, aún
    # «aterrizando», y la prueba daba por no aterrizado un avión en casa.
    if not v.estado["armado"]:
        try:
            v.esperar(lambda e: e["suelo"] == EN_TIERRA, 10, "en tierra")
        except AssertionError:
            pass
    v.muestras.append(dict(v.estado, t=round(time.time() - v.t0, 1)))
    return v


if __name__ == "__main__":
    v = volar(conectar(*sys.argv[1:2]))
    final = v.muestras[-1]
    print("aterrizó" if final["suelo"] == EN_TIERRA else "NO aterrizó",
          f"a {distancia(v.casa, (final['lat'], final['lon'])):.0f} m de la casa")
