"""Requirements Agent (F1.4 (requirements)). Ver SISTEMA_MULTIAGENTE.md § 4.1 y § 4.2.

Es el único agente que corre antes de tu confirmación, y el que decide
la clase de producto — que a su vez decide qué agentes correrán después
(ADR-010).
"""

from pathlib import Path

from orchestrator.llm.structured import LlmClient, structured
from orchestrator.schemas.spec import Spec, errores_de_requisitos

PROMPT_PATH = Path("config/agents/requirements.md")


def _citas_y_cotas(spec: Spec, peticion: str, externos: str = "") -> None:
    """Dentro del bucle de reintento: el modelo recibe el error exacto
    («la petición dice 60 mm y ningún requisito lleva ese valor») y lo
    corrige, en vez de que el fallo aparezca después, al medir."""
    errores = errores_de_requisitos(spec.requisitos, peticion, externos)
    if errores:
        raise ValueError("requisitos incompletos:\n- " + "\n- ".join(errores))


class RequirementsAgent:
    def __init__(self, client: LlmClient, prompt_path: Path = PROMPT_PATH, activo=None) -> None:
        """`activo`: el perfil activo (`orchestrator.impresion`). Sus valores
        por defecto van al prompt desde el código: escritos en el texto, se
        quedaron en PETG cuando el usuario pasó a PLA+ (2026-10-24)."""
        self._client = client
        self._instrucciones = prompt_path.read_text(encoding="utf-8")
        if activo is not None:
            self._instrucciones += (
                f"\n\n## Perfil activo\n\n- printer: `{activo.impresora.id}`\n"
                f"- material: `{activo.material}`\n")

    def draft(self, peticion: str, adjuntos: list[str] | None = None,
              externos: str = "") -> Spec:
        """Redacta la spec a partir de la petición.

        Si el modelo clasifica como `robot` u omite un dato obligatorio de
        la clase, el esquema lo rechaza y `structured` le devuelve el error
        exacto para que lo corrija (ADR-010 + F1.3 (estructurada)). La coherencia entre
        clase y datos no depende del prompt: la impone el esquema.
        """
        partes = [self._instrucciones, "\n## Petición\n", peticion]
        if adjuntos:
            partes.append("\n\n## Adjuntos\n")
            partes.extend(f"- {a}\n" for a in adjuntos)
        if externos:
            # F3.21 (investigar): lo que la petición no decía y se buscó. Cada
            # cota es un requisito más, con `origen: catalogo`: no lo dijo
            # el usuario, y quien aprueba el concepto ve de dónde sale.
            partes.append("\n\n## Datos buscados en internet\n\nNo los dijo el usuario: "
                          "cada cota es un requisito con `origen: catalogo`, y su `texto` "
                          "dice de dónde sale.\n\n" + externos)
        spec = structured(self._client, "".join(partes), Spec,
                          extra_validation=lambda s: _citas_y_cotas(s, peticion, externos))
        # La petición literal la fija el código después de la llamada: el
        # modelo no puede perderla ni reescribirla al resumir.
        return spec.model_copy(update={"request": peticion})
