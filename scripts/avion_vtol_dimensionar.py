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
AVIONICA_KG = 0.25 + 0.04       # controladora, GPS, telemetría, cables; 4 servos
CARBONO_KG = 0.06 + 0.03 + 0.09  # larguero Ø10, larguero Ø6, vigas Ø16

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
    fuselaje = asb.Fuselage(name="fuselaje", xsecs=[
        asb.FuselageXSec(xyz_c=[xs, 0, Z_FUSELAJE], width=w, height=h, shape=3)
        for xs, w, h in ((-0.22, 0.02, 0.02), (-0.14, 0.11, 0.09), (0.0, 0.15, 0.12),
                         (0.35, 0.15, 0.12), (0.60, 0.09, 0.08), (0.72, 0.04, 0.04))])
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


def dimensionar():
    aeronave, ala = avion(-4.0)
    area = sum(w.area(type="wetted") for w in aeronave.wings) + aeronave.fuselages[0].area_wetted()
    impreso = area * 1e4 * PIEL_MM / 10 * LWPLA_G_CM3 * NERVIOS / 1000
    fijo = impreso + AVIONICA_KG + CARBONO_KG + CARGA_KG
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
            "controladora, GPS, telemetría, cables y servos": AVIONICA_KG,
            "carga útil": CARGA_KG,
            f"batería 6S{paralelo}P de {CELDA['nombre']}": round(bateria, 3),
            "total": round(masa, 3),
        },
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
    return {
        "estaciones": [[round(y * 1000, 1), round(x * 1000, 1), round(z * 1000, 1),
                        round(c * 1000, 1), t, p] for y, x, z, c, t, p in r["estaciones"]],
        "raiz": 2,
        "fuselaje": [[-220, 20, 20], [-140, 110, 90], [0, 150, 120], [350, 150, 120],
                     [600, 90, 80], [720, 40, 40]],
        "z_fuselaje": round(Z_FUSELAJE * 1000),
        "largueros": [[0.25, 10], [0.6, 6]],
        "elevon": [650, 0.75],
        "deriva": {"x": round(X_DERIVA * 1000), "cuerda": [150, 90], "alto": round(ALTO_DERIVA * 1000)},
        "rotores": {"y": round(ro["y_viga"] * 1000), "x": [round(ro["x_delante"] * 1000),
                                                         round(ro["x_detras"] * 1000)],
                    "viga": 16, "helice": round(ro["helice_vtol_pulg"] * 25.4)},
        "empuje": {"x": 720, "helice": round(ro["helice_empuje_pulg"] * 25.4)},
        "ventanas": [[-100, 40, 34], [10, 40, 34], [140, 84, 72]],
    }


if __name__ == "__main__":
    r = dimensionar()
    r["diseno"] = diseno_mm(r)
    r["perfiles"] = perfiles()
    texto = json.dumps(r, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(texto)
    print(json.dumps({k: v for k, v in r.items() if k not in ("perfiles", "estaciones")},
                     ensure_ascii=False, indent=1))
