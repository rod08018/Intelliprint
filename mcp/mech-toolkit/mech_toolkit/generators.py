"""Catálogo de generadores de geometría.

Las plantillas las escribe un humano y son lo único que se ejecuta dentro
de FreeCAD. El LLM solo elige cuáles llamar y con qué parámetros — esa es
la propiedad que hace segura la ejecución (ADR-002).

Convenciones de las plantillas:

- `doc` existe (lo crea el preámbulo de `compose_build_script`).
- La pieza se construye **centrada en el origen** en X e Y, y apoyada en
  Z=0, que es como se imprime.
- Cada paso deja el sólido resultante como **último objeto del documento**,
  que es lo que el epílogo exporta.
- Marcadores `$param` (string.Template), no `{}`: el cuerpo es Python real.

TODO (F2.1 (servicio)): cuando `mech-toolkit` sea un servicio MCP, `GeneratorSpec` y
`GeneratorCatalog` deberían vivir aquí y el orquestador recibirlos por la
red. Hoy se importan del orquestador para no duplicar el contrato.
"""

from orchestrator.schemas.recipe import GeneratorCatalog, GeneratorSpec

_PLACA = """\
_placa = doc.addObject("Part::Box", "placa")
_placa.Length = $length_mm
_placa.Width = $width_mm
_placa.Height = $thickness_mm
_placa.Placement.Base = FreeCAD.Vector(-$length_mm / 2.0, -$width_mm / 2.0, 0)
"""

# Los cilindros de corte se extienden muy por encima y por debajo de la
# pieza: así el corte es pasante sin tener que conocer el espesor, y sin
# dejar caras coincidentes, que es de donde salen los sólidos con errores.
_TALADRO_CENTRAL = """\
_broca = doc.addObject("Part::Cylinder", "broca_central")
_broca.Radius = $diameter_mm / 2.0
_broca.Height = 1000.0
_broca.Placement.Base = FreeCAD.Vector(0, 0, -500.0)
_previo = [o for o in doc.Objects if hasattr(o, "Shape") and o is not _broca][-1]
_corte = doc.addObject("Part::Cut", "con_taladro")
_corte.Base = _previo
_corte.Tool = _broca
doc.recompute()
"""

_PATRON_CUADRADO = """\
_r = $hole_diameter_mm / 2.0
_s = $pitch_mm / 2.0
_brocas = []
for _i, (_x, _y) in enumerate([(_s, _s), (-_s, _s), (_s, -_s), (-_s, -_s)]):
    _b = doc.addObject("Part::Cylinder", "broca_%d" % _i)
    _b.Radius = _r
    _b.Height = 1000.0
    _b.Placement.Base = FreeCAD.Vector(_x, _y, -500.0)
    _brocas.append(_b)
_union = doc.addObject("Part::MultiFuse", "brocas")
_union.Shapes = _brocas
doc.recompute()
_previo = [
    o for o in doc.Objects
    if hasattr(o, "Shape") and o is not _union and o not in _brocas
][-1]
_corte = doc.addObject("Part::Cut", "con_patron")
_corte.Base = _previo
_corte.Tool = _union
doc.recompute()
"""

# --- Para mecanismos ---------------------------------------------------------

# Barra en forma de estadio con un agujero en cada centro: sirve igual para
# una manivela que para una biela. El ORIGEN está en el primer agujero, que
# es el pivote, para que la pieza gire alrededor de su propio origen al
# ensamblarla.
_BARRA = """\
_d, _w, _t = $center_distance_mm, $width_mm, $thickness_mm
_rh = $hole_diameter_mm / 2.0
_cuerpo = Part.makeBox(_d, _w, _t, FreeCAD.Vector(0, -_w / 2.0, 0))
for _cx in (0.0, _d):
    _cuerpo = _cuerpo.fuse(Part.makeCylinder(_w / 2.0, _t, FreeCAD.Vector(_cx, 0, 0)))
for _cx in (0.0, _d):
    _cuerpo = _cuerpo.cut(Part.makeCylinder(_rh, _t + 2, FreeCAD.Vector(_cx, 0, -1)))
_barra = doc.addObject("Part::Feature", "barra")
_barra.Shape = _cuerpo.removeSplitter()
doc.recompute()
"""

