"""Dimensiona el VTOL de la Fase 13 con AeroSandbox: un ala volante ligera.

Lo pidió él el 2026-11-14 (un VTOL «como el TerraHawk pero mejorado», 2 m o
más, la carga del TerraHawk —hasta 1 kg: dos cámaras y un lidar—, unas 3 h y
200–250 km) y el 2026-11-16, al ver la primera versión (8,7 kg, cola en H
sobre vigas largas): «quiero que lo nuestro sea ligero», «más parecido a un
avión moderno eficiente», con el Moose de Flightory y el TerraHawk de
referencia; y que se tenga en cuenta lo que gastan cinco motores.

Lo que cambia de la primera versión, y por qué:
- **Sin cola**: ala volante con flecha, perfil autoestable (MH 60), torsión
  hacia la punta y las puntas levantadas (como el TerraHawk). La cola en H y
  las vigas largas pesaban y daban resistencia.
- **Lo comprado crece con el avión**: los motores de sustentación, sus
  variadores y hélices se dimensionan con el empuje que piden (antes, 275 g
  cada uno fijos, de un avión de 8,7 kg). El peso se busca por punto fijo.
- **Los rotores no se pisan**: los discos de las hélices se separan entre sí,
  del ala y del de empuje al menos un 15 % del diámetro de sustentación.

Lo escribió el asistente a mano: no es nota del sistema. Las masas por kilo
de empuje, los rendimientos y la densidad del LW-PLA son estimaciones del
asistente y van en el informe; la aerodinámica es la de AeroSandbox
(AeroBuildup con NeuralFoil), no un túnel ni un vuelo.

Uso (en el PC, donde está AeroSandbox):
    .venv\\Scripts\\python.exe scripts\\avion_vtol_dimensionar.py salida.json [carga_kg]
"""

import json
import math
import sys

import aerosandbox as asb
import aerosandbox.numpy as np

RHO, G = 1.225, 9.81
V_CRUCERO = 20.0     # 72 km/h, la del TerraHawk según su captura
HORAS = 3.0
CARGA_KG = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

# --- Supuestos del asistente (no medidos) ------------------------------------
RENDIMIENTO_CRUCERO = 0.60      # hélice plegable 0,75 × motor 0,85 × variador 0,95
FIGURA_MERITO = 0.60
RENDIMIENTO_MOTOR_VTOL = 0.85
MIN_VTOL = 3.0                  # despegue, aterrizaje y transiciones
RESERVA = 0.15
EMPUJE_SOBRE_PESO = 1.8         # lo que pueden los cuatro rotores juntos
KG_POR_KG_EMPUJE = 0.065        # motor 0,040 + variador 0,015 + hélice 0,010
EMPUJE_CRUCERO_FRACCION = 0.035  # motor, variador y hélice plegable de empuje
CELDA = {"nombre": "21700 de 4,5 Ah (tipo Molicel P45B)", "Wh": 16.2, "g": 70.0}
EMPAQUE = 1.08
LWPLA_G_CM3, PIEL_MM, NERVIOS = 0.75, 0.6, 1.4
CDA_ROTORES_M2 = 0.006          # cuatro hélices paradas en línea y sus motores
# Controladora, ordenador de a bordo (una Raspberry Pi 5 con disipador:
# la pidió él el 2026-11-16), GPS, telemetría, receptor y cables.
AVIONICA_KG = 0.31
SERVOS_KG = 4 * 0.025            # cuatro servos finos de ala, uno por elevón
LARGUEROS_KG, VIGAS_KG = (0.06, 0.03), 0.09   # Ø10 y Ø6; las dos vigas Ø16
CARBONO_KG = sum(LARGUEROS_KG) + VIGAS_KG

