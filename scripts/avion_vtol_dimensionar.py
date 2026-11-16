"""Dimensiona el VTOL de la Fase 13 con AeroSandbox (2026-11-16).

Lo pidió él: un VTOL de ala integrada «como el TerraHawk pero mejorado»,
de 2 m o más, con la carga del TerraHawk (hasta 1 kg: dos cámaras y un
lidar), unas 3 horas y 200–250 km. Y el 2026-11-16: «tú diseña y usa lo que
habías dicho» (OpenVSP y AeroSandbox), «quiero que se haga rápido».

Esto lo escribió el asistente a mano: no es nota del sistema. Las masas de lo
comprado y los rendimientos son estimaciones del asistente y van apuntados
como tales en el informe; la aerodinámica es la de AeroSandbox (AeroBuildup
con NeuralFoil), no un túnel ni un vuelo.

Uso (en el PC, donde está AeroSandbox):
    .venv\\Scripts\\python.exe scripts\\avion_vtol_dimensionar.py salida.json
"""

import json
import math
import sys

import aerosandbox as asb
import aerosandbox.numpy as np

RHO = 1.225          # aire a nivel del mar
G = 9.81
V_CRUCERO = 20.0     # 72 km/h, la del TerraHawk según su captura
HORAS = 3.0
CARGA_KG = 1.0       # dos cámaras y un lidar (la del TerraHawk de 2 m)

# --- Supuestos del asistente (no medidos) -----------------------------------
RENDIMIENTO_CRUCERO = 0.60   # hélice 0,75 × motor 0,85 × variador 0,95
FIGURA_MERITO = 0.60         # rotores de sustentación de 15"
RENDIMIENTO_MOTOR_VTOL = 0.85
MIN_VTOL = 3.0               # despegue, aterrizaje y transiciones, en minutos
RESERVA = 0.15               # de la batería que no se gasta
CELDA = {"nombre": "21700 de 4,5 Ah (tipo Molicel P45B)", "Wh": 16.2, "g": 70.0}
EMPAQUE = 1.08               # níquel, cables y BMS sobre el peso de las celdas
LWPLA_G_CM3 = 0.75           # LW-PLA espumado
PIEL_MM = 0.6                # una pared
NERVIOS = 1.5                # costillas, largueros y orejas sobre la piel
COMPRADO_KG = {
    "4 motores de sustentación (clase 4014, 380 kV), variadores y hélices de 15\"": 4 * 0.275,
    "motor de empuje (clase 3515), variador y hélice de 13\"": 0.175,
    "controladora, GPS, telemetría, receptor y cables": 0.25,
    "4 servos de 9 g (alerones y timones)": 0.04,
    "largueros de carbono (Ø12 y Ø8, 2 m) y vigas de Ø20 (2 × 1,3 m)": 0.09 + 0.05 + 0.21,
}


