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
import os
import sys

import aerosandbox as asb
import aerosandbox.numpy as np

RHO, G = 1.225, 9.81
V_CRUCERO = 20.0     # 72 km/h, la del TerraHawk según su captura
CARGA_KG = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

# --- Lo que se compra (él, el 2026-11-16) -------------------------------------
# «usemos motores y bateria que pueda comprar en amazon» y «algo de 15k mAh
# para tener un poco mas de 1 hora de vuelo? o usemos 6s». Antes se buscaba
# cuántas celdas 21700 daban 3 horas: con el peso real de las piezas eran 54
# (6S9P, 4,1 kg) y 9,3 kg de avión, y él lo vio ilógico («tiene mas sentido
# una bateria 4s grandecita»). Ahora la batería y los motores son los de un
# anuncio y lo que sale es la autonomía. Las cifras son las de cada anuncio,
# no medidas.
BATERIA = {"nombre": "batería LiPo 6S 16 000 mAh", "serie": 6, "mAh": 16000, "kg": 1.93,
           "caja": (203, 82, 70)}         # Tattu Plus 15C, XT90S
# El 4312 de 400 KV: 3 kg por hélice en 6S con hélices de 15 a 18″, 162 g. Con
# hélices de 13″ ningún motor de Amazon con cifras daba los 3,3 kg que pedía.
MOTOR_VTOL = {"empuje_max_kg": 3.0, "kg": 0.162}
VARIADOR_KG = 0.055                       # 60 A 2–6S; supuesto del asistente
HELICE_VTOL_KG = 0.021                    # 15 × 5,5 de carbono (Xoar: 21 ± 2 g)
EMPUJE_KG = 0.18    # 3510 de 600 KV, su variador y la plegable de 10 × 6: supuesto
EMPUJE_SOBRE_PESO_MINIMO = 1.5   # criterio del asistente: margen para una ráfaga
# Lo que hay que comprar, con su anuncio. Las cantidades salen del diseño.
COMPRAS = [
    ("Batería LiPo 6S 16 000 mAh 15C, XT90S (Tattu Plus)", 1,
     "https://www.amazon.com/Tattu-16000mAh-22-2V-Battery-XT90S/dp/B0C6QRWBGX"),
    ("Motor 4312 400KV, 3 kg por hélice en 6S (sustentación)", 4,
     "https://www.amazon.com/Brushless-Thrust-Bearings-Photography-Industrial/dp/B0FD6JMVMB"),
    ("Hélices 15 × 5,5 de carbono, pares CW + CCW (sustentación)", 2,
     "https://www.amazon.com/QWINOUT-Propeller-Multicopter-Quadcopter-Hexacopter/dp/B07ZYLX92M"),
    ("Variador 60 A 2–6S (4 de sustentación y 1 de empuje)", 5,
     "https://www.amazon.com/Brushless-Controller-RC-Helicopter-Multi-axis/dp/B0FNM5YV9J"),
    ("Motor 3510 600KV 3–6S (empuje)", 1, "https://www.amazon.com/clp/B0FDR8FW7G"),
    ("Hélice plegable 10 × 6 con buje para eje de 4 mm (empuje)", 1,
     "https://www.amazon.com/Folding-Propeller-D38%C3%97H35mm-Diameter-Airplane/dp/B07SG35RGG"),
    ("Servo de ala KST X10 Mini, 10 mm de grueso (elevones)", 4,
     "https://www.amazon.com/Servo-Aluminum-Operating-Voltage-Coreless/dp/B0GTLHDGL1"),
    ("Tubo de carbono 16 × 14 × 1000 mm (vigas de los rotores)", 2,
     "https://www.amazon.com/WHABEST-1000MM-Glossy-Quadcopter-Hexrcopter/dp/B0777KH429"),
    ("Tubos de carbono 10 × 8 × 1000 mm, paquete de 2 (larguero delantero)", 1,
     "https://www.amazon.com/WHABEST-Carbon-Quadcopter-Hexacopter-10x8x1000mm/dp/B08B345NGX"),
    ("Tubo de carbono 6 × 4 × 1000 mm (larguero trasero)", 2,
     "https://www.amazon.com/1000MM-carbon-Fiber-surface-Tubing/dp/B07776WJC4"),
    ("Varilla de carbono maciza redonda de Ø2, de 500 mm (elevones exteriores y guías del "
     "cuerpo central)", 2,
     "https://www.amazon.com/s?k=carbon+fiber+rod+2mm+round+500mm"),
    ("Pixhawk 6C con módulo de potencia PM02 y GPS M10", 1,
     "https://www.amazon.com/Controller-High-Performance-STM32H743-Processor-Pre-Installed/dp/B0H4RCG8WG"),
    ("Sensor de velocidad MS4525DO con tubo pitot", 1,
     "https://www.amazon.com/MS4525DO-Airspeed-Differential-Pressure-Monitoring/dp/B0H2GVVF3K"),
    ("Radio de telemetría SiK V3 (915 o 433 MHz, la legal en su país)", 1,
     "https://www.amazon.com/Holybro-Telemetry-Open-Source-Plug-N-Play-Controller/dp/B0HNBJHVBC"),
    ("Raspberry Pi 5 de 8 GB con disipador activo", 1,
     "https://www.amazon.com/Raspberry-Basic-Including-Active-Cooler/dp/B0CX19SV2N"),
]

