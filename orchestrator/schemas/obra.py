"""El árbol de un proyecto por partes (F7.2 (desglose)).

Cada nodo es algo que se diseña de una vez: una pieza del tamaño de un
encargo del banco, que es lo que ya sale, o un conjunto que se mueve. Las
dependencias son físicas: B depende de A si se une a A o se apoya en ella,
y por eso B se diseña contra la ficha de A ya terminada.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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


class Obra(BaseModel):
    titulo: str
    nodos: list[Nodo] = Field(min_length=1)

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
        return self

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
