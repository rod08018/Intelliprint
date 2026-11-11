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

# --- Cuerpos colocados donde se pide ------------------------------------------

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
    ]
)