def avion():
    perfil = asb.Airfoil("sd7037")
    cola = asb.Airfoil("naca0009")
    # El ala integrada: el centro es largo para tapar el fuselaje, y desde los
    # 0,25 m va un ala de 230 a 150 mm de cuerda, que cabe de pie en una cama
    # de 235.
    ala = asb.Wing(
        name="ala", symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.00, 0.00, 0], chord=0.50, twist=2, airfoil=perfil),
            asb.WingXSec(xyz_le=[0.12, 0.17, 0], chord=0.30, twist=2, airfoil=perfil),
            asb.WingXSec(xyz_le=[0.16, 0.25, 0.005], chord=0.23, twist=1.5, airfoil=perfil),
            asb.WingXSec(xyz_le=[0.24, 1.30, 0.055], chord=0.15, twist=-1, airfoil=perfil),
        ])
    # Cola en H sobre las dos vigas: el estabilizador va arriba de las derivas
    # para que la hélice de empuje no le sople.
    y_viga, x_cola = 0.38, 1.02
    horizontal = asb.Wing(
        name="estabilizador", symmetric=True,
        xsecs=[asb.WingXSec(xyz_le=[x_cola, 0, 0.20], chord=0.13, twist=-2, airfoil=cola),
               asb.WingXSec(xyz_le=[x_cola, y_viga, 0.20], chord=0.13, twist=-2, airfoil=cola)])
    derivas = [asb.Wing(
        name=f"deriva {lado}",
        xsecs=[asb.WingXSec(xyz_le=[x_cola - 0.02, s * y_viga, 0.0], chord=0.17, airfoil=cola),
               asb.WingXSec(xyz_le=[x_cola + 0.01, s * y_viga, 0.20], chord=0.13, airfoil=cola)])
        for lado, s in (("izquierda", -1), ("derecha", 1))]
    # Fuselaje: la batería, la carga y la aviónica; las cámaras y el lidar
    # van en el morro, mirando abajo y adelante, tras ventanas al ras.
    secciones = [(-0.20, 0.02, 0.02), (-0.12, 0.13, 0.11), (0.0, 0.17, 0.14),
                 (0.30, 0.17, 0.14), (0.55, 0.12, 0.10), (0.72, 0.05, 0.05)]
    fuselaje = asb.Fuselage(name="fuselaje", xsecs=[
        asb.FuselageXSec(xyz_c=[x, 0, -0.02], width=w, height=h, shape=3)
        for x, w, h in secciones])
    vigas = [asb.Fuselage(name=f"viga {s}", xsecs=[
        asb.FuselageXSec(xyz_c=[x, s * y_viga, -0.03], radius=0.011) for x in (-0.30, 1.15)])
        for s in (-1, 1)]
    return asb.Airplane(name="VTOL", wings=[ala, horizontal, *derivas],
                        fuselages=[fuselaje, *vigas]), ala, fuselaje


def _num(x):
    """AeroSandbox devuelve vectores de un elemento."""
    return float(np.ravel(x)[0])


def masa_impresa_kg(aeronave):
    area = sum(w.area(type="wetted") for w in aeronave.wings) + sum(
        f.area_wetted() for f in aeronave.fuselages[:1])
    return area * 1e4 * PIEL_MM / 10 * LWPLA_G_CM3 * NERVIOS / 1000, area