# --- Lo de dentro (mm): cajas que ocupan sitio -----------------------------------
# La batería 6S6P: 36 celdas 21700 tumbadas a lo largo, seis de ancho y dos de
# alto, en tres filas de 70 mm; con el forro, 210 × 130 × 46.
CAJA_BATERIA = (210, 130, 46)
CAJA_CARGA = (160, 80, 50)       # dos cámaras y un lidar, en su bandeja
# La controladora y la Raspberry Pi una detrás de otra. Con 110 × 70 en
# x = -60 se salía del morro, que ahí mide 112 × 92 por dentro (cuentas del
# 2026-11-16).
CAJA_ELECTRONICA = (120, 60, 40)
X_ELECTRONICA = -20
CAJA_SERVO = (24, 34, 10)        # un servo fino de ala, tumbado
# Dos elevones por lado, cada uno con su servo (él, el 2026-11-16: «debe
# tener alerones, implica que debe tener 4 servos»). Por tramos de ala: el
# interior es el 3 (570–730 mm) y el exterior, el 4 y el 5 pegados
# (730–1050), que reparten la superficie entre los dos servos (7 000 y
# 11 300 mm²); si uno falla, el avión sigue gobernable.
ELEVONES = ((3,), (4, 5))
SERVO_Y = (650, 850)             # cada servo, dentro de un tramo y en su elevón
# El margen estático que se acepta, con carga y sin ella. Un ala volante
# vuela con poco (un 5–10 %); por debajo del 5 % se vuelve nerviosa y
# pasado el punto neutro, inestable (criterio del asistente).
MARGEN_MINIMO, MARGEN_MAXIMO = 0.05, 0.12
SERVO_CUERDA = 0.42              # entre los dos largueros (25 % y 60 %)
# El techo de la batería: 3 mm bajo el larguero de Ø6, que cruza el fuselaje
# a z ≈ -7 (el de Ø10, más adelante, a -4,5).
Z_TECHO_BATERIA = -13
MEDIO_GONDOLA = 40               # el de `avion.MEDIO_LARGO_GONDOLA`
X_EMPUJE_MM = 720

# --- La forma (m), x hacia atrás, y a la derecha, z arriba ----------------------
ENVERGADURA = 2.10
FLECHA_GRADOS = 25.0
Y_VIGA = 0.38
HELICE_VTOL_PULG = 13
HELICE_EMPUJE_PULG = 10      # el crucero pide 4,4 N: sobra
Z_FUSELAJE = -0.02           # el eje del fuselaje y de la hélice de empuje
# La viga va donde la pone el kit, justo bajo el ala. Las derivas y las patas
# son el tren de aterrizaje: con 130 mm la hélice de empuje bajaba 5 mm más
# que ellas y tocaba el suelo al posarse (cuentas del 2026-11-16); se alargan
# hasta dejarle 30 mm.
X_DERIVA, Z_VIGA = 0.72, -0.012
HUECO_SUELO = 0.03
ALTO_DERIVA = round(Z_VIGA - (Z_FUSELAJE - HELICE_EMPUJE_PULG * 0.0254 / 2 - HUECO_SUELO), 3)
# El fuselaje: (x, ancho, alto, z del centro). En el centro de gravedad se
# ahonda hacia abajo: arriba, bajo los largueros, la batería; debajo, la
# carga. Las dos tienen que ir ahí (él, el 2026-11-16: «la batería debe
# estar en un lugar donde no modifique mucho el centro de gravedad»): con
# la carga en el morro, quitarla echaba el centro de gravedad 35–83 mm
# atrás, más allá del punto neutro, y el ala volante se volvía inestable.
FUSELAJE = ((-0.22, 0.02, 0.02, -0.02), (-0.14, 0.11, 0.09, -0.02), (0.0, 0.15, 0.13, -0.03),
            (0.18, 0.16, 0.18, -0.05), (0.42, 0.16, 0.18, -0.05), (0.60, 0.09, 0.08, -0.02),
            (0.72, 0.04, 0.04, -0.02))


def estaciones(torsion_punta):
    """(y, x del borde de ataque, z, cuerda, torsión, perfil)."""
    y_punta = ENVERGADURA / 2
    x_punta = 0.19 + (y_punta - 0.25) * math.tan(math.radians(FLECHA_GRADOS))
    # La última sube 40°: la punta levantada del TerraHawk. Una aleta vertical
    # no se imprime de pie sobre la cara de la raíz del tramo; esta sí.
    sube = 0.085
    return [(0.00, 0.00, 0.000, 0.62, 2.0, "mh78"),
            (0.20, 0.17, 0.000, 0.28, 1.0, "mh60"),
            (0.25, 0.19, 0.005, 0.23, 0.0, "mh60"),
            (y_punta, x_punta, 0.050, 0.12, torsion_punta, "mh60"),
            (y_punta + sube, x_punta + sube * math.tan(math.radians(FLECHA_GRADOS)) + 0.02,
             0.050 + sube * math.tan(math.radians(40)), 0.08, torsion_punta, "mh60")]


