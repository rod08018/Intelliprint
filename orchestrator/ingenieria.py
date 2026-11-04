"""Cuentas de ingeniería que hace el código, no el modelo (F3.19 (resistencia)).

El ingeniero (F3.18 (ingeniero)) decide el CASO de carga —qué parte trabaja,
con cuánto peso, a qué distancia y con qué sección— y aquí se calcula si
aguanta. Un modelo se equivoca en una potencia o en una unidad y no se
nota; esta cuenta tiene tests hechos a mano.

Modelo: voladizo de sección rectangular con la carga en la punta, flexión
simple en el empotramiento (σ = M / W, W = b·h²/6). Es el caso que manda en
escuadras, ganchos, soportes y brazos. NO cubre concentración de tensiones
en esquinas vivas, pandeo, fatiga ni fluencia: eso lo absorbe el factor de
seguridad del perfil, que por eso es alto. Un FEM de verdad (CalculiX) queda
como seguimiento.
"""

import math

from pydantic import BaseModel, Field

G = 9.81


class Material(BaseModel):
    xy_MPa: float = Field(gt=0)
    """Resistencia a lo largo del filamento: la pieza trabaja en el plano de capa."""
    z_MPa: float = Field(gt=0)
    """Resistencia entre capas: la pieza tira de una capa para separarla."""
    factor_seguridad: float = Field(gt=1)

    @classmethod
    def del_perfil(cls, datos: dict) -> "Material":
        """Del YAML de impresora+material: el valor cambia con el material y
        tiene que cambiar con el perfil activo, no vivir en el código."""
        r = datos["resistencia"]
        return cls(xy_MPa=r["xy_MPa"], z_MPa=r["z_MPa"],
                   factor_seguridad=r["factor_seguridad"])


class CasoDeCarga(BaseModel):
    que: str
    """Qué parte trabaja: «brazo de la escuadra, empotrado en el ala de pared»."""
    carga_kg: float = Field(gt=0)
    brazo_mm: float = Field(gt=0)
    """Distancia de la carga a la sección que se comprueba."""
    ancho_mm: float = Field(gt=0)
    """Ancho de la sección, perpendicular a la carga."""
    canto_mm: float = Field(gt=0)
    """Alto de la sección, en la dirección de la carga: el que más cuenta (al cuadrado)."""
    capas_a_traccion: bool
    """Si la flexión intenta separar capas, según la orientación de impresión."""


class Comprobacion(BaseModel):
    que: str
    tension_MPa: float
    resistencia_MPa: float
    factor_seguridad: float
    exigido: float
    cumple: bool
    canto_minimo_mm: float
    """El canto que daría el factor exigido con el mismo ancho: lo que vuelve
    al ingeniero, en vez de un «no aguanta» sin número."""

    def texto(self) -> str:
        veredicto = "aguanta" if self.cumple else "NO aguanta"
        return (f"{self.que}: σ = {self.tension_MPa:.1f} MPa contra {self.resistencia_MPa:g} MPa"
                f" → factor {self.factor_seguridad:.2f} (se exige {self.exigido:g}): {veredicto}."
                + ("" if self.cumple else
                   f" Con ese ancho hace falta un canto de al menos {self.canto_minimo_mm:.1f} mm."))


def comprobar(caso: CasoDeCarga, material: Material) -> Comprobacion:
    momento = caso.carga_kg * G * caso.brazo_mm                  # N·mm
    modulo = caso.ancho_mm * caso.canto_mm ** 2 / 6              # mm³
    tension = momento / modulo                                   # MPa
    resistencia = material.z_MPa if caso.capas_a_traccion else material.xy_MPa
    factor = resistencia / tension
    canto_minimo = math.sqrt(6 * momento * material.factor_seguridad
                             / (caso.ancho_mm * resistencia))
    return Comprobacion(
        que=caso.que, tension_MPa=tension, resistencia_MPa=resistencia,
        factor_seguridad=factor, exigido=material.factor_seguridad,
        cumple=factor >= material.factor_seguridad, canto_minimo_mm=canto_minimo)
