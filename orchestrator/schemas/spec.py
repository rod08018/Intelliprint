"""Especificación de un proyecto. Ver SISTEMA_MULTIAGENTE.md § 4.2."""

import re
from typing import Literal

from pydantic import BaseModel, model_validator

from orchestrator.traceability import CONTEXTO, requested_dimensions

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
    seccion_mm: list[float] = []
    """Para un `encaje`: la sección del cuerpo que tiene que pasar, ancho y
    alto («el servo mide 40.7 x 19.7»). Se comprueba al construir que pasa
    por una abertura de la pieza: en el banco, la «ventana» del MG996R era un
    rebaje ciego de 4 mm y nadie se lo dijo al diseñador (2026-11-04)."""
    separaciones_mm: list[float] = []
    """Para un `agujero`: distancias entre centros que pide la petición
    («separados 60 mm», «en cuadro de 31»). Cuentan como cotas cubiertas."""


def _normal(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().casefold()


def _es_del_sistema(texto: str, peticion: str) -> bool:
    """Si `texto` no está en lo que pidió el usuario y sus trozos —lo que
    queda entre puntos suspensivos— salen todos de lo que el sistema escribe
    en la petición de una pieza de un backlog (`traceability.CONTEXTO`).

    Entero o abreviado, da igual: la carcasa del encargo 16 (banco
    1114-0535) citó al pie de la letra «El hueco de tu carcasa tiene que
    llegar, como poco, a: x de…», que es del sistema, y como la cita estaba
    en la petición pasó por requisito del usuario: un encaje de 44.3 × 44.3
    que se le exigió como ventana pasante."""
    suyo, hay, contexto = peticion.partition(CONTEXTO)
    if not hay or _normal(texto) in _normal(suyo):
        return False
    trozos = [t for t in (_normal(t) for t in re.split(r"\.{3}|…", texto)) if t]
    return bool(trozos) and all(t in _normal(contexto) for t in trozos)


def sin_lo_del_sistema(requisitos: list["Requisito"], peticion: str) -> list["Requisito"]:
    """Fuera los «requisitos» que son la instrucción del sistema, abreviada.
    Al reanudar el brazo mediano (banco 1113-1330) el brazo superior no pasó
    de aquí, tres veces: el modelo hizo un requisito del usuario con «Se une
    a estas piezas, ya terminadas... colócalas con `kit.componente`…», y la
    cita, con sus puntos suspensivos, no estaba tal cual en la petición. Eso
    le llega al diseñador por la petición y por las uniones: no se pierde."""
    return [r for r in requisitos
            if not (r.origen == "usuario" and _es_del_sistema(r.texto, peticion))]


def errores_de_requisitos(requisitos: list[Requisito], peticion: str,
                          externos: str = "") -> list[str]:
    """Lo que el modelo no puede saltarse, comprobado por el código.

    Una cita inventada pasaría por requisito del usuario algo que nunca
    dijo, y una cota sin requisito es una cota que nadie va a medir.

    `externos`: lo buscado en internet (F3.21 (investigar)). Sus cotas hay
    que cubrirlas igual, pero NO cuentan como dichas por el usuario: van
    como `catalogo`, y quien aprueba el concepto ve de dónde salen."""
    errores = []
    peticion_normal = _normal(peticion)
    for r in requisitos:
        if r.origen == "usuario" and _normal(r.texto) not in peticion_normal:
            if _es_del_sistema(r.texto, peticion):
                continue    # no es un requisito: se quita (`sin_lo_del_sistema`)
            errores.append(
                f"{r.id}: dice venir del usuario, pero «{r.texto}» no está en la petición. "
                "Cita el fragmento tal cual, o márcalo como `estimado`.")
    cubiertas = [r.valor for r in requisitos if r.valor is not None and r.unidad == "mm"]
    cubiertas += [s for r in requisitos for s in r.separaciones_mm + r.seccion_mm]
    for cota in requested_dimensions(peticion) + requested_dimensions(externos):
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
