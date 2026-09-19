"""Adaptador de consola del HumanPort.

Ver SISTEMA_MULTIAGENTE.md § 8.5 y DECISIONES.md ADR-006.
"""

import io

from orchestrator.human.adapters.cli import CliAdapter
from orchestrator.human.port import Question


def _adaptador(respuestas: str) -> tuple[CliAdapter, io.StringIO]:
    salida = io.StringIO()
    return CliAdapter(entrada=io.StringIO(respuestas), salida=salida), salida


def test_ask_muestra_la_pregunta_y_devuelve_lo_que_escribes():
    adaptador, salida = _adaptador("PETG\n")

    respuesta = adaptador.ask(Question(text="¿PLA o PETG?"))

    assert respuesta == "PETG"
    assert "¿PLA o PETG?" in salida.getvalue()


def test_ask_lista_los_adjuntos_que_te_esta_enseñando():
    """Por consola no se ven las imágenes, pero tienes que saber que existen.

    El mismo `Question` viaja por Telegram, donde sí se muestran (§ 8.5).
    """
    adaptador, salida = _adaptador("sí\n")

    adaptador.ask(
        Question(
            text="¿es esta la pieza?",
            attachments=["parts/dedo_der/views/iso.png"],
        )
    )

    assert "iso.png" in salida.getvalue()


def test_una_respuesta_vacia_no_aprueba():
    """Darle a Enter sin leer no es aprobar.

    `confirm()` alimenta el `approved=True` de las tres barreras de § 4.
    Si el silencio aprobara, la barrera de admisión y los dos gates
    dejarían de existir en la práctica.
    """
    adaptador, _ = _adaptador("\n")

    assert adaptador.confirm(Question(text="¿arranco el diseño?")) is False


def test_solo_un_si_explicito_aprueba():
    """Lista blanca corta. Cualquier otra cosa es un no.

    Deliberadamente NO se interpreta lenguaje natural: en una barrera de
    seguridad, "no entiendo" tiene que significar "no".
    """
    for respuesta in ["sí", "si", "s", "y", "yes", "SÍ", "  si  "]:
        adaptador, _ = _adaptador(respuesta + "\n")
        assert adaptador.confirm(Question(text="¿arranco?")) is True, respuesta

    for respuesta in ["no", "n", "espera", "luego lo miro", "?", "sip"]:
        adaptador, _ = _adaptador(respuesta + "\n")
        assert adaptador.confirm(Question(text="¿arranco?")) is False, respuesta
