"""Bucle de error, segundo nivel (F1.11 (bucle)).

Primer nivel: receta inválida → error de esquema, sin lanzar FreeCAD.
Segundo nivel: receta VÁLIDA que FreeCAD rechaza al construir → el motivo
vuelve al diseñador para que la corrija. Máximo 3 construcciones.

El diseñador de estos tests lleva las recetas escritas: lo que se prueba es
el bucle —qué construye, qué le devuelve y cuándo se rinde—, no un agente.
"""

import json

import pytest

from mech_toolkit.generators import CATALOGO
from orchestrator.build import ConstruccionFallida, design_and_build, motivo_del_fallo
from orchestrator.schemas.recipe import Recipe
from tests.test_generators import _freecadcmd


class DisenadorGuionizado:
    """`rechazos`: lo que el bucle le devolvió en cada llamada, (su receta
    anterior, el motivo), o None la primera vez."""

    def __init__(self, recetas):
        self._r = [Recipe.model_validate_json(r) for r in recetas]
        self.rechazos = []

    def design(self, tarea, rechazo=None):
        self.rechazos.append(rechazo)
        return self._r.pop(0)


def _receta(diametro: float) -> str:
    return json.dumps(
        {
            "part": "placa",
            "steps": [
                {"generator": "generate_plate",
                 "params": {"length_mm": 60, "width_mm": 60, "thickness_mm": 6}},
                {"generator": "generate_center_bore",
                 "params": {"diameter_mm": diametro}},
            ],
        }
    )


def test_extrae_el_motivo_marcado_de_entre_el_ruido_de_freecad():
    salida = (
        "FreeCAD 1.1.3\nRecompute......\nTraceback (most recent call last):\n"
        '  File "build.py", line 40\n'
        "RuntimeError: INTELLIPRINT_FALLO: la pieza salió en 4 sólidos separados; "
        "debería ser una sola\n"
    )
    assert motivo_del_fallo(salida) == (
        "la pieza salió en 4 sólidos separados; debería ser una sola"
    )


