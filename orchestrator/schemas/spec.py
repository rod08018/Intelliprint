"""Especificación de un proyecto. Ver SISTEMA_MULTIAGENTE.md § 4.2."""

from typing import Literal

from pydantic import BaseModel, model_validator

ProductClass = Literal["static_part", "mechanism", "robot"]
"""Decide qué fases corren (§ 4.2). Un agente que no corre no alucina."""

_OBLIGATORIOS_POR_CLASE: dict[str, tuple[str, ...]] = {
    # La clase no es una etiqueta: decide qué datos son obligatorios, porque
    # decide qué agentes van a correr y qué necesita cada uno.
    "static_part": (),
    "mechanism": ("payload_g",),           # Actuation: margen de torque
    "robot": ("reach_mm", "payload_g"),    # + Kinematics: espacio de trabajo
}

_ESTIMABLES = {"printer", "material", "payload_g", "reach_mm"}
"""Los datos de la petición. Título, descripción y clase son siempre síntesis
del modelo, así que marcarlos como estimados no aportaría nada."""


class Spec(BaseModel):
    title: str
    description: str
    product_class: ProductClass
    printer: str
    material: str

    reach_mm: float | None = None
    payload_g: float | None = None

    estimated: list[str] = []
    """Campos que el modelo SUPUSO en vez de oírselos al usuario (F1.2).

    Sin esta marca, un `payload_g` inventado es indistinguible de uno
    dicho por el usuario, y la admisión no sabe qué tiene que preguntar."""

    @property
    def estimated_critical(self) -> list[str]:
        """Estimados de los que depende una fase posterior: los que la
        admisión debe preguntar (F5.3). Un material supuesto no rompe nada;
        una carga inventada da un actuador que no puede con ella."""
        exigidos = _OBLIGATORIOS_POR_CLASE[self.product_class]
        return [c for c in self.estimated if c in exigidos]

    @model_validator(mode="after")
    def _estimados_existen(self) -> "Spec":
        desconocidos = sorted(set(self.estimated) - _ESTIMABLES)
        if desconocidos:
            raise ValueError(
                f"`estimated` marca campos que no existen o no se estiman: "
                f"{desconocidos}. Estimables: {sorted(_ESTIMABLES)}"
            )
        return self

    @model_validator(mode="after")
    def _datos_obligatorios_de_la_clase(self) -> "Spec":
        exigidos = _OBLIGATORIOS_POR_CLASE[self.product_class]
        faltantes = [c for c in exigidos if getattr(self, c) is None]
        if faltantes:
            raise ValueError(
                f"la clase {self.product_class!r} exige {faltantes}. "
                "Las fases que los consumen no pueden calcularlos, y si son "
                "opcionales el agente se los inventa (ADR-010)."
            )
        return self