def avion(torsion_punta, x_cg=0.0):
    est = estaciones(torsion_punta)
    ala = asb.Wing(name="ala", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[x, y, z], chord=c, twist=t, airfoil=asb.Airfoil(p))
        for y, x, z, c, t, p in est])
    # Elipses (shape=2), como las dibuja el kit: con 3 AeroSandbox calculaba
    # un fuselaje más cuadrado que el que se imprime.
    fuselaje = asb.Fuselage(name="fuselaje", xsecs=[
        asb.FuselageXSec(xyz_c=[xs, 0, zc], width=w, height=h, shape=2)
        for xs, w, h, zc in FUSELAJE])
    # Sin las aletas de las puntas el ala volante quedaba inestable de guiñada
    # (Cn_beta -0,005): dos derivas bajo la cola de las vigas, que además son
    # las patas traseras al posarse. Abajo, para no tocar las hélices.
    derivas = asb.Wing(name="derivas", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[X_DERIVA, Y_VIGA, Z_VIGA], chord=0.15, airfoil=asb.Airfoil("naca0008")),
        asb.WingXSec(xyz_le=[X_DERIVA + 0.07, Y_VIGA, Z_VIGA - ALTO_DERIVA], chord=0.09,
                     airfoil=asb.Airfoil("naca0008"))])
    return asb.Airplane(name="VTOL", xyz_ref=[x_cg, 0, 0], wings=[ala, derivas],
                        fuselages=[fuselaje]), ala


def _num(x):
    return float(np.ravel(x)[0])


def aero(aeronave, alfa):
    r = asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(
        velocity=V_CRUCERO, alpha=alfa)).run()
    return {k: _num(r[k]) for k in ("L", "D", "CL", "CD", "Cm")}


def alfa_que_sustenta(aeronave, peso):
    lo, hi = -4.0, 12.0
    for _ in range(26):
        a = (lo + hi) / 2
        lo, hi = (a, hi) if aero(aeronave, a)["L"] < peso else (lo, a)
    return (lo + hi) / 2


def equilibrado(peso, margen=0.07):
    """La torsión de la punta que deja el ala volante en equilibrio (Cm = 0 en
    el centro de gravedad) con un margen estático de `margen`."""
    mejor = None
    for torsion in np.linspace(0, -8, 17):
        aeronave, ala = avion(float(torsion))
        alfa = alfa_que_sustenta(aeronave, peso)
        est = asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(
            velocity=V_CRUCERO, alpha=alfa)).run_with_stability_derivatives()
        x_np = _num(est["x_np"])
        x_cg = x_np - margen * ala.mean_aerodynamic_chord()
        aeronave, ala = avion(float(torsion), x_cg)
        cm = aero(aeronave, alfa)["Cm"]
        if mejor is None or abs(cm) < abs(mejor["Cm"]):
            mejor = {"torsion": float(torsion), "alfa": alfa, "x_np": x_np, "x_cg": x_cg,
                     "Cm": cm, "Cm_alfa": _num(est["Cma"]), "Cn_beta": _num(est["Cnb"])}
    return mejor


def rotores(x_cg, ala):
    """Dónde van los cuatro motores de sustentación y el de empuje. Los discos
    no pisan el ala (el soplo del rotor contra el ala resta empuje) ni se
    pisan entre sí: un 15 % del diámetro de sustentación de hueco."""
    rv = HELICE_VTOL_PULG * 0.0254 / 2
    re = HELICE_EMPUJE_PULG * 0.0254 / 2
    hueco = 0.15 * 2 * rv
    y, x, _, c, _, _ = estaciones(0)[2]
    y1, x1, _, c1, _, _ = estaciones(0)[3]
    t = (Y_VIGA - y) / (y1 - y)
    le, cu = x + (x1 - x) * t, c + (c1 - c) * t
    delante = le - rv - hueco
    detras = le + cu + rv + hueco
    d = max(x_cg - delante, detras - x_cg)      # iguales respecto al centro de gravedad
    x_empuje = 0.62 + 0.10                      # tras el borde de salida del centro
    hueco_empuje = Y_VIGA - rv - re
    return {"y_viga": Y_VIGA, "x_delante": x_cg - d, "x_detras": x_cg + d,
            "x_empuje": x_empuje, "helice_vtol_pulg": HELICE_VTOL_PULG,
            "helice_empuje_pulg": HELICE_EMPUJE_PULG,
            "hueco_entre_discos_m": round(hueco_empuje, 3),
            "hueco_minimo_m": round(hueco, 3),
            "helice_empuje_sobre_el_suelo_m": round(
                (Z_FUSELAJE - re) - (Z_VIGA - ALTO_DERIVA), 3),
            "discos_libres": hueco_empuje >= hueco}


