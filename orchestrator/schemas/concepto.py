"""El concepto del ingeniero: cómo se resuelve, antes de dibujar (F3.18 (ingeniero))."""

from pydantic import BaseModel, Field

from orchestrator.ingenieria import CasoDeCarga, Comprobacion
from orchestrator.schemas.uso import Uso


class ComponenteDelConcepto(BaseModel):
    """Un componente comprado que la pieza aloja (F6.11 (biblioteca)). Su
    forma está en la ficha; el concepto decide cómo entra y cómo se sujeta."""
    id: str
    como_entra: str
    """Por dónde se mete y en qué dirección: el soporte del HC-SR04 abría el
    canal por arriba y los transductores atravesaban la pared de delante."""
    como_se_sujeta: str


class Concepto(BaseModel):
    idea: str
    """Cómo resuelve el problema, en dos o tres frases."""
    camino_de_carga: str
    orientacion: str
    """Qué cara va a la cama y por qué: decide si las capas trabajan a tracción."""
    fijaciones: list[str] = []
    componentes: list[ComponenteDelConcepto] = []
    uso: Uso = "general"
    casos_de_carga: list[CasoDeCarga] = []
    alternativas: list[str] = Field(default=[], max_length=2)
    preguntas: list[str] = Field(default=[], max_length=3)
    """Solo cotas críticas que faltan. Una o dos, no un interrogatorio."""


class ConceptoComprobado(BaseModel):
    """El concepto y lo que el código calculó de él: es lo que se aprueba."""

    concepto: Concepto
    comprobaciones: list[Comprobacion] = []

    def texto(self) -> str:
        """Lo que lee la persona antes de dar el visto bueno, por consola, web
        o Telegram: tiene que entenderse sin saber qué es un JSON."""
        c = self.concepto
        lineas = [f"**Idea:** {c.idea}", "",
                  f"**Cómo trabaja:** {c.camino_de_carga}", "",
                  f"**Cómo se imprime:** {c.orientacion}"]
        if c.fijaciones:
            lineas += ["", "**Fijaciones:**", *(f"- {f}" for f in c.fijaciones)]
        if c.componentes:
            lineas += ["", "**Lo que aloja:**", *(f"- {_presentar(x)}" for x in c.componentes)]
        if self.comprobaciones:
            lineas += ["", "**Cálculo:**", *(f"- {x.texto()}" for x in self.comprobaciones)]
        if c.alternativas:
            lineas += ["", "**Otras formas, descartadas:**", *(f"- {a}" for a in c.alternativas)]
        if c.preguntas:
            lineas += ["", "**Necesito que me digas:**", *(f"- {p}" for p in c.preguntas)]
        return "\n".join(lineas)

    def para_el_disenador(self) -> str:
        c = self.concepto
        partes = [
            "Concepto aprobado por el usuario. Dibuja ESTA idea, no otra:",
            f"- Idea: {c.idea}",
            f"- Camino de carga: {c.camino_de_carga}",
            f"- Orientación de impresión: {c.orientacion}",
        ]
        partes += [f"- Fijación: {f}" for f in c.fijaciones]
        for x in c.componentes:
            # Con la ficha entera: sin ella, el soporte del HC-SR04 dibujó el
            # sensor con cajas y cifras de una tienda (2026-11-05).
            partes.append(
                f"- Componente `{x.id}`: entra {x.como_entra}; se sujeta: {x.como_se_sujeta}. "
                f"Colócalo con `kit.componente(\"{x.id}\", en=..., girar=..., entra_por=...)` "
                "y quita su `hueco()` a la pieza. NUNCA lo dibujes con cajas: su forma es "
                "la de la ficha, y al construir se mete en la pieza para ver si cabe y si "
                "entra.\n\n" + _resumen(x.id) + "\n")
        for caso in c.casos_de_carga:
            # La sección es un mínimo: el cálculo la dio por buena así, y
            # adelgazarla al dibujar deshace la comprobación.
            partes.append(f"- Sección mínima de «{caso.que}»: {caso.ancho_mm:g} x "
                          f"{caso.canto_mm:g} mm (ancho x canto en la dirección de la carga)")
        return "\n".join(partes)


def _resumen(id_: str) -> str:
    from orchestrator.componentes import cargar, resumen
    try:
        return resumen(cargar(id_))
    except KeyError:
        return f"(no hay ficha de «{id_}» en la biblioteca)"


def _presentar(x: ComponenteDelConcepto) -> str:
    from urllib.parse import urlparse

    from orchestrator.componentes import cargar
    try:
        f = cargar(x.id)
    except KeyError:
        return f"{x.id} (sin ficha): entra {x.como_entra}; se sujeta: {x.como_se_sujeta}"
    medido = "medido con calibre" if f.verificado else "sin verificar con calibre"
    fuente = urlparse(f.fuentes[0].url).hostname.removeprefix("www.")
    return (f"{f.nombre} (ficha de {fuente}, {medido}): entra {x.como_entra}; "
            f"se sujeta: {x.como_se_sujeta}")
