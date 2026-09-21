"""El solucionador alarga él mismo la búsqueda de un apoyo cuando la pieza
seguía acercándose al acabarse el recorrido (F3.15 (mecanismos)).

Fallo real, el trinquete del 2026-09-21. En las rondas 13, 14 y 15 la uña
de retención «no llegaba a apoyarse» por 0.15, 0.06 y 0.18 mm, y el punto
más cercano caía SIEMPRE en el final del recorrido de búsqueda: -20, -25,
-30. La uña seguía acercándose cuando la búsqueda se paraba. El modelo la
alargaba 5° por ronda, la rueda —que ya giraba empujada— se le escapaba, y
cada persecución costaba una ronda. Alargar la búsqueda no es diseño: es un
parámetro del solucionador, y lo hace el código.

La medición de FreeCAD se sustituye por una función de hueco escrita a mano:
es el oráculo, y así el test no depende de FreeCAD.
"""

import pytest

import orchestrator.mechanisms.contact as contacto
from orchestrator.mechanisms.contact import SinApoyo, solve_contacts
from orchestrator.schemas.mechanism import MechanismSpec


def _spec(start="20", toward="decrease", limit=40):
    return MechanismSpec(**{
        "title": "t", "summary": "s", "driver": {"start": 0, "end": 10, "step": 10},
        "parts": [
            {"name": "base", "brief": "b", "bbox_min": [-50, -50, -5], "bbox_max": [50, 50, 0]},
            {"name": "rueda", "brief": "b", "bbox_min": [-20, -20, 0], "bbox_max": [20, 20, 6]},
            {"name": "una", "origin": [30, 0, 0], "brief": "b",
             "bbox_min": [-6, -6, 0], "bbox_max": [20, 6, 6],
             "joint": {"type": "revolute", "axis": [0, 0, 1],
                       "rest_on": {"target": "rueda", "start": start, "toward": toward,
                                   "limit": limit}}},
        ],
    })


class _Kin:
    def __init__(self, inicio):
        self.inicio = inicio

    def joint_value(self, nombre, t):
        return self.inicio

    def set_solved(self, resueltos):
        pass


@pytest.fixture
def hueco(monkeypatch):
    """Instala la función hueco(valor) -> mm como si fuera FreeCAD."""
    def instalar(funcion):
        def medir(kin, nombre, valores_por_frame, steps, pins, objetivo, freecadcmd):
            return {t: [(v, funcion(v)) for v in vs] for t, vs in valores_por_frame.items()}
        monkeypatch.setattr(contacto, "_medir", medir)
    return instalar


def test_si_seguia_acercandose_al_final_el_codigo_alarga_la_busqueda(hueco):
    # Se apoya en -35: más allá del final de la búsqueda (20 - 40 = -20).
    hueco(lambda v: (v + 35) * 0.02)
    notas = []
    resuelto = solve_contacts(_spec(), _Kin(20.0), {}, {}, "fc", [0.0], notas=notas)

    valor = resuelto[(0.0, "una")]
    assert 0 <= (valor + 35) * 0.02 <= 0.05          # dentro de la banda de contacto
    # Y lo deja dicho: el diseño no cambió, pero la búsqueda sí.
    assert notas and "una" in notas[0] and "alargó" in notas[0]


def test_si_lo_mas_cerca_esta_en_medio_le_falta_pieza_y_vuelve_al_modelo(hueco):
    """Pasa a 0.15 mm en la mitad del recorrido y luego se aleja: no toca en
    ninguna parte. Eso es geometría, y la decide el diseñador."""
    hueco(lambda v: 0.15 + (v / 100) ** 2)
    with pytest.raises(SinApoyo, match="0.15 mm"):
        solve_contacts(_spec(), _Kin(20.0), {}, {}, "fc", [0.0], notas=[])


def test_si_se_aleja_desde_el_principio_el_motivo_sugiere_el_otro_sentido(hueco):
    hueco(lambda v: 0.2 + (20 - v) * 0.01)      # cuanto más baja, más lejos
    with pytest.raises(SinApoyo, match="toward"):
        solve_contacts(_spec(), _Kin(20.0), {}, {}, "fc", [0.0], notas=[])


def test_alargar_tiene_un_limite_y_no_busca_para_siempre(hueco):
    """Una pieza que se acerca tan despacio que nunca llega no puede tener
    al solucionador girando vueltas y vueltas."""
    hueco(lambda v: 1.0 + (v + 1000) * 1e-4)     # baja, pero nunca a la banda
    with pytest.raises(SinApoyo):
        solve_contacts(_spec(), _Kin(20.0), {}, {}, "fc", [0.0], notas=[])