def centroide_impreso(aeronave):
    """(x, z) en m de donde cae el peso de lo impreso. Una piel fina con
    nervios pesa por su superficie, no por su volumen: se pondera cada tramo
    de ala y de fuselaje por su área mojada. Con las piezas del 2026-11-16
    medidas en sus STL, el mismo cálculo daba 355 mm."""
    total = mx = mz = 0.0
    for w in aeronave.wings:
        for a, b in zip(w.xsecs, w.xsecs[1:]):
            pa, pb = np.array(a.xyz_le), np.array(b.xyz_le)
            largo = math.hypot(pb[1] - pa[1], pb[2] - pa[2])
            area = (a.chord + b.chord) * largo * (2 if w.symmetric else 1)
            x = ((pa[0] + a.chord / 2) * a.chord + (pb[0] + b.chord / 2) * b.chord) / (a.chord + b.chord)
            total, mx, mz = total + area, mx + area * x, mz + area * (pa[2] + pb[2]) / 2
    for f in aeronave.fuselages:
        for a, b in zip(f.xsecs, f.xsecs[1:]):
            perimetro = math.pi * (a.width + a.height + b.width + b.height) / 4
            area = perimetro * (b.xyz_c[0] - a.xyz_c[0])
            total += area
            mx += area * (a.xyz_c[0] + b.xyz_c[0]) / 2
            mz += area * (a.xyz_c[2] + b.xyz_c[2]) / 2
    return [_num(mx / total), _num(mz / total)]


