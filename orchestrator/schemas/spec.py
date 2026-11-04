"""Especificación de un proyecto. Ver SISTEMA_MULTIAGENTE.md § 4.2."""

import re
from typing import Literal

from pydantic import BaseModel, model_validator

from orchestrator.traceability import requested_dimensions

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


TipoRequisito = Literal["cota", "agujero", "encaje", "fijacion", "carga",
                        "imprimibilidad", "funcion", "estetica"]


class Requisito(BaseModel):
    """Una cosa que la pieza tiene que cumplir, con nombre (F3.17 (requisitos)).

    Antes la petición viajaba como prosa: no se podía medir qué cota era un
    agujero y cuál un fondo, y las modificaciones se apilaban como texto
    (Ø34 y Ø40 convivieron en el prompt del sargento). Con `id`, una
    modificación REEMPLAZA un requisito, y la medida y el revisor pueden
    decir cuál falla."""

    id: str
    tipo: TipoRequisito
    texto: str
    """Si `origen` es `usuario`, una cita LITERAL de la petición: el código
    comprueba que está. Si no, por qué se supuso."""
    valor: float | None = None
    unidad: str = "mm"
    origen: Literal["usuario", "estimado", "catalogo"]
    cantidad: int | None = None
    """Para un `agujero`: cuántos de ese diámetro. Sin esto «faltan 2 de
    los 4 agujeros del NEMA17» no se podía medir (F6.7 (lazo))."""
    separaciones_mm: list[float] = []
    """Para un `agujero`: distancias entre centros que pide la petición
    («separados 60 mm», «en cuadro de 31»). Cuentan como cotas cubiertas."""


def _normal(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().casefold()


def errores_de_requisitos(requisitos: list[Requisito], peticion: str) -> list[str]:
    """Lo que el modelo no puede saltarse, comprobado por el código.

    Una cita inventada pasaría por requisito del usuario algo que nunca
    dijo, y una cota sin requisito es una cota que nadie va a medir."""
    errores = []
    peticion_normal = _normal(peticion)
    for r in requisitos:
        if r.origen == "usuario" and _normal(r.texto) not in peticion_normal:
            errores.append(
                f"{r.id}: dice venir del usuario, pero «{r.texto}» no está en la petición. "
                "Cita el fragmento tal cual, o márcalo como `estimado`.")
    cubiertas = [r.valor for r in requisitos if r.valor is not None and r.unidad == "mm"]
    cubiertas += [s for r in requisitos for s in r.separaciones_mm]
    for cota in requested_dimensions(peticion):
        if not any(abs(v - cota) < 1e-6 for v in cubiertas):
            errores.append(
                f"la petición dice {cota:g} mm y ningún requisito lleva ese valor "
                "(`valor` con `unidad: mm`). Añade el requisito que le corresponda.")
    return errores


class Spec(BaseModel):
    title: str
    description: str
    request: str = ""
    """Petición LITERAL del usuario. La pone el código, no el modelo: el
    resumen de `description` puede perder cotas y esto no (bug real: el
    modelo resumió "agujeros de 3.3 mm" y el diseñador acabó usando 3.2)."""
    product_class: ProductClass
    printer: str
    material: str

    reach_mm: float | None = None
    payload_g: float | None = None

    estimated: list[str] = []
    """Campos que el modelo SUPUSO en vez de oírselos al usuario (F1.2 (procedencia)).

    Sin esta marca, un `payload_g` inventado es indistinguible de uno
    dicho por el usuario, y la admisión no sabe qué tiene que preguntar."""

    requisitos: list[Requisito] = []

    @model_validator(mode="after")
    def _ids_unicos(self) -> "Spec":
        ids = [r.id for r in self.requisitos]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(f"requisitos con el id repetido: {repetidos}")
        return self

    @property
    def estimated_critical(self) -> list[str]:
        """Estimados de los que depende una fase posterior: los que la
        admisión debe preguntar (F5.3 (admisión)). Un material supuesto no rompe nada;
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
