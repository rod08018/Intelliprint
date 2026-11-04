"""El concepto del ingeniero: cómo se resuelve, antes de dibujar (F3.18 (ingeniero))."""

from pydantic import BaseModel, Field

from orchestrator.ingenieria import CasoDeCarga, Comprobacion
from orchestrator.schemas.uso import Uso


class Concepto(BaseModel):
    idea: str
    """Cómo resuelve el problema, en dos o tres frases."""
    camino_de_carga: str
    orientacion: str
    """Qué cara va a la cama y por qué: decide si las capas trabajan a tracción."""
    fijaciones: list[str] = []
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
        for caso in c.casos_de_carga:
            # La sección es un mínimo: el cálculo la dio por buena así, y
            # adelgazarla al dibujar deshace la comprobación.
            partes.append(f"- Sección mínima de «{caso.que}»: {caso.ancho_mm:g} x "
                          f"{caso.canto_mm:g} mm (ancho x canto en la dirección de la carga)")
        return "\n".join(partes)