def dentro(r):
    """Dónde va cada cosa, en mm, y cuánto pesa. La carga va en el centro de
    gravedad: así ponerla o quitarla no lo mueve a lo largo. La batería, que
    es casi la mitad del peso, va donde cuadran los momentos, justo encima de
    la carga y bajo los largueros (en una bandeja: correrla 1 cm mueve el
    centro de gravedad 4,5 mm). Los variadores de sustentación van en las
    góndolas, con sus motores, que están a la misma distancia por delante y
    por detrás del centro de gravedad."""
    m = r["_masas"]
    x_cg = r["equilibrio"]["cg_x_m"] * 1000
    est = [(y * 1000, x * 1000, z * 1000, c * 1000) for y, x, z, c, _, _ in r["estaciones"]]

    def ala(y, f):
        """(x, z) a la fracción `f` de la cuerda, en `y` del ala exterior."""
        for a, b in zip(est[2:], est[3:]):
            if y <= b[0] or b is est[-1]:
                t = (y - a[0]) / (b[0] - a[0])
                return (a[1] + (b[1] - a[1]) * t + f * (a[3] + (b[3] - a[3]) * t),
                        a[2] + (b[2] - a[2]) * t)

    ro = r["rotores"]
    xd, xt, yv = ro["x_delante"] * 1000, ro["x_detras"] * 1000, ro["y_viga"] * 1000
    z_motor = Z_VIGA * 1000 + 30
    ci = r["_centroide_impreso_m"]
    cosas = [{"id": "impreso", "nombre": "lo impreso (LW-PLA)", "masa_kg": m["impreso"],
              "en": [ci[0] * 1000, 0, ci[1] * 1000]}]
    for (f, mk), nombre in zip(zip((0.25, 0.6), LARGUEROS_KG), ("Ø10", "Ø6")):
        x, z = ala(505, f)   # de y = -20 a casi la punta: su mitad
        cosas.append({"id": f"larguero-{nombre}", "nombre": f"largueros {nombre}", "masa_kg": mk,
                      "en": [x, 0, z]})
    cosas.append({"id": "vigas", "nombre": "vigas Ø16 de los rotores", "masa_kg": VIGAS_KG,
                  "en": [(xd - MEDIO_GONDOLA + X_DERIVA * 1000 + 150) / 2, 0, Z_VIGA * 1000]})
    for lado, s in (("d", 1), ("i", -1)):
        for donde, x in (("delante", xd), ("detras", xt)):
            cosas.append({"id": f"motor-{lado}-{donde}",
                          "nombre": "motor de sustentación, variador y hélice",
                          "masa_kg": m["sustentacion"] / 4, "en": [x, s * yv, z_motor]})
    cosas += [{"id": "motor-empuje", "nombre": "motor y hélice de empuje",
               "masa_kg": 0.8 * m["empuje"], "en": [X_EMPUJE_MM + 15, 0, Z_FUSELAJE * 1000]},
              {"id": "variador-empuje", "nombre": "variador del motor de empuje",
               "masa_kg": 0.2 * m["empuje"], "en": [600, 0, Z_FUSELAJE * 1000]},
              {"id": "electronica", "nombre": "controladora, ordenador de a bordo, GPS, "
               "telemetría y receptor", "masa_kg": AVIONICA_KG, "en": [X_ELECTRONICA, 0, -28],
               "caja": list(CAJA_ELECTRONICA)}]
    for lado, s in (("d", 1), ("i", -1)):
        for donde, y in zip(("interior", "exterior"), SERVO_Y):
            x, z = ala(y, SERVO_CUERDA)
            cosas.append({"id": f"servo-{lado}-{donde}", "nombre": f"servo del elevón {donde}",
                          "masa_kg": SERVOS_KG / 4, "en": [x, s * y, z], "caja": list(CAJA_SERVO)})
    z_bateria = Z_TECHO_BATERIA - CAJA_BATERIA[2] / 2
    z_carga = z_bateria - CAJA_BATERIA[2] / 2 - 4 - CAJA_CARGA[2] / 2
    cosas.append({"id": "carga", "nombre": "carga: dos cámaras y un lidar", "masa_kg": CARGA_KG,
                  "en": [x_cg, 0, z_carga], "caja": list(CAJA_CARGA)})
    momento = sum(c["masa_kg"] * (c["en"][0] - x_cg) for c in cosas)
    cosas.append({"id": "bateria", "nombre": f"batería 6S{r['bateria']['paralelo']}P",
                  "masa_kg": m["bateria"], "en": [x_cg - momento / m["bateria"], 0, z_bateria],
                  "caja": list(CAJA_BATERIA)})
    for c in cosas:
        c["masa_kg"] = round(c["masa_kg"], 4)
        c["en"] = [round(v, 1) for v in c["en"]]
    return cosas


def equilibrio_de(cosas, x_np, mac, sin=()):
    """Centro de gravedad (mm) y margen estático sin las cosas `sin`."""
    quedan = [c for c in cosas if c["id"] not in sin]
    masa = sum(c["masa_kg"] for c in quedan)
    cg = [sum(c["masa_kg"] * c["en"][k] for c in quedan) / masa for k in range(3)]
    return {"masa_kg": round(masa, 3), "cg_mm": [round(v, 1) for v in cg],
            "margen": round((x_np - cg[0]) / mac, 4)}


