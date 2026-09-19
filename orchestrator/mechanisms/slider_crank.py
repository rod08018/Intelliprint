"""Disposición de una biela-manivela-corredera en línea.

Qué piezas hay, sus medidas y dónde está cada una en cada ángulo. Lo
decide el CÓDIGO a partir de la carrera pedida y de las holguras del
perfil de la impresora; el Part Designer diseñará después cada pieza a
partir de estas medidas. Las posiciones salen de `sim.linkages`.

Apilado en altura (Z), con un hueco axial entre capas para que nada roce:

    biela       ── capa 2
    manivela, corredera ── capa 1 (misma altura)
    bancada con raíles ── base, cara superior en z = 0

Ejes de las articulaciones: M3. Su diámetro, 3.0, es el medido en la caña
del tornillo de referencia (library/models/reference/screw_m3x10_iso4762).
"""

from mech_toolkit.geometry import Placement
from mech_toolkit.profile import PrinterProfile
from orchestrator.schemas.recipe import Recipe, RecipeStep
from sim.linkages import SliderCrank

PIN_D = 3.0  # caña del M3 de referencia, medida con el extractor


class SliderCrankLayout:
    def __init__(
        self,
        stroke_mm: float,
        profile: PrinterProfile,
        rod_ratio: float = 3.0,
        width: float = 10.0,
        thickness: float = 5.0,
        gap: float = 0.5,
        base_t: float = 4.0,
        slider_len: float = 20.0,
        slider_w: float = 12.0,
        rail_w: float = 4.0,
    ) -> None:
        self.r = stroke_mm / 2
        self.l = rod_ratio * self.r
        self.kinematics = SliderCrank(self.r, self.l)
        self.width, self.thickness, self.gap, self.base_t = width, thickness, gap, base_t
        self.slider_len, self.slider_w, self.rail_w = slider_len, slider_w, rail_w

        # Holguras del PERFIL, no inventadas: las articulaciones giran con
        # juego de "clearance" y la corredera desliza con juego de "slide".
        self.hole_d = PIN_D + profile.fit_mm("clearance")
        self.rail_inner_y = slider_w / 2 + profile.fit_mm("slide") / 2
        self.rail_y = self.rail_inner_y + rail_w / 2

        alcance_manivela = self.r + width / 2
        self.rail_x0 = max(alcance_manivela + 3, self.l - self.r - slider_len / 2 - 3)
        self.rail_x1 = self.l + self.r + slider_len / 2 + 3
        self.base_x0 = -(alcance_manivela + 5)
        self.base_x1 = self.rail_x1 + 5
        self.base_half_w = max(alcance_manivela + 5, self.rail_y + rail_w / 2 + 5)

    # --- piezas ---------------------------------------------------------------

    def recipes(self) -> dict[str, Recipe]:
        """Recetas de referencia de cada pieza. El Part Designer recibirá las
        mismas medidas como enunciado y emitirá su propia receta."""
        caja = lambda l, w, h, x, y, z: RecipeStep(  # noqa: E731
            generator="generate_box",
            params={"length_mm": l, "width_mm": w, "height_mm": h, "x_mm": x, "y_mm": y, "z_mm": z},
        )
        agujero = lambda x, y: RecipeStep(  # noqa: E731
            generator="generate_hole", params={"diameter_mm": self.hole_d, "x_mm": x, "y_mm": y})
        barra = lambda d: RecipeStep(  # noqa: E731
            generator="generate_link",
            params={"center_distance_mm": d, "width_mm": self.width,
                    "thickness_mm": self.thickness, "hole_diameter_mm": self.hole_d})

        largo_rail = self.rail_x1 - self.rail_x0
        centro_rail = (self.rail_x0 + self.rail_x1) / 2
        alto_rail = self.thickness + self.gap
        return {
            "bancada": Recipe(part="bancada", steps=[
                caja(self.base_x1 - self.base_x0, 2 * self.base_half_w, self.base_t,
                     (self.base_x0 + self.base_x1) / 2, 0, -self.base_t),
                caja(largo_rail, self.rail_w, alto_rail, centro_rail, self.rail_y, 0),
                caja(largo_rail, self.rail_w, alto_rail, centro_rail, -self.rail_y, 0),
                agujero(0, 0),
            ]),
            "manivela": Recipe(part="manivela", steps=[barra(self.r)]),
            "biela": Recipe(part="biela", steps=[barra(self.l)]),
            "corredera": Recipe(part="corredera", steps=[
                caja(self.slider_len, self.slider_w, self.thickness, 0, 0, 0),
                agujero(0, 0),
            ]),
        }

    def pins(self) -> dict[str, tuple[float, float]]:
        """Ejes de las articulaciones: nombre -> (diámetro, largo)."""
        capa2_top = 2 * self.gap + 2 * self.thickness
        return {
            # Acaba a media holgura por encima de la manivela: la biela pasa
            # por encima del pivote cuando la manivela apunta hacia atrás
            # (~180°). Con 1 mm de más chocaban; lo encontró el barrido.
            "eje_pivote": (PIN_D, self.base_t + self.gap + self.thickness + self.gap / 2),
            "eje_muñon": (PIN_D, capa2_top + 1 - self.gap),
            "eje_corredera": (PIN_D, capa2_top + 1 - self.gap),
        }

    # --- posiciones -----------------------------------------------------------

    def poses(self, grados: float) -> dict[str, Placement]:
        k = self.kinematics.at(grados)
        z1 = self.gap
        z2 = self.gap + self.thickness + self.gap
        px, py = k.crank_pin
        return {
            "bancada": Placement(),
            "manivela": Placement(origin=[0, 0, z1], rotation=[0, 0, grados]),
            "biela": Placement(origin=[px, py, z2], rotation=[0, 0, k.rod_angle_deg]),
            "corredera": Placement(origin=[k.slider_x, 0, z1]),
            "eje_pivote": Placement(origin=[0, 0, -self.base_t]),
            "eje_muñon": Placement(origin=[px, py, z1]),
            "eje_corredera": Placement(origin=[k.slider_x, 0, z1]),
        }
