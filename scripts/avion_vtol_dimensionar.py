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

Y el 2026-11-18, al ver 7 kg («me parece irreal el peso del avion no creo
que vuele», con el TerraHawk y el Flightory de menos de 3 kg), se rehízo con
lo que él compra, sección a sección, en la lista de compras que aprobó: LiPo
6S de 10 000 mAh, cuatro 4214 de 660 KV con hélice de 15″ («Usa 600kv y
helices mas grandes»; el 660 KV es el único de esa franja para 6S que llega
a Guatemala), el 3115 de 900 KV de empuje con 9″, 300 g de carga y casi una
hora de vuelo. Vuela a 1 500 m (la Ciudad de Guatemala): el aire pesa un 13 %
menos que al nivel del mar, y se dimensiona con ese aire. Imprime en una
CORE One L+ (300 × 300 × 330): menos piezas, más grandes.

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

G = 9.81
# Vuela en la Ciudad de Guatemala (2026-11-18): a 1 500 m el aire pesa
# 1,058 kg/m³ (atmósfera estándar), no 1,225. Con el del nivel del mar el
# dimensionado daba un 13 % más de empuje y de sustentación que los que hay.
ATMOSFERA = asb.Atmosphere(altitude=1500)
RHO = float(ATMOSFERA.density())
V_CRUCERO = 19.0     # 68 km/h: el de la lista de compras v4
CARGA_KG = float(sys.argv[2]) if len(sys.argv) > 2 else 0.3

# --- Lo que se compra (la lista de compras v4, aprobada el 2026-11-18) ----------
# Él: «dame los links de todo y debe estar en amazon para yo poder traerlo a
# guatemala y trata de usar los pesos que dice amazon», «porque no una
# bateria de 10Ah 6s?», y de los motores de subir, «Usa 600kv y helices mas
# grandes» y «Con el de 660KV». Las cifras son las de cada anuncio, no
# medidas; donde el anuncio decía un peso imposible («50 g» para un motor),
# se dice al lado de dónde sale el otro.
BATERIA = {"nombre": "batería LiPo 6S 10 000 mAh", "serie": 6, "mAh": 10000, "kg": 1.248,
           "caja": (161, 66, 48)}         # 161 × 48 × 66 en su anuncio, tumbada