def dimensionar():
    aeronave, ala = avion(-4.0)
    area = sum(w.area(type="wetted") for w in aeronave.wings) + aeronave.fuselages[0].area_wetted()
    impreso = area * 1e4 * PIEL_MM / 10 * LWPLA_G_CM3 * NERVIOS / 1000
    fijo = impreso + AVIONICA_KG + SERVOS_KG + CARBONO_KG + CARGA_KG
    paralelo = 1
    while True:
        bateria = 6 * paralelo * CELDA["g"] * EMPAQUE / 1000
        masa = fijo + bateria
        for _ in range(30):      # lo comprado crece con el avión: punto fijo
            sustentacion = KG_POR_KG_EMPUJE * EMPUJE_SOBRE_PESO * masa
            empuje = EMPUJE_CRUCERO_FRACCION * masa
            masa = fijo + bateria + sustentacion + empuje
        peso = masa * G
        eq = equilibrado(peso)
        aeronave, ala = avion(eq["torsion"], eq["x_cg"])
        a = aero(aeronave, eq["alfa"])
        resistencia = a["D"] + 0.5 * RHO * V_CRUCERO ** 2 * CDA_ROTORES_M2
        p_crucero = resistencia * V_CRUCERO / RENDIMIENTO_CRUCERO
        disco = 4 * math.pi * (HELICE_VTOL_PULG * 0.0254 / 2) ** 2
        p_vtol = peso ** 1.5 / math.sqrt(2 * RHO * disco) / FIGURA_MERITO / RENDIMIENTO_MOTOR_VTOL
        wh = 6 * paralelo * CELDA["Wh"]
        horas = (wh * (1 - RESERVA) - p_vtol * MIN_VTOL / 60) / p_crucero
        if horas >= HORAS or paralelo > 20:
            break
        paralelo += 1
    s = ala.area()
    clmax = 1.0     # MH 60 autoestable, sin flaps: menos que un perfil normal
    # Lo que cuestan los cinco motores: el peso de los cuatro de sustentación
    # y su resistencia parados se pagan en crucero; el despegue y el aterrizaje,
    # en vuelo vertical.
    sin_vtol = (masa - sustentacion) * G
    p_sin = (a["D"] * sin_vtol / peso) * V_CRUCERO / RENDIMIENTO_CRUCERO
    return {
        "carga_kg": CARGA_KG,
        "envergadura_m": round(2 * estaciones(0)[-1][0], 3),
        "area_alar_m2": round(s, 4),
        "alargamiento": round(ala.aspect_ratio(), 2),
        "cuerda_media_m": round(ala.mean_aerodynamic_chord(), 4),
        "masa_kg": {
            "impreso (LW-PLA, estimado)": round(impreso, 3),
            "carbono: largueros y vigas": CARBONO_KG,
            "4 motores de sustentación, variadores y hélices": round(sustentacion, 3),
            "motor de empuje, variador y hélice plegable": round(empuje, 3),
            "controladora, ordenador de a bordo, GPS, telemetría y cables": AVIONICA_KG,
            "cuatro servos de los elevones": SERVOS_KG,
            "carga útil": CARGA_KG,
            f"batería 6S{paralelo}P de {CELDA['nombre']}": round(bateria, 3),
            "total": round(masa, 3),
        },
        "_masas": {"impreso": impreso, "sustentacion": sustentacion, "empuje": empuje,
                   "bateria": bateria, "total": masa},
        "_centroide_impreso_m": centroide_impreso(aeronave),
        "_x_np_m": eq["x_np"], "_mac_m": ala.mean_aerodynamic_chord(),
        "bateria": {"serie": 6, "paralelo": paralelo, "Wh": round(wh, 1)},
        "carga_alar_kg_m2": round(masa / s, 2),
        "crucero": {"velocidad_m_s": V_CRUCERO, "alfa_grados": round(eq["alfa"], 2),
                    "CL": round(a["CL"], 3), "L_D": round(a["L"] / resistencia, 2),
                    "resistencia_N": round(resistencia, 2), "potencia_W": round(p_crucero, 1)},
        "vtol": {"potencia_W": round(p_vtol), "minutos": MIN_VTOL,
                 "empuje_max_por_motor_kg": round(EMPUJE_SOBRE_PESO * masa / 4, 2)},
        "lo_que_cuestan_los_rotores": {
            "peso_kg": round(sustentacion + CARBONO_KG * 0.5, 3),
            "potencia_crucero_W": round(p_crucero - p_sin, 1),
            "energia_vertical_Wh": round(p_vtol * MIN_VTOL / 60, 1),
        },
        "autonomia_h": round(horas, 2),
        "alcance_km": round(horas * V_CRUCERO * 3.6),
        "perdida_m_s": round(math.sqrt(2 * peso / (RHO * s * clmax)), 1),
        "equilibrio": {"torsion_punta_grados": eq["torsion"], "punto_neutro_x_m": round(eq["x_np"], 4),
                       "cg_x_m": round(eq["x_cg"], 4), "margen": 0.07, "Cm": round(eq["Cm"], 4),
                       "Cm_alfa": round(eq["Cm_alfa"], 3), "Cn_beta": round(eq["Cn_beta"], 4)},
        "rotores": rotores(eq["x_cg"], ala),
        "estaciones": [list(e) for e in estaciones(eq["torsion"])],
        "supuestos": {"rendimiento_crucero": RENDIMIENTO_CRUCERO, "figura_de_merito": FIGURA_MERITO,
                      "empuje_sobre_peso": EMPUJE_SOBRE_PESO, "kg_por_kg_de_empuje": KG_POR_KG_EMPUJE,
                      "minutos_vtol": MIN_VTOL, "reserva": RESERVA, "clmax": clmax,
                      "lwpla_g_cm3": LWPLA_G_CM3, "piel_mm": PIEL_MM, "nervios": NERVIOS,
                      "cda_rotores_m2": CDA_ROTORES_M2},
    }


