"""Adaptador de consola del HumanPort (F0.9 (HumanPort))."""

import sys
from typing import TextIO

from orchestrator.human.port import HumanPort, Question


class CliAdapter(HumanPort):
    def __init__(
        self,
        entrada: TextIO | None = None,
        salida: TextIO | None = None,
    ) -> None:
        self._entrada = entrada if entrada is not None else sys.stdin
        self._salida = salida if salida is not None else sys.stdout

    def ask(self, question: Question) -> str:
        self._salida.write(f"\n{question.text}\n")
        for adjunto in question.attachments:
            self._salida.write(f"  [adjunto] {adjunto}\n")
        self._salida.write("> ")
        self._salida.flush()
        return self._entrada.readline().strip()

    def notify(self, message: str, *, project: str | None = None) -> None:
        prefijo = f"[{project}] " if project else ""
        self._salida.write(f"{prefijo}{message}\n")
        self._salida.flush()
