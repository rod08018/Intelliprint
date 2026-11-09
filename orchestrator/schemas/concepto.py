"""El concepto del ingeniero: cómo se resuelve, antes de dibujar (F3.18 (ingeniero))."""

from typing import Literal

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
    ajuste: Literal["press", "slide", "clearance"] = "slide"
    """El ajuste por su nombre; el diámetro lo pone `hueco()` con la holgura
    del perfil. En el proyecto del 608ZZ (2026-11-06) el concepto pedía un
    alojamiento de Ø21.9 «con 0.1 de interferencia», contra el perfil, que
    pone +0.10 sobre el nominal para «press» porque los agujeros FDM salen
    pequeños: habría salido de 21.7 y el rodamiento no entraba."""


AJUSTES = {"press": "a presión", "slide": "deslizante", "clearance": "con holgura"}


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
    cambios: list[str] = []
    """Con un concepto anterior: qué cambia respecto a él y por qué. La base
    del pan-tilt (2026-11-09) perdió en silencio los tornillos que la fijaban
    al rehacerla por otra cosa; lo que cambia tiene que verse al aprobar."""


class ConceptoComprobado(BaseModel):
    """El concepto y lo que el código calculó de él: es lo que se aprueba."""

    concepto: Concepto
    comprobaciones: list[Comprobacion] = []

    def texto(self) -> str:
        """Lo que lee la persona antes de dar el visto bueno, por consola, web
        o Telegram: tiene que entenderse sin saber qué es un JSON."""
        c = self.concepto
        lineas = []
        if c.cambios:
            lineas += ["**Qué cambia respecto al concepto anterior:**",
                       *(f"- {x}" for x in c.cambios), ""]
        lineas += [f"**Idea:** {c.idea}", "",
                  f"**Cómo trabaja:** {c.camino_de_carga}", "",
                  f"**Cómo se imprime:** {c.orientacion}"]
        if c.fijaciones:
            lineas += ["", "**Fijaciones:**", *(f"- {f}" for f in c.fijaciones)]
        if c.componentes:
            lineas += ["", "**Lo que aloja:**", *(_presentar(x) for x in c.componentes)]
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
        partes += [f"- Cambio que pidió la persona: {x}" for x in c.cambios]
        for x in c.componentes:
            # Con la ficha entera: sin ella, el soporte del HC-SR04 dibujó el
            # sensor con cajas y cifras de una tienda (2026-11-05).
            hueco = "hueco()" if x.ajuste == "slide" else f'hueco(holgura="{x.ajuste}")'
            partes.append(
                f"- Componente `{x.id}`. Cómo entra: {x.como_entra} Cómo se sujeta: "
                f"{x.como_se_sujeta} Ajuste: {AJUSTES[x.ajuste]}. "
                f"Colócalo con `kit.componente(\"{x.id}\", en=..., girar=..., entra_por=...)` "
                f"y quita su `{hueco}` a la pieza: el diámetro del alojamiento lo pone "
                "el ajuste con la holgura del perfil, no lo dibujes a mano. NUNCA lo "
                "dibujes con cajas: su forma es "
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
    from orchestrator.componentes import cargar, fuente as sitio
    detalle = (f"  - Cómo entra: {x.como_entra}\n  - Cómo se sujeta: {x.como_se_sujeta}\n"
               f"  - Ajuste: {AJUSTES[x.ajuste]} (la holgura sale del perfil de la impresora)")
    try:
        f = cargar(x.id)
    except KeyError:
        return f"- {x.id} (sin ficha)\n{detalle}"
    medido = "medido con calibre" if f.verificado else "sin verificar con calibre"
    fuente = sitio(f.fuentes[0].url)
    return f"- {f.nombre} (ficha de {fuente}, {medido})\n{detalle}"