# El 4214 de 660 KV (copia del iFlight XING 4214): 213 g según las tiendas del
# XING. A fondo gira la hélice de 15″ a unas 12 000 rpm, más de lo que
# aguantan ella y los variadores de 40 A: PX4 lo limita al 65 %, donde gira
# como el MAD 5005 de 440 KV a fondo y empuja lo mismo, 3,0 kg al nivel del
# mar (tabla de banco de MAD con la misma hélice).
MOTOR_VTOL = {"empuje_max_kg": 3.0, "kg": 0.213, "limite": 0.65}
VARIADOR_KG = 0.022                       # MAD AMPX 40A Pro, su anuncio
HELICE_VTOL_KG = 0.020                    # 15 × 5,5 de carbono, su anuncio
# DYS X3115 de 900 KV (112 g), Hobbywing Skywalker 60A V2 (68 g) y la Gemfan
# 9045 tripala (unos 10 g: Amazon no la pesa).
EMPUJE_KG = 0.19
EMPUJE_SOBRE_PESO_MINIMO = 1.5   # criterio del asistente: margen para una ráfaga
# Lo que hay que comprar, con su anuncio. La controladora no: él ya tiene una
# Pixhawk 1 (un clon, «px4pilot»).
COMPRAS = [
    ("LiPo 6S 10 000 mAh 100C, pedirla con XT90", 1, "https://www.amazon.com/dp/B0HBQBDRJM"),
    ("Motor 4214 660KV X-class, paquete de 4 (sustentación; limitado al 65 % en PX4)", 1,
     "https://www.amazon.com/dp/B0HQC3FQK1"),
    ("Hélices de carbono 15 × 5,5″, 2 CW + 2 CCW (sustentación)", 2,
     "https://www.amazon.com/dp/B0B3V5F7C2"),
    ("Variador MAD AMPX 40A Pro 2–6S (sustentación)", 4, "https://www.amazon.com/dp/B082W7ZHZ5"),
    ("Motor DYS X3115 900KV, paquete de 4 (empuje)", 1, "https://www.amazon.com/dp/B0G3FBRBP4"),
    ("Hélices Gemfan 9045 tripala, 2 CW + 2 CCW (empuje)", 1,
     "https://www.amazon.com/dp/B0BM91PDTQ"),
    ("Variador Hobbywing Skywalker 60A V2 (empuje; su BEC alimenta los servos)", 1,
     "https://www.amazon.com/dp/B0DQD7W8V8"),
    ("Módulo de potencia para Pixhawk, 30 V / 90 A", 1, "https://www.amazon.com/dp/B0BCJM3R5P"),
    ("Conectores XT90-S antichispa, 5 pares", 1, "https://www.amazon.com/dp/B0HDRYTGP5"),
    ("Cable de silicona 10 AWG, 10 ft", 1, "https://www.amazon.com/dp/B0D968WN4W"),
    ("Cable de silicona 12 AWG, 10 ft", 1, "https://www.amazon.com/dp/B0D968VXCT"),
    ("Extensiones de servo de 30 cm, 10 piezas", 1, "https://www.amazon.com/dp/B01LA9YDEI"),
    ("GPS M8N con brújula (JeeFly)", 1, "https://www.amazon.com/dp/B0FLV6RTY1"),
    ("Sensor de velocidad (pitot digital)", 1, "https://www.amazon.com/dp/B01J7NCML0"),
    ("Servo MG90D digital, engranes de metal, 4 piezas (elevones)", 1,
     "https://www.amazon.com/dp/B0D5YBL2JX"),
    ("Tubo de carbono 16 × 12 × 1000 mm (vigas de los rotores)", 2,
     "https://www.amazon.com/dp/B09Q7Y1ZWJ"),
    ("Tubo de carbono 10 × 8 × 1000 mm (larguero delantero, uno por ala)", 2,
     "https://www.amazon.com/dp/B09QLFGBN3"),
    ("Tubos de carbono 6 × 4 × 1000 mm, paquete de 6 (larguero trasero)", 1,
     "https://www.amazon.com/dp/B0GWYYKDCS"),
    ("Varilla de carbono maciza redonda de Ø2, de 500 mm (guías del cuerpo central)", 1,
     "https://www.amazon.com/s?k=carbon+fiber+rod+2mm+round+500mm"),
    # F13.13 (compras): lo que faltaba al compararlo con el Stallion de
    # Flightory (2026-11-18). Buscado en Amazon con la entrega a Guatemala
    # el 2026-11-19; ninguno dice su peso, por eso van en HERRAJES_KG.
    ("Tubos de carbono 12 × 10 × 500 mm, paquete de 4 (ARRIS; los manguitos de las alas "
     "desmontables, uno por tubo)", 1, "https://www.amazon.com/dp/B08ZSTPHVS"),
    ("Bisagras de papel para CA de 20 × 15 mm, 20 piezas (tres por elevón)", 1,
     "https://www.amazon.com/dp/B0DY7ZQG1D"),
    ("Varillas Z de 1,5 × 450 mm con cuernos de nailon de 21 × 10 y topes, 10 juegos "
     "(un cuerno y una varilla por elevón)", 1, "https://www.amazon.com/dp/B0BHYRRBHP"),
    ("Tornillos M2 autorroscantes, surtido (los cuernos de los elevones)", 1,
     "https://www.amazon.com/dp/B0CY986CCR"),
    ("Tornillos M3 de cabeza Allen de 6 a 30 mm con tuercas, inox 304, 720 piezas "
     "(las alas al cuerpo y los pilones)", 1, "https://www.amazon.com/dp/B0FG2BRXL3"),
    ("Conectores MPX de 6 pines, 20 pares (un par por ala: sus dos servos al desmontarla)", 1,
     "https://www.amazon.com/dp/B07C6NV1GK"),
    ("Pegamento CA fino, 20 g (las bisagras y las juntas de LW-PLA)", 1,
     "https://www.amazon.com/dp/B0DSCCB7G5"),
    ("Jeringa de epoxi J-B Weld de 25 ml (los manguitos al cuerpo central)", 1,
     "https://www.amazon.com/dp/B072V321DX"),
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
    """{masa_kg, centro_mm, proyecto} de lo pesado, o None si no se ha pesado.
    Con IMPRESO_ESTIMADO=1, None: la primera vuelta de un avión nuevo, cuyas
    piezas aún no existen (lo pesado es del de antes)."""
    if os.environ.get("IMPRESO_ESTIMADO") or not os.path.exists(IMPRESO_MEDIDO):
        return None
    with open(IMPRESO_MEDIDO, encoding="utf-8") as f:
        return json.load(f)
# Cuatro hélices de 15″ paradas en línea, sus motores y las vigas de casi un
# metro: algo más que con las de 13″ (0,006).
CDA_ROTORES_M2 = 0.007
# La Pixhawk 1 que ya tiene (38 g, los de la original), GPS, pitot, módulo de
# potencia, receptor y unos 160 g de cables y conectores: la lista de compras.
AVIONICA_KG = 0.291
SERVOS_KG = 4 * 0.0135           # MG90D, su anuncio
# Ø10 (31 g el metro, su anuncio) y Ø6 (calculado); las dos vigas de 16 × 12,
# 136 g el metro de tubo (calculado: Amazon no lo da), contadas enteras.
LARGUEROS_KG, VIGAS_KG = (0.062, 0.036), 0.272
# Las alas desmontables (2026-11-18): el tubo de 12 × 10 de los manguitos,
# 55 g el metro (calculado con 1,6 g/cm³), contado entero. Y los herrajes:
# 12 bisagras de chapa, 4 cuernos, 4 varillas de mando y la tornillería, unos
# 30 g (estimación del asistente: los anuncios no los pesan todos).
MANGUITOS_KG, HERRAJES_KG = 0.055, 0.030
CARBONO_KG = sum(LARGUEROS_KG) + VIGAS_KG + MANGUITOS_KG + HERRAJES_KG

# --- Lo de dentro (mm): cajas que ocupan sitio -----------------------------------
# La LiPo de 161 × 48 × 66 de su anuncio, tumbada (66 de ancho y 48 de alto:
# así el fuselaje es más bajo), con 2 mm de espuma por cada lado de los de
# abajo y de los lados.
CAJA_BATERIA = (BATERIA["caja"][0] + 3, BATERIA["caja"][1] + 4, BATERIA["caja"][2] + 2)
CAJA_CARGA = (120, 60, 40)       # 300 g: dos cámaras pequeñas y un lidar ligero
# La controladora (la Pixhawk 1 mide 82 × 50 × 16) con el receptor y el
# módulo de potencia; sigue cabiendo una Raspberry Pi detrás, que él pidió
# el 2026-11-16 y la lista de compras v4 no lleva.
CAJA_ELECTRONICA = (110, 55, 35)
X_ELECTRONICA = 10
# Entra por la panza y se empuja hacia delante: tiene que pasar bajo el
# larguero de Ø10 (z = -4,5 en el centro, menos 5, menos 1 de aire: -10,5).
# En -28 su techo quedaba en -8 y no pasaba
# (`test_la_electronica_entra_por_la_panza_y_se_desliza_hasta_su_sitio`).
Z_ELECTRONICA = -33
# El MG90D, tumbado: 22,8 × 12,2 × 28,5 y 32,5 con las orejas (las medidas
# del MG90 de siempre), con las orejas a lo largo del ala. Era el KST X10
# Mini, de 10 mm de grueso.
CAJA_SERVO = (30, 34, 13)
# Dos elevones por lado, cada uno con su servo (él, el 2026-11-16: «debe
# tener alerones, implica que debe tener 4 servos»). Con la cama grande cada
# elevón es un tramo de ala entero, de una pieza: el interior, el 2, y el
# exterior, el 3. Si un servo falla, el avión sigue gobernable.
ELEVONES = ((2,), (3,))
SERVO_Y = (520, 735)             # cada servo, dentro de su tramo y en su elevón
TRAMO_MAX_MM = 220.0             # de pie en la cama de 300 × 300 × 330
CELDA_RAIZ_MM = 270.0
CAMA_MM = (300, 300, 330)        # la CORE One L+
# El margen estático que se acepta, con carga y sin ella. Un ala volante
# vuela con poco (un 5–10 %); por debajo del 5 % se vuelve nerviosa y
# pasado el punto neutro, inestable (criterio del asistente).
MARGEN_MINIMO, MARGEN_MAXIMO = 0.05, 0.12
SERVO_CUERDA = 0.42              # entre los dos largueros (25 % y 60 %)
# El techo de la batería: 3 mm bajo el larguero de Ø6, que cruza el fuselaje
# a z ≈ -7 (el de Ø10, más adelante, a -4,5).
Z_TECHO_BATERIA = -13
X_EMPUJE_MM = 610

# --- La forma (m), x hacia atrás, y a la derecha, z arriba ----------------------
ENVERGADURA = 1.72           # sin las puntas levantadas
FLECHA_GRADOS = 25.0
# La viga, tan cerca del fuselaje como deja la hélice de empuje: entre su
# disco y el de un rotor trasero, el 15 % del diámetro de sustentación
# (0,365 − 0,1905 − 0,1143 = 0,060 ≥ 0,057).
Y_VIGA = 0.365
HELICE_VTOL_PULG = 15        # la de la lista de compras, para el 4214 de 660 KV
HELICE_EMPUJE_PULG = 9       # la Gemfan 9045
Z_FUSELAJE = -0.02           # el eje del fuselaje y de la hélice de empuje
# La viga va donde la pone el kit, justo bajo el ala. Las derivas y las patas
# son el tren de aterrizaje: con 130 mm la hélice de empuje bajaba 5 mm más
# que ellas y tocaba el suelo al posarse (cuentas del 2026-11-16); se alargan
# hasta dejarle 30 mm. La deriva va colgada de la góndola de atrás y centrada
# en su motor (`avion._gondola_con_aleta`): su x sale de los rotores.
Z_VIGA = -0.012
PATA_CUERDA_MM = (90, 60)
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
# Más cortas que las de 150 y 90: con la deriva centrada en el motor de atrás,
# la viga va de la punta de la pata a la de la deriva y no pasa del metro del
# tubo que se compra.
CUERDAS_DERIVA = (0.13, 0.08)
# Donde empieza la deriva: la primera vuelta la supone; `dimensionar` la pone
# centrada en el motor de atrás en cuanto sabe dónde va.
X_DERIVA = 0.66
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
#
# El 2026-11-18, con la LiPo de 10 Ah (164 × 70 × 50 con su espuma) y la carga
# de 300 g (120 × 60 × 40), el fuselaje es más corto y más estrecho: de 0,94 m
# a 0,76 y de 160 mm de ancho a 130.
FUSELAJE = ((-0.15, 0.02, 0.02, -0.02), (-0.08, 0.09, 0.08, -0.02), (0.02, 0.12, 0.11, -0.03),
            (0.17, 0.13, 0.16, -0.05), (0.22, 0.13, 0.17, -0.055), (0.38, 0.13, 0.17, -0.055),
            (0.53, 0.08, 0.07, -0.02),
            (0.61, 0.04, 0.04, -0.02))


def estaciones(torsion_punta):
    """(y, x del borde de ataque, z, cuerda, torsión, perfil).

    El 2026-11-18: 1,72 m sin las puntas (eran 2,10) y cuerdas mayores, para
    unos 0,5 m² de ala: con 4,5 kg y el aire de 1 500 m entra en pérdida a
    unos 13 m/s (con CL máx. 1,0). Más corta, con menos tramos."""
    y_punta = ENVERGADURA / 2
    x_punta = 0.17 + (y_punta - 0.22) * math.tan(math.radians(FLECHA_GRADOS))
    # La última sube 40°: la punta levantada del TerraHawk. Una aleta vertical
    # no se imprime de pie sobre la cara de la raíz del tramo; esta sí.
    sube = 0.085
    return [(0.00, 0.00, 0.000, 0.56, 2.0, "mh78"),
            (0.17, 0.15, 0.000, 0.33, 1.0, "mh60"),
            (0.22, 0.17, 0.005, 0.30, 0.0, "mh60"),
            (y_punta, x_punta, 0.045, 0.16, torsion_punta, "mh60"),
            (y_punta + sube, x_punta + sube * math.tan(math.radians(FLECHA_GRADOS)) + 0.02,
             0.045 + sube * math.tan(math.radians(40)), 0.11, torsion_punta, "mh60")]


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
    r = asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(atmosphere=ATMOSFERA,
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
        est = asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(atmosphere=ATMOSFERA,
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
    est = asb.AeroBuildup(airplane=aeronave, op_point=asb.OperatingPoint(atmosphere=ATMOSFERA,
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
    pisan entre sí: un 15 % del diámetro de sustentación de hueco entre
    discos, y un 5 % entre un disco y el ala.

    Del ala eran también el 15 %: con hélices de 15″ y la cuerda de esta
    ala, la viga pedía 1 059 mm y el tubo que se compra mide 1 000
    (2026-11-18). Con el 5 % (19 mm) el disco sigue sin pisar el ala."""
    rv = HELICE_VTOL_PULG * 0.0254 / 2
    re = HELICE_EMPUJE_PULG * 0.0254 / 2
    hueco = 0.15 * 2 * rv
    hueco_ala = 0.05 * 2 * rv
    y, x, _, c, _, _ = estaciones(0)[2]
    y1, x1, _, c1, _, _ = estaciones(0)[3]
    t = (Y_VIGA - y) / (y1 - y)
    le, cu = x + (x1 - x) * t, c + (c1 - c) * t
    delante = le - rv - hueco_ala
    detras = le + cu + rv + hueco_ala
    d = max(x_cg - delante, detras - x_cg)      # iguales respecto al centro de gravedad
    x_empuje = X_EMPUJE_MM / 1000               # tras la cola del fuselaje
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
        x, z = ala(ENVERGADURA * 250, f)   # de y = -20 a casi la punta: su mitad
        cosas.append({"id": f"larguero-{nombre}", "nombre": f"largueros {nombre}", "masa_kg": mk,
                      "en": [x, 0, z]})
    # Los manguitos cruzan el fuselaje a la altura del Ø10; los herrajes van
    # casi todos en la bisagra de los elevones, al 75 % de la cuerda.
    x, z = ala(est[2][0], 0.25)
    cosas.append({"id": "manguitos", "nombre": "manguitos Ø12 de las alas desmontables",
                  "masa_kg": MANGUITOS_KG, "en": [x - 40, 0, z]})
    x, z = ala(ENVERGADURA * 330, 0.75)
    cosas.append({"id": "herrajes", "nombre": "bisagras, cuernos, varillas de mando y tornillos",
                  "masa_kg": HERRAJES_KG, "en": [x, 0, z]})
    cosas.append({"id": "vigas", "nombre": "vigas Ø16 de los rotores", "masa_kg": VIGAS_KG,
                  "en": [(xd - PATA_CUERDA_MM[0] / 2 + xt + CUERDAS_DERIVA[0] * 500) / 2, 0,
                         Z_VIGA * 1000]})
    for lado, s in (("d", 1), ("i", -1)):
        for donde, x in (("delante", xd), ("detras", xt)):
            cosas.append({"id": f"motor-{lado}-{donde}",
                          "nombre": "motor de sustentación, variador y hélice",
                          "masa_kg": m["sustentacion"] / 4, "en": [x, s * yv, z_motor]})
    cosas += [{"id": "motor-empuje", "nombre": "motor y hélice de empuje",
               "masa_kg": 0.8 * m["empuje"], "en": [X_EMPUJE_MM + 15, 0, Z_FUSELAJE * 1000]},
              {"id": "variador-empuje", "nombre": "variador del motor de empuje",
               "masa_kg": 0.2 * m["empuje"], "en": [X_EMPUJE_MM - 60, 0, Z_FUSELAJE * 1000]},
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
    # A 1 500 m una hélice empuja lo que su aire pesa: un 13 % menos.
    empuje_sobre_peso = 4 * MOTOR_VTOL["empuje_max_kg"] * RHO / 1.225 / masa
    if empuje_sobre_peso < EMPUJE_SOBRE_PESO_MINIMO:
        raise SystemExit(f"los cuatro rotores dan {4 * MOTOR_VTOL['empuje_max_kg']:g} kg y el "
                         f"avión pesa {masa:.2f}: {empuje_sobre_peso:.2f} veces su peso, menos "
                         f"de {EMPUJE_SOBRE_PESO_MINIMO}")
    peso = masa * G
    # La deriva cuelga de la góndola de atrás, centrada en su motor; el motor
    # va donde lo pone el centro de gravedad, que la deriva mueve un poco.
    global X_DERIVA
    deriva = derivas_que_estabilizan(peso)
    eq = equilibrado(peso, deriva=deriva)
    for _ in range(3):
        _, ala = avion(eq["torsion"], eq["x_cg"], deriva)
        x_deriva = rotores(eq["x_cg"], ala, deriva[2])["x_detras"] - CUERDAS_DERIVA[0] / 2
        if abs(x_deriva - X_DERIVA) < 0.003:
            break
        X_DERIVA = x_deriva
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
            "carbono (largueros, manguitos y vigas) y herrajes": CARBONO_KG,
            "4 motores de sustentación, variadores y hélices": round(sustentacion, 3),
            "motor de empuje, variador y hélice": round(empuje, 3),
            "controladora, GPS, pitot, receptor y cables": AVIONICA_KG,
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
        # Los elevones, en los tramos con el centro de 500 mm en adelante.
        "elevon": [500, 0.75],
        "deriva": {"x": round(X_DERIVA * 1000),
                   "cuerda": [round(c * 1000) for c in r["_deriva_m"][:2]],
                   "alto": round(r["_deriva_m"][2] * 1000)},
        "pata": {"cuerda": list(PATA_CUERDA_MM)},
        # La pata y la deriva van en las góndolas (`avion._gondola_con_aleta`).
        # El motor, el iFlight XING 4214: Ø50 × 33 según las tiendas.
        "rotores": {"y": round(ro["y_viga"] * 1000), "x": [round(ro["x_delante"] * 1000),
                                                         round(ro["x_detras"] * 1000)],
                    "viga": 16, "helice": round(ro["helice_vtol_pulg"] * 25.4),
                    "aletas": True, "motor": [50, 33],
                    "empuje_kg": MOTOR_VTOL["empuje_max_kg"]},
        "empuje": {"x": X_EMPUJE_MM, "helice": round(ro["helice_empuje_pulg"] * 25.4)},
        # Bajo la carga, en el centro de gravedad: el lidar en medio y una
        # cámara a cada lado. Estaban en el morro.
        "ventanas": [[x_cg - 42, 30, 26], [x_cg, 50, 44], [x_cg + 42, 30, 26]],
        # Las quillas bajo la bandeja, a los lados de la carga de 60 de ancho
        # y dentro de la bandeja (71): a 42, como con la LiPo de 86, quedaban
        # fuera de ella.
        "quilla_y": 33,
        # Celdas de 210 y no de 200: el corte que esquiva el borde de ataque
        # (en x = −5) dejaba la segunda de 235, más del 15 % de 200 (el kit no
        # la corta; primera vuelta del 2026-11-18). Con 290 una celda llevaba
        # el borde de ataque y la boca de la panza, y pedía soportes.
        "cama": list(CAMA_MM), "tramo_max": TRAMO_MAX_MM, "celda_raiz": CELDA_RAIZ_MM,
        "celda_fuselaje": 210,
        # Y cortadas a mano: el borde de ataque del centro va a 41° (de x = 0
        # en y = 0 a 150 en y = 170) y la celda que lo llevaba, de pie sobre
        # su corte de delante, pedía soportes en su morro. Detrás de él (en
        # 105) se imprime sobre su cara de atrás; 230 y 420 parten la boca de
        # la panza (de 156 a 324) como en las celdas que ya se imprimían.
        "cortes_fuselaje": [round(FUSELAJE[0][0] * 1000), 105, 230, 420,
                            round(FUSELAJE[-1][0] * 1000)],
        # Cuatro celdas, y no tres, aunque de pie caben en 325 mm: las orillas
        # de la boca de la panza y el borde de salida del centro piden
        # imprimirse en sentidos contrarios (probado el 2026-11-18,
        # `tests/test_avion_menos_piezas.py`). La punta levantada sí va pegada
        # al último tramo: él, ese día, «Sí, bájalas»; dos piezas menos.
        "punta_unida": True,
        # Lo que salió de compararlo con el Stallion de Flightory (2026-11-18):
        # las alas se desmontan (F13.7 (desmontable); él: «Alas desmontables»),
        # las juntas se pegan cara con cara (F13.9 (juntas)), los elevones
        # llevan bisagras, cuerno y frente en V (F13.10 (mandos)), y el pilón
        # se atornilla al larguero (F13.12 (pilón)).
        "desmontable": True, "juntas": True, "mandos": {"bisel": 30.0},
        "pilon_atornillado": True,
        "elevones":[list(e) for e in ELEVONES],
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
    r["tubos_mm"][f"viga Ø{ro['viga']}"] = round(kit_avion.extremos_viga(d)[1] - kit_avion.extremos_viga(d)[0], 1)
    # La varilla maciza de Ø2: los dos elevones exteriores y, desde el
    # 2026-11-16, las guías del cuerpo central.
    r["tubos_mm"]["varilla Ø2"] = round(kit_avion.largo_varilla(d), 1)
    if d.get("desmontable"):
        r["tubos_mm"]["manguito Ø12"] = round(math.dist(*kit_avion.extremos_manguito(d)), 1)
        r["tubos_mm"]["pasador Ø6"] = round(math.dist(*kit_avion.extremos_pasador(d)), 1)
    # Lo que dejan girar las piezas a cada elevón (F13.10 (mandos)): lo usa
    # el simulador como límite de sus articulaciones.
    d["mandos"]["recorrido"] = round(min(
        kit_avion.recorrido_elevon(d, y) for y0, y1, i in kit_avion._tramos_ala(d)
        if kit_avion._con_elevon(d, y0, y1, i) for y in (y0, y1)), 1)
    # Lo que trabajan los tubos de carbono (F13.11 (esfuerzos)).
    e = kit_avion.esfuerzos(d)
    r["esfuerzos"] = {"n": e["n"], "masa_kg": round(e["masa_kg"], 3),
                      "flecha_punta_mm_1g": round(e["flecha_punta_mm_1g"], 1),
                      "tubos": {k: {"mpa": round(v["mpa"], 1), "n_m": round(v["n_m"], 2),
                                    "donde": v["donde"]} for k, v in e["tubos"].items()}}
    for k in [k for k in r if k.startswith("_")] + ["dentro"]:
        del r[k]
    r["perfiles"] = perfiles()
    texto = json.dumps(r, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(texto)
    print(json.dumps({k: v for k, v in r.items() if k not in ("perfiles", "estaciones")},
                     ensure_ascii=False, indent=1))
