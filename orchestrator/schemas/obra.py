"""El árbol de un proyecto por partes (F7.2 (desglose)).

Cada nodo es algo que se diseña de una vez: una pieza del tamaño de un
encargo del banco, que es lo que ya sale, o un conjunto que se mueve. Las
dependencias son físicas: B depende de A si se une a A o se apoya en ella,
y por eso B se diseña contra la ficha de A ya terminada.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_METRICA = re.compile(r"^M\d+(\.\d+)?$")
EXTERIOR = "exterior"
"""Donde agarra un tornillo que sale del invento: la mesa, una pared."""


class Nodo(BaseModel):
    id: str
    """Corto, en minúsculas y con guiones: da nombre a su carpeta y a su
    ficha (`obra-<id>`)."""
    nombre: str
    tipo: Literal["pieza", "conjunto"] = "pieza"
    """«conjunto»: piezas que se mueven unas respecto de otras. Solo ahí hay
    simulación (F7.4 (conjunto)); una pieza sola solo se mide."""
    que_hace: str
    compra: list[str] = []
    """Ids de la biblioteca de componentes que lleva (un SG90, un 608ZZ)."""
    depende_de: list[str] = []
    """Los nodos a los que se une o en los que se apoya."""
    ofrece: list[str] = []
    """Lo que da a las demás, corto y medible: «asiento Ø22 para un 608ZZ»."""
    necesita: list[str] = []


class Fija(BaseModel):
    """Dos piezas atornilladas, o una pieza atornillada a algo de fuera
    (F9.2 (uniones)). Sin coordenadas: dónde cae cada tornillo lo decide el
    diseño de la pieza, y se mide en lo construido."""
    tipo: Literal["fija"]
    id: str
    cabeza: str
    """El nodo donde apoya la cabeza del tornillo: lleva el agujero pasante."""
    agarra: str
    """El nodo donde agarra, o «exterior»."""
    metrica: str
    cantidad: int = Field(ge=1, le=12)
    agarre: Literal["tuerca", "inserto", "rosca"] | None = None
    """Cómo agarra en la pieza: tuerca cautiva, inserto térmico o rosca en
    el plástico. Lo propone el plan en cada unión y la persona lo ve antes
    de aprobar (decidido con el usuario, 2026-11-10). En el exterior no lo
    decide el invento."""
    grosor_exterior_mm: float | None = Field(default=None, gt=0)
    """Solo si la petición lo dice («un tablero de 18 mm»): con él la lista
    de compras da el largo del tornillo en vez de «lo que entre donde se
    fije»."""

    def nodos(self) -> tuple[str, ...]:
        return tuple(n for n in (self.cabeza, self.agarra) if n != EXTERIOR)


class Gira(BaseModel):
    """Una pieza que gira sobre la salida de algo comprado que monta otra:
    el eje de un servo, el aro de un rodamiento (F9.2 (uniones))."""
    tipo: Literal["gira"]
    id: str
    gira: str
    sobre: str
    """El nodo que monta el componente. La que gira se diseña después y
    contra él."""
    componente: str
    """La ficha de lo que la mueve, que está en `compra` de `sobre`."""
    salida: str = ""
    """El nombre de la salida en la ficha; vacío si solo tiene una."""
    recorrido_grados: float = Field(gt=0, le=360)
    radio_libre_mm: float | None = Field(default=None, gt=0)
    """Cuánto sitio necesita lo que gira alrededor del eje, desde la cara de
    la salida hacia fuera. Es un presupuesto que se reparte entre dos
    piezas: la que monta el actuador no mete nada ahí, y la que gira no pasa
    de él. El pan-tilt del banco 1110-0313 no lo tenía: su soporte dejó
    12.7 mm para una plataforma de 37.7."""

    def nodos(self) -> tuple[str, ...]:
        return (self.gira, self.sobre)


Union = Annotated[Fija | Gira, Field(discriminator="tipo")]


class Obra(BaseModel):
    titulo: str
    nodos: list[Nodo] = Field(min_length=1)
    uniones: list[Union] = []
    """Cómo se unen las piezas. Los backlogs de antes del 2026-11-10 no las
    tienen, y siguen cargando."""

    @model_validator(mode="after")
    def _arbol(self):
        vistos = set()
        for n in self.nodos:
            if not _ID.match(n.id):
                raise ValueError(f"id «{n.id}»: minúsculas, números y guiones, sin espacios")
            if n.id in vistos:
                raise ValueError(f"id «{n.id}» repetido")
            vistos.add(n.id)
        for n in self.nodos:
            for d in n.depende_de:
                if d not in vistos:
                    raise ValueError(f"«{n.id}» depende de «{d}», que no es un nodo")
        self.orden()
        self._uniones_posibles()
        return self

    def _uniones_posibles(self) -> None:
        """Lo que una unión no puede ser, sin mirar ninguna ficha. Lo que
        depende de las fichas y del perfil lo comprueba `plan.validar_plan`."""
        vistas: set[str] = set()
        giran: dict[str, str] = {}
        for u in self.uniones:
            if u.id in vistas:
                raise ValueError(f"unión «{u.id}» repetido: cada unión lleva su id")
            vistas.add(u.id)
            for i in u.nodos():
                try:
                    n = self.nodo(i)
                except KeyError as e:   # ya dice qué nodos hay
                    raise ValueError(f"unión «{u.id}»: {e.args[0]}")
                if n.tipo == "conjunto":
                    raise ValueError(f"unión «{u.id}»: «{i}» es un conjunto, no una pieza; "
                                     "las uniones van entre piezas")
            if isinstance(u, Fija):
                self._fija_posible(u)
            else:
                self._gira_posible(u, giran)
        for u in self.uniones:
            if isinstance(u, Fija) and len(u.nodos()) == 2:
                for a, b in (u.nodos(), u.nodos()[::-1]):
                    if giran.get(a) == b:
                        raise ValueError(
                            f"unión «{u.id}»: «{a}» gira sobre «{b}»; no puede ir además "
                            "atornillada a ella")

    def _fija_posible(self, u: "Fija") -> None:
        if not _METRICA.match(u.metrica):
            raise ValueError(f"unión «{u.id}»: «{u.metrica}» no es una métrica; se escribe "
                             "«M3», «M2.5»")
        if u.cabeza == EXTERIOR:
            raise ValueError(f"unión «{u.id}»: la cabeza del tornillo apoya en una pieza; "
                             f"«{EXTERIOR}» solo puede ser donde agarra")
        if u.agarra == EXTERIOR:
            return
        if u.cabeza == u.agarra:
            raise ValueError(f"unión «{u.id}»: une «{u.cabeza}» consigo misma")
        a, b = self.nodo(u.cabeza), self.nodo(u.agarra)
        if b.id not in a.depende_de and a.id not in b.depende_de:
            raise ValueError(
                f"unión «{u.id}»: «{a.id}» no depende de «{b.id}» ni al revés. Dos piezas "
                "que se atornillan se diseñan una contra la otra: pon la dependencia")
        if u.agarre is None:
            raise ValueError(f"unión «{u.id}»: falta el agarre: «tuerca», «inserto» o "
                             "«rosca»")

    def _gira_posible(self, u: "Gira", giran: dict[str, str]) -> None:
        if u.sobre not in self.nodo(u.gira).depende_de:
            raise ValueError(
                f"unión «{u.id}»: «{u.gira}» no depende de «{u.sobre}». La pieza que gira "
                "se diseña después de la que monta el actuador, y contra ella")
        lleva = self.nodo(u.sobre).compra
        if u.componente not in lleva:
            raise ValueError(
                f"unión «{u.id}»: «{u.sobre}» no lleva «{u.componente}» en `compra`; lleva: "
                + (", ".join(lleva) or "nada"))
        if u.gira in giran:
            raise ValueError(
                f"unión «{u.id}»: «{u.gira}» gira sobre dos piezas («{giran[u.gira]}» y "
                f"«{u.sobre}»). Un conjunto es un árbol: cada pieza gira sobre una sola")
        giran[u.gira] = u.sobre

    def uniones_de(self, id_: str) -> list:
        """Las uniones en las que entra el nodo `id_`."""
        return [u for u in self.uniones if id_ in u.nodos()]

    def nodo(self, id_: str) -> Nodo:
        for n in self.nodos:
            if n.id == id_:
                return n
        raise KeyError(f"no hay nodo «{id_}»; hay: {', '.join(n.id for n in self.nodos)}")

    def orden(self) -> list[str]:
        """De lo que no depende de nada a lo que depende de todo; entre
        iguales, en el orden en que se escribieron."""
        hechos: list[str] = []
        pendientes = list(self.nodos)
        while pendientes:
            listos = [n for n in pendientes if all(d in hechos for d in n.depende_de)]
            if not listos:
                raise ValueError("las dependencias forman un ciclo: "
                                 + ", ".join(n.id for n in pendientes))
            hechos.append(listos[0].id)
            pendientes.remove(listos[0])
        return hechos

    def dependientes(self, id_: str) -> list[str]:
        """Los que dependen de `id_`, directa o indirectamente, en orden."""
        afectados = {id_}
        for i in self.orden():
            if any(d in afectados for d in self.nodo(i).depende_de):
                afectados.add(i)
        return [i for i in self.orden() if i in afectados and i != id_]
