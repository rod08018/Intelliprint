"""Cinemática de mecanismos articulados (servicio `sim`, § 9.2).

Las posiciones las calcula código con fórmulas cerradas, no un modelo de
lenguaje: el modelo decide las MEDIDAS (radio, longitud de biela) a partir
de lo que pide el usuario; dónde está cada pieza en cada ángulo es
geometría y no se deja a su criterio.
"""

import math

from pydantic import BaseModel


class SliderCrankPose(BaseModel):
    crank_deg: float
    crank_pin: list[float]
    """Centro del muñón de la manivela, en el plano XY."""
    rod_angle_deg: float
    """Ángulo de la biela respecto al eje X, medido desde el muñón."""
    slider_x: float
    """Posición del pasador de la corredera sobre el eje X."""


class SliderCrank:
    """Biela-manivela-corredera en línea: manivela en el origen, corredera
    sobre el eje X, sin descentrado."""

    def __init__(self, r: float, l: float) -> None:
        if l <= r:
            raise ValueError(
                f"con biela de {l} mm y manivela de {r} mm el mecanismo se bloquea: "
                "la biela tiene que ser más larga que el radio de la manivela"
            )
        self.r, self.l = r, l

    @property
    def stroke(self) -> float:
        """Carrera de la corredera entre los dos puntos muertos."""
        return 2 * self.r

    def at(self, grados: float) -> SliderCrankPose:
        t = math.radians(grados)
        px, py = self.r * math.cos(t), self.r * math.sin(t)
        # La corredera está sobre y=0, a distancia L del muñón.
        slider_x = px + math.sqrt(self.l**2 - py**2)
        rod = math.degrees(math.atan2(-py, slider_x - px))
        return SliderCrankPose(
            crank_deg=grados, crank_pin=[px, py], rod_angle_deg=rod, slider_x=slider_x
        )
