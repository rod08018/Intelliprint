"""Informe del Design Reviewer. Ver DECISIONES.md ADR-003: es un informe
para la persona, no una aprobación."""

from typing import Literal

from pydantic import BaseModel, field_validator

Verdict = Literal["cumple", "no_cumple", "no_verificable"]


class ReviewItem(BaseModel):
    requirement: str
    verdict: Verdict
    comment: str


class ReviewReport(BaseModel):
    items: list[ReviewItem]
    summary: str
    para_el_usuario: list[str] = []
    """Lo que no salió como pidió, en llano y en tres frases como mucho: lo
    único del informe que enseña la web. «Saca como 40 mil líneas de que
    cumple y que no, a un usuario le vale pito eso» (2026-10-26)."""

    @field_validator("para_el_usuario")
    @classmethod
    def _tres_como_mucho(cls, v: list[str]) -> list[str]:
        # Recortar y no rechazar: una cuarta frase no vale un reintento.
        return [f.strip() for f in v if f.strip()][:3]

    def por_veredicto(self, veredicto: Verdict) -> list[ReviewItem]:
        return [i for i in self.items if i.verdict == veredicto]
