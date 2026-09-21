"""Mechanism Designer (F3.15 (mecanismos)).

De la petición en texto a un `MechanismSpec`. Lo que se puede comprobar
sin geometría (fórmulas evaluables en todo el recorrido, requisitos
medibles) entra en el bucle de reintento de `structured`; lo que necesita
geometría (choques, contactos, piezas que no cuadran) vuelve en la ronda
siguiente como `rechazo`.
"""

from pathlib import Path

from mech_toolkit.profile import PrinterProfile
from orchestrator.llm.structured import LlmClient, structured
from orchestrator.mechanisms.checks import levantar_apoyadas, mechanism_problems
from orchestrator.mechanisms.kinematics import Kinematics
from orchestrator.schemas.mechanism import MechanismSpec
from orchestrator.schemas.recipe import GeneratorCatalog

PROMPT_PATH = Path("config/agents/mechanism_designer.md")


class MechanismDesignerAgent:
    def __init__(self, client: LlmClient, catalog: GeneratorCatalog, profile: PrinterProfile,
                 bed_mm: tuple[float, float, float], min_gap_mm: float,
                 wall_mm: float = 1.8,
                 prompt_path: Path = PROMPT_PATH,
                 reserva: LlmClient | None = None) -> None:
        self._client = client
        # Si el razonador se corta dos veces, contesta este: un modelo sin
        # pensamiento tiene todo `max_tokens` para el JSON (F3.15 (mecanismos)).
        self._reserva = reserva
        self._min_gap_mm = min_gap_mm
        self.ajustes: list[str] = []
        """Lo que el código arregló por su cuenta en la última propuesta."""
        self._instrucciones = prompt_path.read_text(encoding="utf-8").format(
            min_gap=f"{min_gap_mm:g}", bed=" × ".join(f"{v:g}" for v in bed_mm),
            profile_id=profile.id, clearance=f"{profile.fit_mm('clearance'):g}",
            slide=f"{profile.fit_mm('slide'):g}", press=f"{profile.fit_mm('press'):g}",
            wall=f"{wall_mm:g}",
            catalog=catalog.describe(),
        )

    def design(self, peticion: str, rechazo: tuple[str, str] | None = None,
               referencias=None) -> MechanismSpec:
        """`rechazo` = (especificación anterior, qué falló al construirla).
        `referencias` = imágenes y diseños que el usuario mandó como ejemplo
        de algo que ya funciona (F5.2 (adjuntos)); opcionales."""
        prompt = f"{self._instrucciones}\n## Petición del usuario\n\n{peticion}\n"
        if referencias:
            prompt += (
                "\n## Referencias que manda el usuario\n\n"
                "Son ejemplos de algo que YA FUNCIONA, o fotos y bocetos de lo que "
                "quiere. Apóyate en ellas: adaptar lo que funciona es mejor que "
                "inventar. Si contradicen la petición, manda la petición.\n")
            if referencias.imagenes:
                prompt += (f"\nTe adjunto {len(referencias.imagenes)} imagen(es). Mira cómo "
                           "son las piezas, cómo se apoyan unas en otras y dónde giran.\n")
            for titulo, contenido in referencias.textos:
                prompt += f"\n### {titulo}\n\n{contenido}\n"
        if rechazo is not None:
            anterior, motivo = rechazo
            prompt += (
                "\n## Tu diseño anterior NO funciona\n\n"
                f"Diseño:\n{anterior}\n\n"
                f"Lo que falló al construirlo y moverlo:\n{motivo}\n\n"
                "Corrígelo. Antes de tocar nada, PLANIFICA: rellena `fix_plan` con "
                "`causa` (por qué crees que falla), `cambio` (qué vas a cambiar, con "
                "números) y `espera` (qué debería medir el sistema si aciertas). Luego "
                "aplica ese cambio al diseño sin dejar de cumplir la petición.\n"
            )
        def comprobar(spec: MechanismSpec) -> None:
            if rechazo is not None and spec.fix_plan is None:
                raise ValueError(
                    "falta `fix_plan`: al corregir hay que decir la causa que supones, "
                    "qué cambias (con números) y qué esperas conseguir"
                )
            Kinematics(spec).validate()
            # Lo exacto lo arregla el código ANTES de juzgar: si no, cada
            # «súbelas 0.10 mm» costaba un intento entero del modelo.
            self.ajustes = levantar_apoyadas(spec, self._min_gap_mm)
            problemas = mechanism_problems(spec, self._min_gap_mm)
            if problemas:
                raise ValueError("; ".join(problemas))

        return structured(self._client, prompt, MechanismSpec, extra_validation=comprobar,
                          cliente_de_reserva=self._reserva,
                          imagenes=referencias.imagenes if referencias else None)