# --- Supuestos del asistente (no medidos) ------------------------------------
RENDIMIENTO_CRUCERO = 0.60      # hélice plegable 0,75 × motor 0,85 × variador 0,95
FIGURA_MERITO = 0.60
RENDIMIENTO_MOTOR_VTOL = 0.85
MIN_VTOL = 3.0                  # despegue, aterrizaje y transiciones
RESERVA = 0.15                  # una LiPo no se baja de 3,7 V por celda
LWPLA_G_CM3, PIEL_MM, NERVIOS = 0.75, 0.6, 1.4
# Lo impreso pesado en sus STL (`scripts/avion_vtol_masas.py`). Manda sobre
# la estimación de arriba, que solo vale para la primera vuelta: con ella el
# dimensionado contaba 0,94 kg cuando las piezas, macizas, pesaban 6–7.
IMPRESO_MEDIDO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avion_vtol_impreso.json")


def impreso_medido():
    """{masa_kg, centro_mm, proyecto} de lo pesado, o None si no se ha pesado."""
    if not os.path.exists(IMPRESO_MEDIDO):
        return None
    with open(IMPRESO_MEDIDO, encoding="utf-8") as f:
        return json.load(f)
CDA_ROTORES_M2 = 0.006          # cuatro hélices paradas en línea y sus motores
# Controladora, ordenador de a bordo (una Raspberry Pi 5 con disipador:
# la pidió él el 2026-11-16), GPS, telemetría, receptor y cables.
AVIONICA_KG = 0.31
SERVOS_KG = 4 * 0.025            # cuatro servos finos de ala, uno por elevón
LARGUEROS_KG, VIGAS_KG = (0.06, 0.03), 0.09   # Ø10 y Ø6; las dos vigas Ø16
CARBONO_KG = sum(LARGUEROS_KG) + VIGAS_KG