def dimensionar():
    aeronave, ala, fuselaje = avion()
    impreso, mojada = masa_impresa_kg(aeronave)
    seca = impreso + sum(COMPRADO_KG.values()) + CARGA_KG
    paralelo = 1
    while True:
        celdas = 6 * paralelo
        bateria = celdas * CELDA["g"] * EMPAQUE / 1000
        masa = seca + bateria
        peso = masa * G
        # Ángulo de ataque que sustenta en crucero (bisección sobre AeroBuildup).
        lo, hi = -4.0, 12.0
        for _ in range(30):
            alfa = (lo + hi) / 2
            aero = asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(
                velocity=V_CRUCERO, alpha=alfa)).run()
            aero = {k: _num(v) for k, v in aero.items() if k in ("L", "D", "CL", "CD")}
            sustenta = aero["L"]
            lo, hi = (alfa, hi) if sustenta < peso else (lo, alfa)
        # Las vigas llevan cuatro hélices paradas y sus motores: resistencia
        # que AeroBuildup no ve. 0,012 m² de CdA, estimación del asistente.
        resistencia = aero["D"] + 0.5 * RHO * V_CRUCERO ** 2 * 0.012
        p_crucero = resistencia * V_CRUCERO / RENDIMIENTO_CRUCERO
        disco = 4 * math.pi * (15 * 0.0254 / 2) ** 2
        p_vtol = peso ** 1.5 / math.sqrt(2 * RHO * disco) / FIGURA_MERITO / RENDIMIENTO_MOTOR_VTOL
        wh = celdas * CELDA["Wh"]
        util = wh * (1 - RESERVA) - p_vtol * MIN_VTOL / 60
        horas = util / p_crucero
        if horas >= HORAS or paralelo > 20:
            break
        paralelo += 1
    estab = asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(
        velocity=V_CRUCERO, alpha=alfa)).run_with_stability_derivatives()
    mac = ala.mean_aerodynamic_chord()
    x_np = float(np.ravel(estab["x_np"])[0])
    x_cg = x_np - 0.10 * mac          # margen estático del 10 %
    s = ala.area()
    clmax = 1.15                      # SD7037 a Re ~250 000, sin flaps
    return {
        "envergadura_m": round(ala.span(), 3),
        "area_alar_m2": round(s, 4),
        "alargamiento": round(ala.aspect_ratio(), 2),
        "cuerda_media_m": round(mac, 4),
        "area_mojada_m2": round(float(mojada), 3),
        "masa_kg": {
            "impreso (LW-PLA, estimado)": round(float(impreso), 3),
            **{k: round(v, 3) for k, v in COMPRADO_KG.items()},
            "carga útil": CARGA_KG,
            f"batería 6S{paralelo}P de {CELDA['nombre']}": round(bateria, 3),
            "total": round(float(masa), 3),
        },
        "bateria": {"serie": 6, "paralelo": paralelo, "Wh": round(wh, 1)},
        "carga_alar_kg_m2": round(float(masa / s), 2),
        "crucero": {
            "velocidad_m_s": V_CRUCERO, "alfa_grados": round(float(alfa), 2),
            "CL": round(float(aero["CL"]), 3), "L_D": round(float(aero["L"] / resistencia), 2),
            "resistencia_N": round(float(resistencia), 2),
            "potencia_W": round(float(p_crucero), 1),
        },
        "vtol": {"potencia_W": round(float(p_vtol), 0),
                 "empuje_por_motor_kg": round(float(masa / 4), 2), "minutos": MIN_VTOL},
        "autonomia_h": round(float(horas), 2),
        "alcance_km": round(float(horas * V_CRUCERO * 3.6), 0),
        "perdida_m_s": round(math.sqrt(2 * float(peso) / (RHO * s * clmax)), 1),
        "estabilidad": {"punto_neutro_x_m": round(x_np, 4), "cg_x_m": round(x_cg, 4),
                        "margen": 0.10,
                        "Cm_alfa": round(float(np.ravel(estab["Cma"])[0]), 4),
                        "Cn_beta": round(float(np.ravel(estab["Cnb"])[0]), 4)},
        "supuestos": {
            "rendimiento_crucero": RENDIMIENTO_CRUCERO, "figura_de_merito": FIGURA_MERITO,
            "minutos_vtol": MIN_VTOL, "reserva": RESERVA, "clmax": clmax,
            "lwpla_g_cm3": LWPLA_G_CM3, "piel_mm": PIEL_MM, "nervios": NERVIOS,
            "cda_rotores_m2": 0.012,
        },
    }


def perfiles():
    """Las coordenadas que dibuja FreeCAD, en fracciones de cuerda. El borde
    de salida va engrosado al 0,6 % de la cuerda (0,9 mm en la punta): uno
    afilado no se imprime y se rompe al tocarlo."""
    salida = {}
    for nombre, de in (("ala", "sd7037"), ("cola", "naca0009")):
        a = asb.Airfoil(de).repanel(n_points_per_side=24)
        # `set_TE_thickness` de AeroSandbox 4.2 abría el borde al revés y las
        # dos caras se cruzaban (FreeCAD: «lados que se cruzan»). Se abre aquí:
        # cada cara se aparta en proporción a la distancia al borde de ataque.
        xy = a.coordinates
        delante = int(np.argmin(xy[:, 0]))
        puntos = [[float(x), float(z) + (0.003 * x if i < delante else -0.003 * x if i > delante
                                         else 0.0)] for i, (x, z) in enumerate(xy)]
        salida[nombre] = {
            "de": de,
            "puntos": [[round(x, 5), round(z, 5)] for x, z in puntos],
            "comba": {str(f): round(_num(a.local_camber(f)), 5) for f in (0.27, 0.62)},
            "grueso": {str(f): round(_num(a.local_thickness(f)), 5) for f in (0.27, 0.62)},
        }
    return salida


if __name__ == "__main__":
    r = dimensionar()
    r["perfiles"] = perfiles()
    texto = json.dumps(r, ensure_ascii=False, indent=2)
    print(texto)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(texto)