# Caja centrada en (x, y) en planta y apoyada en z. Si ya hay cuerpo, se
# suma a él: así se construye una bancada con su placa y sus raíles.
_CAJA = """\
_previos = [o for o in doc.Objects if hasattr(o, "Shape") and o.Shape.Volume > 0]
_caja = doc.addObject("Part::Box", "caja")
_caja.Length, _caja.Width, _caja.Height = $length_mm, $width_mm, $height_mm
_caja.Placement.Base = FreeCAD.Vector(
    ($x_mm) - ($length_mm) / 2.0, ($y_mm) - ($width_mm) / 2.0, $z_mm)
doc.recompute()
if _previos:
    _suma = doc.addObject("Part::MultiFuse", "suma")
    _suma.Shapes = [_previos[-1], _caja]
    doc.recompute()
"""

# Agujero pasante vertical en (x, y). La broca sobresale mucho por arriba y
# por abajo para cortar de lado a lado sin caras coincidentes.
_AGUJERO = """\
_broca_h = doc.addObject("Part::Cylinder", "broca_agujero")
_broca_h.Radius = ($diameter_mm) / 2.0
_broca_h.Height = 1000.0
_broca_h.Placement.Base = FreeCAD.Vector($x_mm, $y_mm, -500.0)
_previo = [o for o in doc.Objects if hasattr(o, "Shape") and o is not _broca_h][-1]
_corte = doc.addObject("Part::Cut", "con_agujero")
_corte.Base = _previo
_corte.Tool = _broca_h
doc.recompute()
"""


# --- Cuerpos que se suman a lo anterior -------------------------------------
# `_sumar` fusiona `_forma` con el último cuerpo, si lo hay. Así una pieza se
# compone de varios pasos (placa + soportes + cilindros) sin booleanas a mano.
_SUMAR = """
_previos = [o for o in doc.Objects if hasattr(o, "Shape") and o.Shape.Volume > 0]
if _previos:
    _forma = _previos[-1].Shape.fuse(_forma).removeSplitter()
_obj = doc.addObject("Part::Feature", "cuerpo")
_obj.Shape = _forma
doc.recompute()
"""

_RESTAR = """
_previo = [o for o in doc.Objects if hasattr(o, "Shape") and o.Shape.Volume > 0][-1]
_obj = doc.addObject("Part::Feature", "corte")
_obj.Shape = _previo.Shape.cut(_herramienta).removeSplitter()
doc.recompute()
"""

_EJES = """
_dir = {"x": FreeCAD.Vector(1, 0, 0), "y": FreeCAD.Vector(0, 1, 0), "z": FreeCAD.Vector(0, 0, 1)}[$axis]
"""

# Cilindro con la base en (x, y, z) que crece hacia +eje: ejes, nudillos de
# bisagra, pasadores, discos de leva, casquillos.
_CILINDRO = _EJES + """
_forma = Part.makeCylinder(($diameter_mm) / 2.0, $length_mm,
                           FreeCAD.Vector($x_mm, $y_mm, $z_mm), _dir)
""" + _SUMAR

# Agujero pasante a lo largo de un eje, que pasa por (x, y, z).
_AGUJERO_EJE = _EJES + """
_p = FreeCAD.Vector($x_mm, $y_mm, $z_mm) - _dir * 500.0
_herramienta = Part.makeCylinder(($diameter_mm) / 2.0, 1000.0, _p, _dir)
""" + _RESTAR