def test_sin_motivo_marcado_devuelve_el_final_del_traceback():
    """Un error de FreeCAD que no provocamos nosotros también tiene que
    llegarle al agente, aunque sea en crudo."""
    salida = "Traceback (most recent call last):\nNameError: name 'x' is not defined\n"
    assert "NameError" in motivo_del_fallo(salida)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_receta_que_parte_la_pieza_se_corrige_con_el_motivo(tmp_path):
    """Taladro Ø70 en placa de 60: válida como receta, rota como pieza.
    El agente recibe "4 sólidos" y en el segundo intento pide Ø22."""
    agente = DisenadorGuionizado([_receta(70), _receta(22)])

    receta, resultado = design_and_build(
        agente, "placa con taladro", CATALOGO, tmp_path, freecadcmd=_freecadcmd()
    )

    assert resultado.solids == 1
    assert receta.steps[1].params["diameter_mm"] == 22
    assert agente.rechazos[0] is None
    anterior, motivo = agente.rechazos[1]
    assert "4 sólidos" in motivo
    assert '"diameter_mm": 70' in anterior  # ve su propia receta


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_cada_construccion_fallida_queda_guardada_con_su_motivo(tmp_path):
    """Banco 1110-0128: la polea del 608ZZ falló cuatro construcciones y solo
    quedó la última; por qué no colocó el soporte hubo que reproducirlo a
    mano. Cada intento queda en `intentos/<n>/`, con lo que escribió y el
    porqué."""
    design_and_build(DisenadorGuionizado([_receta(70), _receta(22)]), "placa con taladro",
                     CATALOGO, tmp_path, freecadcmd=_freecadcmd())
    assert "4 sólidos" in (tmp_path / "intentos" / "1" / "motivo.md").read_text(encoding="utf-8")
    assert '"diameter_mm": 70' in (tmp_path / "intentos" / "1" / "programa.txt").read_text(
        encoding="utf-8")
    assert not (tmp_path / "intentos" / "2").exists()   # el segundo salió


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_tres_construcciones_fallidas_se_rinden_con_el_ultimo_motivo(tmp_path):
    agente = DisenadorGuionizado([_receta(70)] * 3)

    with pytest.raises(ConstruccionFallida, match="4 sólidos"):
        design_and_build(
            agente, "placa", CATALOGO, tmp_path, freecadcmd=_freecadcmd()
        )
    assert len(agente.rechazos) == 3


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_la_construccion_informa_de_donde_queda_la_pieza(tmp_path):
    """El tamaño no basta para ensamblar: una placa de 60 mm centrada en el
    origen y otra que empieza en el origen miden lo mismo."""
    from orchestrator.build import build_part

    r = build_part(Recipe.model_validate_json(_receta(8)), CATALOGO, tmp_path, _freecadcmd())
    assert r.bbox_min == pytest.approx([-30, -30, 0], abs=1e-6)
    assert r.bbox_max == pytest.approx([30, 30, 6], abs=1e-6)


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_comprobacion_fallida_tras_construir_vuelve_al_agente(tmp_path):
    """Una pieza construible pero mal colocada es un rechazo más: su motivo
    llega al agente igual que un fallo de FreeCAD."""
    agente = DisenadorGuionizado([_receta(8), _receta(10)])

    def comprobar(resultado):
        return None if resultado.volume_mm3 < 60 * 60 * 6 - 400 else "el taladro central tiene que ser mayor"

    _, resultado = design_and_build(
        agente, "placa", CATALOGO, tmp_path, freecadcmd=_freecadcmd(), check=comprobar)
    assert len(agente.rechazos) == 2
    assert "el taladro central tiene que ser mayor" in agente.rechazos[1][1]
    assert resultado.volume_mm3 < 60 * 60 * 6 - 400


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_una_caja_que_no_cuadra_no_quema_los_tres_intentos(tmp_path):
    """4 rondas del trinquete se fueron así: la pieza estaba bien dibujada y
    era la caja DECLARADA la que no cuadraba, pero se le pedía al diseñador
    de la pieza que arreglara un desacuerdo que no era suyo."""
    agente = DisenadorGuionizado([_receta(8)] * 3)

    with pytest.raises(ConstruccionFallida, match="caja"):
        design_and_build(agente, "placa", CATALOGO, tmp_path, freecadcmd=_freecadcmd(),
                         check=lambda r: "la pieza ocupa x de -30 a 30; se necesita de 0 a 60",
                         check_es_de_la_caja=True)

    assert len(agente.rechazos) == 2      # un intento y una corrección, no tres


@pytest.mark.skipif(_freecadcmd() is None, reason="freecadcmd no disponible")
def test_un_retoque_llega_al_disenador_en_cada_intento(tmp_path):
    """El programa construido y el cambio pedido van en TODOS los intentos:
    si el primero no cuadra, el segundo sigue siendo un retoque de la pieza
    que había, no una pieza nueva (base del pan-tilt, 2026-11-09)."""
    from orchestrator.schemas.programa import Programa
    from tests.test_sondas import PERFIL

    class Disenador:
        llamadas = []

        def design(self, tarea, rechazo=None, partida=None):
            self.llamadas.append((rechazo, partida))
            return Programa(part="p", codigo="def construir(kit):\n    return kit.caja(20, 10, 5)\n")

    agente = Disenador()
    design_and_build(agente, "t", None, tmp_path, freecadcmd=_freecadcmd(), perfil=PERFIL,
                     partida=("CODIGO", "la tuerca más adentro"),
                     check=lambda r: "falla" if len(agente.llamadas) < 2 else None)
    assert [p for _, p in agente.llamadas] == [("CODIGO", "la tuerca más adentro")] * 2
    assert agente.llamadas[1][0][1] == "falla"
