"""`HumanPort`: un puerto, tres adaptadores.

Ver SISTEMA_MULTIAGENTE.md § 8.5 y DECISIONES.md ADR-006.

Los dos gates, la confirmación de la admisión, las preguntas del
Requirements Agent y las consultas del QA son **la misma operación**:
preguntar algo a un humano y esperar. Se implementa una sola vez aquí, y
cada adaptador decide por qué canal viaja.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel


_AFIRMACIONES = frozenset({"sí", "si", "s", "y", "yes"})
"""Lista blanca corta y deliberada. En una barrera de seguridad el
silencio y lo ambiguo tienen que significar NO, así que no se interpreta
lenguaje natural: cualquier cosa fuera de este conjunto no aprueba."""


class Question(BaseModel):
    text: str
    attachments: list[str] = []
    """Rutas dentro de `workspace/`. Por consola se listan; por Telegram
    se envían como imágenes."""
    project: str | None = None


class HumanPort(ABC):
    """Un adaptador transporta preguntas y respuestas. No decide nada de
    diseño, no lee ni escribe el blackboard y no aparece en el grafo."""

    @abstractmethod
    def ask(self, question: Question) -> str:
        """Pregunta y espera. Puede tardar días (regla 7 de § 4)."""

    @abstractmethod
    def notify(self, message: str, *, project: str | None = None) -> None:
        """Avisa sin esperar respuesta."""

    def confirm(self, question: Question) -> bool:
        """Aprobación explícita para las tres barreras de § 4.

        Vive en el puerto y no en cada adaptador **a propósito**: la
        semántica de seguridad debe ser idéntica por consola, por web y
        por Telegram. Un adaptador que la reimplemente se está saltando
        la garantía.
        """
        return self.ask(question).strip().lower() in _AFIRMACIONES