# --- Lo de dentro (mm): cajas que ocupan sitio -----------------------------------
# La LiPo de 203 × 82 × 70 de su anuncio, con 2 mm de espuma por cada lado de
# los de abajo y de los lados. Era la 6S6P de 21700, de 210 × 130 × 46.
CAJA_BATERIA = (BATERIA["caja"][0] + 3, BATERIA["caja"][1] + 4, BATERIA["caja"][2] + 2)
CAJA_CARGA = (160, 80, 50)       # dos cámaras y un lidar, en su bandeja
# La controladora y la Raspberry Pi una detrás de otra. Con 110 × 70 en
# x = -60 se salía del morro, que ahí mide 112 × 92 por dentro (cuentas del
# 2026-11-16).
CAJA_ELECTRONICA = (120, 60, 40)
X_ELECTRONICA = -20
# Entra por la panza y se empuja hacia delante: tiene que pasar bajo el
# larguero de Ø10 (z = -4,5 en el centro, menos 5, menos 1 de aire: -10,5).
# En -28 su techo quedaba en -8 y no pasaba
# (`test_la_electronica_entra_por_la_panza_y_se_desliza_hasta_su_sitio`).
Z_ELECTRONICA = -33
# El KST X10 Mini, tumbado: 30 × 10 × 30 según su anuncio, y las orejas de
# los tornillos a lo largo del ala (supuesto del asistente hasta tenerlo en la
# mano). Era una caja de 24 × 34 de un servo cualquiera.
CAJA_SERVO = (31, 38, 10)
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
HELICE_VTOL_PULG = 15        # la del motor de Amazon (de 15 a 18″); eran 13
HELICE_EMPUJE_PULG = 10      # el crucero pide 4,4 N: sobra
Z_FUSELAJE = -0.02           # el eje del fuselaje y de la hélice de empuje
# La viga va donde la pone el kit, justo bajo el ala. Las derivas y las patas
# son el tren de aterrizaje: con 130 mm la hélice de empuje bajaba 5 mm más
# que ellas y tocaba el suelo al posarse (cuentas del 2026-11-16); se alargan
# hasta dejarle 30 mm.
X_DERIVA, Z_VIGA = 0.72, -0.012
# El alto de las derivas (m) sale de pedirles estabilidad de guiñada:
# Cn_beta de 0,001 por grado o más respecto al centro de gravedad, el borde
# bajo de lo típico en un avión ligero (criterio del asistente). Se calculaba
# respecto al morro y daba 0,0555; respecto al CG era 0,0156 (visto al
# simularlo, 2026-11-16). Crecen de alto y no de cuerda: con 165 mm de alto
# una deriva tiene un alargamiento de 0,2 y casi no sustenta; con cuerdas
# cinco veces mayores Cn_beta no pasaba de 0,023, y con 280 mm de alto llega
# a 0,076 (AeroSandbox, ese día). El alto mínimo es el del tren: 30 mm de la
# hélice de empuje al suelo. Más alto, también las patas.
CN_BETA_MINIMO = 0.001 * 180 / math.pi
CUERDAS_DERIVA = (0.15, 0.09)
HUECO_SUELO = 0.03
ALTO_DERIVA = round(Z_VIGA - (Z_FUSELAJE - HELICE_EMPUJE_PULG * 0.0254 / 2 - HUECO_SUELO), 3)
DERIVA = (*CUERDAS_DERIVA, ALTO_DERIVA)
# El fuselaje: (x, ancho, alto, z del centro). En el centro de gravedad se
# ahonda hacia abajo: arriba, bajo los largueros, la batería; debajo, la
# carga. Las dos tienen que ir ahí (él, el 2026-11-16: «la batería debe
# estar en un lugar donde no modifique mucho el centro de gravedad»): con
# la carga en el morro, quitarla echaba el centro de gravedad 35–83 mm
# atrás, más allá del punto neutro, y el ala volante se volvía inestable.
# Con la LiPo (70 mm de alto, 24 más que el pack de 21700) la carga bajaba a
# z = -139 y su esquina se salía 1,5 mm del hueco: el vientre baja 20 mm donde
# va la carga, con el techo donde estaba. Solo ahí: bajándolo desde x = 180
# la unión del ala con el fuselaje del cuerpo central 2 volaba 5,4 mm y pedía
# soportes (2026-11-16).
FUSELAJE = ((-0.22, 0.02, 0.02, -0.02), (-0.14, 0.11, 0.09, -0.02), (0.0, 0.15, 0.13, -0.03),
            (0.18, 0.16, 0.18, -0.05), (0.24, 0.16, 0.20, -0.06), (0.40, 0.16, 0.20, -0.06),
            (0.60, 0.09, 0.08, -0.02),
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


def avion(torsion_punta, x_cg=0.0, deriva=DERIVA):
    est = estaciones(torsion_punta)
    c0, c1, alto = deriva
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
        asb.WingXSec(xyz_le=[X_DERIVA, Y_VIGA, Z_VIGA], chord=c0, airfoil=asb.Airfoil("naca0008")),
        asb.WingXSec(xyz_le=[X_DERIVA + c0 - c1 + 0.01, Y_VIGA, Z_VIGA - alto], chord=c1,
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


def equilibrado(peso, margen=0.07, deriva=DERIVA):
    """La torsión de la punta que deja el ala volante en equilibrio (Cm = 0 en
    el centro de gravedad) con un margen estático de `margen`."""
    mejor = None
    for torsion in np.linspace(0, -8, 17):
        aeronave, ala = avion(float(torsion), deriva=deriva)
        alfa = alfa_que_sustenta(aeronave, peso)
        est = asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(
            velocity=V_CRUCERO, alpha=alfa)).run_with_stability_derivatives()
        x_np = _num(est["x_np"])
        x_cg = x_np - margen * ala.mean_aerodynamic_chord()
        aeronave, ala = avion(float(torsion), x_cg, deriva)
        cm = aero(aeronave, alfa)["Cm"]
        if mejor is None or abs(cm) < abs(mejor["Cm"]):
            mejor = {"torsion": float(torsion), "alfa": alfa, "x_np": x_np, "x_cg": x_cg,
                     "Cm": cm, "Cm_alfa": _num(est["Cma"])}
    # Las derivadas de guiñada, respecto al centro de gravedad: `est` las da
    # respecto a la referencia del avión, que arriba es el morro (x = 0). Así
    # se calculó hasta el 2026-11-16 y salía 0,0555 en vez de 0,0156.
    aeronave, _ = avion(mejor["torsion"], mejor["x_cg"], deriva)
    est = asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(
        velocity=V_CRUCERO, alpha=mejor["alfa"])).run_with_stability_derivatives()
    mejor["Cn_beta"] = _num(est["Cnb"])
    return mejor


