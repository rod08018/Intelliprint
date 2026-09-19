"""Informe del Design Reviewer. Ver DECISIONES.md ADR-003: es un informe
para la persona, no una aprobación."""

from typing import Literal

from pydantic import BaseModel

Verdict = Literal["cumple", "no_cumple", "no_verificable"]


class ReviewItem(BaseModel):
    requirement: str
    verdict: Verdict
    comment: str


class ReviewReport(BaseModel):
    items: list[ReviewItem]
    summary: str

    def por_veredicto(self, veredicto: Verdict) -> list[ReviewItem]:
        return [i for i in self.items if i.verdict == veredicto]
