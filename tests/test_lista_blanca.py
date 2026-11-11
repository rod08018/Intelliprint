"""La lista blanca del canal de Telegram (F5.10 (lista)): OPCIONAL.

Decisión del usuario (2026-09-21): el canal va ABIERTO. La lista se había
hecho obligatoria sin que él lo aprobara, al leer su «haz todo» como que
incluía esta tarea de la tabla de deuda. Queda como opción: vacía, Crafty
atiende a cualquiera; con ids, solo a ellos.

Un bot de Telegram NO es local aunque corra en el PC: hace sondeo contra
los servidores de Telegram, que le entregan los mensajes de cualquiera que
lo encuentre. Con el canal abierto, un desconocido puede lanzar proyectos,
gastar el saldo de DeepSeek y contestar las barreras del sistema.

Aquí solo se prueba cómo se LEE la lista. Lo que Crafty hace con ella (a
quién atiende, y que un grupo no lo abre a sus miembros) está en
test_crafty_docker.py.
"""

import pytest

from orchestrator.crafty import ListaBlancaInvalida, leer_lista_blanca


def test_la_lista_se_lee_separada_por_comas():
    assert leer_lista_blanca("111, 222,333") == frozenset({111, 222, 333})


def test_sin_lista_el_canal_esta_abierto():
    """Vacía significa «sin lista»: el canal atiende a cualquiera."""
    for vacia in ("", "   ", None, " , "):
        assert leer_lista_blanca(vacia) is None


def test_un_nombre_de_usuario_no_vale_como_id():
    """@alias se puede cambiar y lo puede coger otro. El id numérico no."""
    with pytest.raises(ListaBlancaInvalida, match="@jdr"):
        leer_lista_blanca("111,@jdr")