def derivas_que_estabilizan(peso):
    """(cuerda de la raíz, de la punta, alto) de las derivas: el alto, de 1
    en 1 cm desde el del tren, hasta que el Cn_beta respecto al CG llega a
    CN_BETA_MINIMO."""
    for k in range(30):
        deriva = (*CUERDAS_DERIVA, round(ALTO_DERIVA + 0.01 * k, 3))
        eq = equilibrado(peso, deriva=deriva)
        print(f"derivas de {deriva[2] * 1000:.0f} mm: Cn_beta {eq['Cn_beta']:.4f}", flush=True)
        if eq["Cn_beta"] >= CN_BETA_MINIMO:
            return deriva
    raise SystemExit(f"ni con derivas de {deriva[2]:.2f} m llega a Cn_beta {CN_BETA_MINIMO:.3f}")


def rotores(x_cg, ala, alto_deriva=ALTO_DERIVA):
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
                (Z_FUSELAJE - re) - (Z_VIGA - alto_deriva), 3),
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
    cosas = [{"id": "impreso", "nombre": "lo impreso (alas de LW-PLA, el resto de PETG)",
              "masa_kg": m["impreso"],
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
               "telemetría y receptor", "masa_kg": AVIONICA_KG, "en": [X_ELECTRONICA, 0, Z_ELECTRONICA],
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
    cosas.append({"id": "bateria", "nombre": BATERIA["nombre"],
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
    deriva = None
    aeronave, ala = avion(-4.0)
    area = sum(w.area(type="wetted") for w in aeronave.wings) + aeronave.fuselages[0].area_wetted()
    impreso = area * 1e4 * PIEL_MM / 10 * LWPLA_G_CM3 * NERVIOS / 1000
    medido = impreso_medido()
    if medido:
        impreso = medido["masa_kg"]
    bateria = BATERIA["kg"]
    sustentacion = 4 * (MOTOR_VTOL["kg"] + VARIADOR_KG + HELICE_VTOL_KG)
    empuje = EMPUJE_KG
    masa = impreso + AVIONICA_KG + SERVOS_KG + CARBONO_KG + CARGA_KG + bateria + sustentacion + empuje
    empuje_sobre_peso = 4 * MOTOR_VTOL["empuje_max_kg"] / masa
    if empuje_sobre_peso < EMPUJE_SOBRE_PESO_MINIMO:
        raise SystemExit(f"los cuatro rotores dan {4 * MOTOR_VTOL['empuje_max_kg']:g} kg y el "
                         f"avión pesa {masa:.2f}: {empuje_sobre_peso:.2f} veces su peso, menos "
                         f"de {EMPUJE_SOBRE_PESO_MINIMO}")
    peso = masa * G
    deriva = derivas_que_estabilizan(peso)
    eq = equilibrado(peso, deriva=deriva)
    aeronave, ala = avion(eq["torsion"], eq["x_cg"], deriva)
    a = aero(aeronave, eq["alfa"])
    resistencia = a["D"] + 0.5 * RHO * V_CRUCERO ** 2 * CDA_ROTORES_M2
    p_crucero = resistencia * V_CRUCERO / RENDIMIENTO_CRUCERO
    disco = 4 * math.pi * (HELICE_VTOL_PULG * 0.0254 / 2) ** 2
    p_vtol = peso ** 1.5 / math.sqrt(2 * RHO * disco) / FIGURA_MERITO / RENDIMIENTO_MOTOR_VTOL
    wh = BATERIA["serie"] * 3.7 * BATERIA["mAh"] / 1000
    horas = (wh * (1 - RESERVA) - p_vtol * MIN_VTOL / 60) / p_crucero
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
            ("impreso, pesado en sus STL" if medido else "impreso (LW-PLA, estimado)"):
                round(impreso, 3),
            "carbono: largueros y vigas": CARBONO_KG,
            "4 motores de sustentación, variadores y hélices": round(sustentacion, 3),
            "motor de empuje, variador y hélice plegable": round(empuje, 3),
            "controladora, ordenador de a bordo, GPS, telemetría y cables": AVIONICA_KG,
            "cuatro servos de los elevones": SERVOS_KG,
            "carga útil": CARGA_KG,
            BATERIA["nombre"]: round(bateria, 3),
            "total": round(masa, 3),
        },
        "_deriva_m": deriva,
        "_masas": {"impreso": impreso, "sustentacion": sustentacion, "empuje": empuje,
                   "bateria": bateria, "total": masa},
        "_centroide_impreso_m": ([medido["centro_mm"][0] / 1000, medido["centro_mm"][2] / 1000]
                                 if medido else centroide_impreso(aeronave)),
        "impreso_pesado_en": medido["proyecto"] if medido else None,
        "_x_np_m": eq["x_np"], "_mac_m": ala.mean_aerodynamic_chord(),
        "bateria": {"serie": BATERIA["serie"], "mAh": BATERIA["mAh"], "Wh": round(wh, 1)},
        "carga_alar_kg_m2": round(masa / s, 2),
        "crucero": {"velocidad_m_s": V_CRUCERO, "alfa_grados": round(eq["alfa"], 2),
                    "CL": round(a["CL"], 3), "L_D": round(a["L"] / resistencia, 2),
                    "resistencia_N": round(resistencia, 2), "potencia_W": round(p_crucero, 1)},
        "vtol": {"potencia_W": round(p_vtol), "minutos": MIN_VTOL,
                 "empuje_max_por_motor_kg": MOTOR_VTOL["empuje_max_kg"],
                 "empuje_sobre_peso": round(empuje_sobre_peso, 2)},
        "compras": [{"que": q, "cantidad": n, "url": u} for q, n, u in COMPRAS],
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
        "rotores": rotores(eq["x_cg"], ala, deriva[2]),
        "estaciones": [list(e) for e in estaciones(eq["torsion"])],
        "supuestos": {"rendimiento_crucero": RENDIMIENTO_CRUCERO, "figura_de_merito": FIGURA_MERITO,
                      "empuje_sobre_peso_minimo": EMPUJE_SOBRE_PESO_MINIMO,
                      "variador_kg": VARIADOR_KG, "empuje_kg": EMPUJE_KG,
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
        "deriva": {"x": round(X_DERIVA * 1000),
                   "cuerda": [round(c * 1000) for c in r["_deriva_m"][:2]],
                   "alto": round(r["_deriva_m"][2] * 1000)},
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
    # Lo que mide cada tubo de carbono tal como lo corta el kit: se venden de
    # 1000 mm (`avion.TUBO_COMPRADO`).
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp",
                                    "mech-toolkit"))
    from mech_toolkit import avion as kit_avion
    d = r["diseno"]
    r["tubos_mm"] = {f"larguero Ø{di}": round(math.dist(*kit_avion.extremos_larguero(d, f, di)), 1)
                     for f, di in d["largueros"]}
    ro = d["rotores"]
    r["tubos_mm"][f"viga Ø{ro['viga']}"] = ro["x"][1] - ro["x"][0] + 2 * kit_avion.MEDIO_LARGO_GONDOLA
    # La varilla maciza de Ø2: los dos elevones exteriores y, desde el
    # 2026-11-16, las guías del cuerpo central.
    r["tubos_mm"]["varilla Ø2"] = round(kit_avion.largo_varilla(d), 1)
    for k in [k for k in r if k.startswith("_")] + ["dentro"]:
        del r[k]
    r["perfiles"] = perfiles()
    texto = json.dumps(r, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(texto)
    print(json.dumps({k: v for k, v in r.items() if k not in ("perfiles", "estaciones")},
                     ensure_ascii=False, indent=1))