# Vaciado con una caja (ranuras, alojamientos). Mismo convenio que generate_box.
_VACIADO = """
_herramienta = Part.makeBox($length_mm, $width_mm, $height_mm, FreeCAD.Vector(
    ($x_mm) - ($length_mm) / 2.0, ($y_mm) - ($width_mm) / 2.0, $z_mm))
""" + _RESTAR

# Prisma de un polígono en planta [[x, y], ...], de z a z + espesor.
_PRISMA = """
_pts = [FreeCAD.Vector(_x, _y, $z_mm) for _x, _y in $points_mm]
_forma = Part.Face(Part.makePolygon(_pts + [_pts[0]])).extrude(FreeCAD.Vector(0, 0, $thickness_mm))
""" + _SUMAR

# Rueda de trinquete con dientes de sierra, centrada en el origen, de z = 0 a
# z = espesor. Cada diente sube en línea recta del fondo (ángulo k·p) a la
# punta (ángulo (k+1)·p) y cae en radial: la cara radial es la que empuja el
# trinquete. Gira en sentido antihorario para avanzar. El mismo perfil está en
# sim.ratchet; si cambia aquí, tiene que cambiar allí.
_RUEDA_TRINQUETE = """
import math as _m
_n = int($teeth)
_p = 2 * _m.pi / _n
_pts = []
for _k in range(_n):
    for _r, _a in ((($root_diameter_mm) / 2.0, _k * _p), (($tip_diameter_mm) / 2.0, (_k + 1) * _p)):
        _pts.append(FreeCAD.Vector(_r * _m.cos(_a), _r * _m.sin(_a), 0))
_forma = Part.Face(Part.makePolygon(_pts + [_pts[0]])).extrude(FreeCAD.Vector(0, 0, $thickness_mm))
""" + _SUMAR

# Resorte helicoidal a lo largo de +z, de z = 0 a z = largo. Representación
# simplificada: se estira o se comprime escalando en z al ensamblar.
_RESORTE = """
_vueltas = (($length_mm) - ($wire_diameter_mm)) / ($pitch_mm)
if _vueltas < 1:
    raise RuntimeError(
        "INTELLIPRINT_FALLO: el resorte sale de %.2f vueltas (largo %s, alambre %s, paso %s): "
        "menos de una vuelta no es un resorte. Alarga el resorte o baja el paso."
        % (_vueltas, $length_mm, $wire_diameter_mm, $pitch_mm))
# La hélice va de w/2 a L - w/2: con el alambre, el resorte ocupa de 0 a L y
# sus puntas no se meten en los asientos.
_helice = Part.makeHelix($pitch_mm, ($length_mm) - ($wire_diameter_mm), ($coil_diameter_mm) / 2.0)
_helice.translate(FreeCAD.Vector(0, 0, ($wire_diameter_mm) / 2.0))
_ini = _helice.Edges[0].valueAt(_helice.Edges[0].FirstParameter)
_tan = _helice.Edges[0].tangentAt(_helice.Edges[0].FirstParameter)
_perfil = Part.Wire(Part.makeCircle(($wire_diameter_mm) / 2.0, _ini, _tan))
_forma = Part.Wire(_helice.Edges).makePipeShell([_perfil], True, True)
""" + _SUMAR


