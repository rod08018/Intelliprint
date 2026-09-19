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

    def briefs(self) -> dict[str, str]:
        """Enunciado de cada pieza para el Part Designer: TODAS sus cotas y
        el origen de la pieza, que es el que asumen las poses. Si el modelo
        eligiera otro origen, la pieza estaría bien y el ensamble no."""
        g = lambda v: f"{v:g} mm"  # noqa: E731
        comun = (
            f"Los agujeros son para ejes M3 y miden {g(self.hole_d)} de diámetro: "
            "ya llevan la holgura, úsalos tal cual."
        )
        largo_rail = self.rail_x1 - self.rail_x0
        return {
            "bancada": (
                "Pieza «bancada»: la base fija de una biela-manivela-corredera. "
                f"Placa de {g(self.base_x1 - self.base_x0)} en X, {g(2 * self.base_half_w)} en Y "
                f"y {g(self.base_t)} de espesor, con la cara superior en z = 0 "
                f"(la placa baja {g(self.base_t)} por debajo) y centrada en "
                f"x = {g((self.base_x0 + self.base_x1) / 2)}, y = 0. "
                f"Encima, dos raíles guía de {g(largo_rail)} en X, {g(self.rail_w)} de ancho "
                f"y {g(self.thickness + self.gap)} de alto, apoyados en z = 0, centrados en "
                f"x = {g((self.rail_x0 + self.rail_x1) / 2)} y en y = ±{g(self.rail_y)}. "
                "Un agujero pasante vertical para el eje del pivote de la manivela, "
                "centrado en el origen. " + comun
            ),
            "manivela": (
                "Pieza «manivela»: barra con un agujero en cada extremo. "
                f"Distancia entre centros {g(self.r)}, ancho {g(self.width)}, "
                f"espesor {g(self.thickness)}. El origen de la pieza está en el centro "
                "del primer agujero, con el segundo sobre el eje X positivo. " + comun
            ),
            "biela": (
                "Pieza «biela»: barra con un agujero en cada extremo. "
                f"Distancia entre centros {g(self.l)}, ancho {g(self.width)}, "
                f"espesor {g(self.thickness)}. El origen de la pieza está en el centro "
                "del primer agujero, con el segundo sobre el eje X positivo. " + comun
            ),
            "corredera": (
                "Pieza «corredera»: bloque que desliza entre dos raíles. "
                f"{g(self.slider_len)} en X, {g(self.slider_w)} en Y, {g(self.thickness)} de alto, "
                "centrado en X e Y sobre el origen y apoyado en z = 0. "
                "Un agujero pasante vertical en el origen para el eje de la biela. " + comun
            ),
        }

    def bounds(self) -> dict[str, tuple[list[float], list[float]]]:
        """Caja envolvente de cada pieza en SU marco, según la disposición."""
        w, t = self.width / 2, self.thickness
        return {
            "bancada": ([self.base_x0, -self.base_half_w, -self.base_t],
                        [self.base_x1, self.base_half_w, t + self.gap]),
            "manivela": ([-w, -w, 0], [self.r + w, w, t]),
            "biela": ([-w, -w, 0], [self.l + w, w, t]),
            "corredera": ([-self.slider_len / 2, -self.slider_w / 2, 0],
                          [self.slider_len / 2, self.slider_w / 2, t]),
        }

    def check_bounds(self, nombre: str, resultado, tol: float = 0.05) -> str | None:
        """Motivo para el Part Designer si la pieza no está donde la espera
        el ensamble; None si está. Con los números de lo que hizo y de lo
        que se pedía: un "está mal colocada" a secas no se puede corregir."""
        if resultado.bbox_min is None:
            return None
        lo, hi = self.bounds()[nombre]
        fuera = [
            i for i in range(3)
            if abs(resultado.bbox_min[i] - lo[i]) > tol or abs(resultado.bbox_max[i] - hi[i]) > tol
        ]
        if not fuera:
            return None
        rango = lambda a, b, i: f"{'xyz'[i]} de {a[i]:g} a {b[i]:g} mm"  # noqa: E731
        return (
            f"la pieza ocupa {', '.join(rango(resultado.bbox_min, resultado.bbox_max, i) for i in fuera)}; "
            f"el ensamble la necesita en {', '.join(rango(lo, hi, i) for i in fuera)}. "
            "Revisa el origen y la posición de cada cuerpo: si un generador no deja "
            "colocar el cuerpo donde pide el enunciado, usa otro que sí lo permita."
        )

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