def perfiles():
    """Las coordenadas que dibuja FreeCAD, en fracciones de cuerda, con el
    borde de salida abierto un 0,6 % de la cuerda para poder imprimirlo."""
    salida = {}
    for de in ("mh60", "mh78", "naca0008"):
        a = asb.Airfoil(de).repanel(n_points_per_side=24)
        # `set_TE_thickness` de AeroSandbox 4.2 abría el borde al revés y las
        # dos caras se cruzaban (FreeCAD: «lados que se cruzan»). Se abre aquí:
        # cada cara se aparta en proporción a la distancia al borde de ataque.
        xy = a.coordinates
        delante = int(np.argmin(xy[:, 0]))
        puntos = [[float(x), float(z) + (0.003 * x if i < delante else -0.003 * x if i > delante
                                         else 0.0)] for i, (x, z) in enumerate(xy)]
        salida[de] = {
            "puntos": [[round(x, 5), round(z, 5)] for x, z in puntos],
            "comba": {str(f): round(_num(a.local_camber(f)), 5) for f in (0.25, 0.6)},
            "grueso": {str(f): round(_num(a.local_thickness(f)), 5) for f in (0.25, 0.6)},
        }
    return salida


def diseno_mm(r):
    """Lo que el kit necesita para dibujarlo (`kit.avion_pieza`), en mm."""
    ro = r["rotores"]
    x_cg = round(r["equilibrio"]["cg_x_m"] * 1000)
    return {
        "estaciones": [[round(y * 1000, 1), round(x * 1000, 1), round(z * 1000, 1),
                        round(c * 1000, 1), t, p] for y, x, z, c, t, p in r["estaciones"]],
        "raiz": 2,
        "fuselaje": [[round(x * 1000), round(w * 1000), round(h * 1000), round(z * 1000)]
                     for x, w, h, z in FUSELAJE],
        "z_fuselaje": round(Z_FUSELAJE * 1000),
        "largueros": [[0.25, 10], [0.6, 6]],
        "elevon": [650, 0.75],
        "deriva": {"x": round(X_DERIVA * 1000), "cuerda": [150, 90], "alto": round(ALTO_DERIVA * 1000)},
        "rotores": {"y": round(ro["y_viga"] * 1000), "x": [round(ro["x_delante"] * 1000),
                                                         round(ro["x_detras"] * 1000)],
                    "viga": 16, "helice": round(ro["helice_vtol_pulg"] * 25.4)},
        "empuje": {"x": 720, "helice": round(ro["helice_empuje_pulg"] * 25.4)},
        # Bajo la carga, en el centro de gravedad: el lidar en medio y una
        # cámara a cada lado. Estaban en el morro.
        "ventanas": [[x_cg - 62, 40, 34], [x_cg, 70, 60], [x_cg + 62, 40, 34]],
        "elevones": [list(e) for e in ELEVONES],
        "dentro": r["dentro"],
        "equilibrio": {"punto_neutro_x": round(r["_x_np_m"] * 1000, 1),
                       "cuerda_media": round(r["_mac_m"] * 1000, 1),
                       "margen_minimo": MARGEN_MINIMO, "margen_maximo": MARGEN_MAXIMO},
    }


if __name__ == "__main__":
    r = dimensionar()
    r["dentro"] = dentro(r)
    x_np, mac = r["_x_np_m"] * 1000, r["_mac_m"] * 1000
    r["equilibrio"]["con_carga"] = equilibrio_de(r["dentro"], x_np, mac)
    r["equilibrio"]["sin_carga"] = equilibrio_de(r["dentro"], x_np, mac, sin=("carga",))
    r["diseno"] = diseno_mm(r)
    for k in [k for k in r if k.startswith("_")] + ["dentro"]:
        del r[k]
    r["perfiles"] = perfiles()
    texto = json.dumps(r, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(texto)
    print(json.dumps({k: v for k, v in r.items() if k not in ("perfiles", "estaciones")},
                     ensure_ascii=False, indent=1))