CATALOGO = GeneratorCatalog(
    [
        GeneratorSpec(
            name="generate_plate",
            description='Placa centrada en X e Y sobre el origen, de z = 0 a z = espesor. Úsala solo si la pieza va centrada en el origen; para colocarla en otro sitio, generate_box.',
            required_params={"length_mm", "width_mm", "thickness_mm"},
            template=_PLACA,
        ),
        GeneratorSpec(
            name="generate_center_bore",
            description='Agujero vertical pasante en el origen (x = 0, y = 0).',
            required_params={"diameter_mm"},
            template=_TALADRO_CENTRAL,
        ),
        GeneratorSpec(
            name="generate_square_bolt_pattern",
            description='Cuatro agujeros verticales pasantes en las esquinas de un cuadrado de lado `pitch_mm` centrado en el origen.',
            required_params={"hole_diameter_mm", "pitch_mm"},
            template=_PATRON_CUADRADO,
        ),
        GeneratorSpec(
            name="generate_link",
            description='Barra de estadio: primer agujero en el origen, segundo en (center_distance, 0), de z = 0 a z = espesor. Para manivelas, bielas, brazos. Caja: x de −ancho/2 a distancia+ancho/2, y ±ancho/2, z de 0 a espesor.',
            required_params={"center_distance_mm", "width_mm", "thickness_mm",
                             "hole_diameter_mm"},
            template=_BARRA,
        ),
        GeneratorSpec(
            name="generate_box",
            description='Caja centrada en (x, y) en planta, de z a z + height. Se suma a lo anterior.',
            required_params={"length_mm", "width_mm", "height_mm", "x_mm", "y_mm", "z_mm"},
            template=_CAJA,
        ),
        GeneratorSpec(
            name="generate_hole",
            description='Agujero vertical (eje Z) pasante en (x, y). Corta lo anterior.',
            required_params={"diameter_mm", "x_mm", "y_mm"},
            template=_AGUJERO,
        ),
        GeneratorSpec(
            name="generate_cylinder",
            description='Cilindro con la base en (x, y, z) que crece hacia + del eje elegido. Se suma a lo anterior. Caja: un cuadrado de lado el diámetro alrededor del eje, y la longitud a lo largo de él.',
            required_params={"diameter_mm", "length_mm", "x_mm", "y_mm", "z_mm"},
            choice_params={"axis": {"x", "y", "z"}},
            template=_CILINDRO,
        ),
        GeneratorSpec(
            name="generate_hole_axis",
            description='Agujero pasante a lo largo del eje elegido, que pasa por (x, y, z). Corta lo anterior.',
            required_params={"diameter_mm", "x_mm", "y_mm", "z_mm"},
            choice_params={"axis": {"x", "y", "z"}},
            template=_AGUJERO_EJE,
        ),
        GeneratorSpec(
            name="generate_cut_box",
            description='Vaciado con una caja centrada en (x, y) en planta, de z a z + height (ranuras, alojamientos). Corta lo anterior.',
            required_params={"length_mm", "width_mm", "height_mm", "x_mm", "y_mm", "z_mm"},
            template=_VACIADO,
        ),
        GeneratorSpec(
            name="generate_prism",
            description='Polígono [[x, y], ...] en planta extruido de z a z + espesor. Se suma a lo anterior. Caja: la del polígono, y de z a z+espesor.',
            required_params={"points_mm", "thickness_mm", "z_mm"},
            template=_PRISMA,
        ),
        GeneratorSpec(
            name="generate_ratchet_wheel",
            description='Rueda de trinquete centrada en el origen, de z = 0 a espesor. Cada diente sube en línea recta del fondo (ángulo k·360/N) a la punta (ángulo (k+1)·360/N) y cae en radial: avanza girando en sentido antihorario. Se suma a lo anterior; el agujero del eje va aparte. Caja: NO es ±tip/2 salvo que una punta caiga sobre el eje; es el máximo de r·cos y r·sin sobre los vértices del perfil.',
            required_params={"teeth", "tip_diameter_mm", "root_diameter_mm", "thickness_mm"},
            template=_RUEDA_TRINQUETE,
        ),
        GeneratorSpec(
            name="generate_spring",
            description='Resorte helicoidal a lo largo de z, de z = 0 a z = largo, centrado en el eje Z. Caja: en planta ±(coil+wire)/2 (el alambre sobresale del diámetro de espira), en z de 0 a largo. Necesita al menos una vuelta: (largo − alambre)/paso ≥ 1.',
            required_params={"coil_diameter_mm", "wire_diameter_mm", "pitch_mm", "length_mm"},
            template=_RESORTE,
        ),
    ]
)
