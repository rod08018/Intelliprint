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

TODO (F2.1): cuando `mech-toolkit` sea un servicio MCP, `GeneratorSpec` y
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

CATALOGO = GeneratorCatalog(
    [
        GeneratorSpec(
            name="generate_plate",
            required_params={"length_mm", "width_mm", "thickness_mm"},
            template=_PLACA,
        ),
        GeneratorSpec(
            name="generate_center_bore",
            required_params={"diameter_mm"},
            template=_TALADRO_CENTRAL,
        ),
        GeneratorSpec(
            name="generate_square_bolt_pattern",
            required_params={"hole_diameter_mm", "pitch_mm"},
            template=_PATRON_CUADRADO,
        ),
    ]
)
