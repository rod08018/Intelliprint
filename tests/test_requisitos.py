"""Requisitos estructurados (F3.17 (requisitos)).

Hasta ahora la petición viajaba como prosa, y las cotas se buscaban en la
receta con una expresión regular. Eso no deja medir nada —no se sabe qué
cota es un agujero y cuál un fondo— y las modificaciones se apilaban como
texto: Ø34 y Ø40 convivieron en el mismo prompt del sargento.

Cada requisito cita LITERALMENTE la petición, y el código comprueba dos
cosas que el modelo no puede saltarse: que la cita existe, y que ninguna
cota de la petición se queda sin requisito.
"""

import json

import pytest
from pydantic import ValidationError

from orchestrator.agents.requirements import RequirementsAgent
from orchestrator.schemas.spec import Requisito, Spec, errores_de_requisitos
from orchestrator.tasks import spec_to_task
from orchestrator.traceability import requested_dimensions

REPISA = ("Escuadra para una repisa de madera de 200 mm de fondo que tiene que aguantar "
          "5 kg de libros. Se atornilla a la pared con 2 tornillos de 4 mm (agujeros de "
          "4.5 mm separados 60 mm).")

REQUISITOS = [
    {"id": "R1", "tipo": "cota", "texto": "repisa de madera de 200 mm de fondo",
     "valor": 200, "origen": "usuario"},
    {"id": "R2", "tipo": "carga", "texto": "aguantar 5 kg de libros",
     "valor": 5, "unidad": "kg", "origen": "usuario"},
    {"id": "R3", "tipo": "agujero", "texto": "agujeros de 4.5 mm", "valor": 4.5,
     "origen": "usuario"},
    {"id": "R4", "tipo": "cota", "texto": "separados 60 mm", "valor": 60,
     "origen": "usuario"},
]


def _spec(requisitos=REQUISITOS, **extra) -> dict:
    return {"title": "escuadra de repisa", "description": "aguanta una repisa",
            "product_class": "static_part", "printer": "ankermake_m5_plamas",
            "material": "PLA+", "requisitos": requisitos, **extra}


class Guion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.prompts = []

    def complete(self, prompt, **_):
        self.prompts.append(prompt)
        return self._respuestas.pop(0)


# --- la medida de un tornillo no es una cota de la pieza ---------------------

def test_el_tamano_de_un_tornillo_no_es_una_cota_de_la_pieza():
    """Falso positivo real del banco (2026-11-03): «2 tornillos de 4 mm»
    hacía exigir un 4 en la receta, cuando lo que lleva la pieza es el
    agujero de 4.5 para ese tornillo."""
    assert sorted(requested_dimensions(REPISA)) == [4.5, 60, 200]


def test_un_agujero_para_un_tornillo_si_es_una_cota():
    """Solo se descarta el número que ES el tornillo, no el que va con él."""
    assert requested_dimensions("agujeros de 5.5 mm para tornillos M5") == [5.5]
    assert requested_dimensions("dos tornillos de 3 mm y una placa de 3 mm") == [3]


# --- el esquema ---------------------------------------------------------------

def test_dos_requisitos_no_pueden_tener_el_mismo_id():
    """El id es por donde una modificación reemplaza un requisito: repetido,
    no se sabría cuál cambiar."""
    duplicados = [REQUISITOS[0], {**REQUISITOS[2], "id": "R1"}]
    with pytest.raises(ValidationError, match="R1"):
        Spec(**_spec(duplicados))


def test_una_cita_del_usuario_tiene_que_estar_en_la_peticion():
    inventado = Requisito(id="R9", tipo="cota", texto="ala de 80 mm", valor=80,
                          origen="usuario")
    errores = errores_de_requisitos([*map(Requisito.model_validate, REQUISITOS), inventado],
                                    REPISA)
    assert any("R9" in e and "ala de 80 mm" in e for e in errores)


def test_la_cita_ignora_mayusculas_y_saltos_de_linea():
    """Las peticiones del banco vienen de YAML plegado: los saltos de línea
    caen donde caen."""
    peticion = "Escuadra para una repisa de madera de 200 mm\nde fondo"
    r = Requisito(id="R1", tipo="cota", texto="repisa de madera de 200 mm de fondo",
                  valor=200, origen="usuario")
    assert errores_de_requisitos([r], peticion) == []


def test_una_estimacion_no_necesita_cita():
    r = Requisito(id="R5", tipo="cota", texto="ala de pared de 80 mm para que quepan "
                  "los dos agujeros", valor=80, origen="estimado")
    assert errores_de_requisitos([*map(Requisito.model_validate, REQUISITOS), r], REPISA) == []


def test_ninguna_cota_de_la_peticion_se_queda_sin_requisito():
    sin_separacion = [r for r in REQUISITOS if r["id"] != "R4"]
    errores = errores_de_requisitos(list(map(Requisito.model_validate, sin_separacion)), REPISA)
    assert any("60 mm" in e for e in errores)


# --- el agente ------------------------------------------------------------------

def test_el_agente_corrige_una_cota_olvidada_con_el_error_exacto():
    sin_separacion = [r for r in REQUISITOS if r["id"] != "R4"]
    guion = Guion([json.dumps(_spec(sin_separacion)), json.dumps(_spec())])

    spec = RequirementsAgent(guion).draft(REPISA)

    assert [r.id for r in spec.requisitos] == ["R1", "R2", "R3", "R4"]
    assert "60 mm" in guion.prompts[1]


def test_el_enunciado_del_disenador_lleva_cada_requisito_con_su_id():
    """Con id, el revisor y la medida (F6) pueden decir «R3 no se cumple»."""
    spec = Spec(**_spec(), request=REPISA)
    brief = spec_to_task(spec).brief
    assert "R3" in brief and "agujeros de 4.5 mm" in brief


def test_una_separacion_de_agujeros_cubre_su_cota():
    """F6.7 (lazo): «separados 60 mm» puede ir dentro del requisito del
    agujero, que es donde se mide; no hace falta repetirlo como cota."""
    agujeros = Requisito(id="R3", tipo="agujero", texto="agujeros de 4.5 mm", valor=4.5,
                         origen="usuario", cantidad=2, separaciones_mm=[60])
    resto = [Requisito.model_validate(r) for r in REQUISITOS if r["id"] in ("R1", "R2")]
    assert errores_de_requisitos([*resto, agujeros], REPISA) == []


# --- lo que el sistema escribe en la petición de una pieza no es un requisito ------------------

DE_UN_BACKLOG = "\n".join([
    "Brazo superior: Va del hombro al codo; la distancia entre ejes es 150 mm.",
    "",
    "Lo que sigue es de dónde va esta pieza, no medidas suyas:",
    "",
    "Es una de las piezas de «Brazo de cuatro ejes», que se diseñan una a una: aquí solo "
    "se diseña esta.",
    "",
    "Se une a estas piezas, ya terminadas. Tienen ficha con su forma construida y sus "
    "agujeros con nombre: colócalas con `kit.componente` y atorníllate a sus agujeros con "
    "`punto()`:",
    "- Torreta de giro: ficha obra-torreta (Gira 180° sobre la base.)",
    ""])
"""La petición del brazo superior del banco 1113-1330, resumida."""

SUYO = {"id": "R1", "tipo": "cota", "texto": "la distancia entre ejes es 150 mm", "valor": 150,
        "origen": "usuario"}
DEL_SISTEMA = {"id": "R4", "tipo": "fijacion", "origen": "usuario", "texto": (
    "Se une a estas piezas, ya terminadas... colócalas con `kit.componente` y atorníllate "
    "a sus agujeros con `punto()`")}
"""Tal cual lo escribió el modelo al reanudar la 1113-1330: lo que el sistema
le cuenta a la pieza, con unos puntos suspensivos en medio."""


def test_un_requisito_sacado_de_lo_que_escribe_el_sistema_no_tumba_la_pieza():
    """Al reanudar la 1113-1330 el brazo superior no pasó de los requisitos,
    tres veces, por R4: «dice venir del usuario, pero … no está en la
    petición». No lo dijo el usuario ni es un requisito: es la instrucción
    del sistema, abreviada. No es un error; se quita."""
    from orchestrator.schemas.spec import errores_de_requisitos, sin_lo_del_sistema
    requisitos = [Requisito(**SUYO), Requisito(**DEL_SISTEMA)]
    assert errores_de_requisitos(requisitos, DE_UN_BACKLOG) == []
    assert [r.id for r in sin_lo_del_sistema(requisitos, DE_UN_BACKLOG)] == ["R1"]


def test_una_cita_inventada_sigue_siendo_un_error_aunque_haya_contexto():
    from orchestrator.schemas.spec import errores_de_requisitos, sin_lo_del_sistema
    inventado = Requisito(id="R2", tipo="carga", origen="usuario",
                          texto="aguanta 2 kg en la punta... sin flexar")
    [error] = errores_de_requisitos([Requisito(**SUYO), inventado], DE_UN_BACKLOG)
    assert "R2" in error and "no está en la petición" in error
    assert len(sin_lo_del_sistema([Requisito(**SUYO), inventado], DE_UN_BACKLOG)) == 2


def test_el_agente_de_requisitos_entrega_la_spec_sin_lo_del_sistema():
    spec = RequirementsAgent(Guion([json.dumps(_spec([SUYO, DEL_SISTEMA]))])).draft(DE_UN_BACKLOG)
    assert [r.id for r in spec.requisitos] == ["R1"]


DE_UNA_CARCASA = "\n".join([
    "Carcasa abombada: Tapa abombada de pared fina que cubre el cuerpo del NEMA 17, se "
    "atornilla al soporte con cuatro tornillos M3 y deja salir el cable. Se imprime sin "
    "soportes..",
    "",
    "Lo que sigue es de dónde va esta pieza, no medidas suyas:",
    "",
    "- Soporte escuadra: ficha obra-soporte (Escuadra que aloja el NEMA 17.)",
    "  El hueco de tu carcasa tiene que llegar, como poco, a: x de -22.15 a 22.15, y de 25.85 "
    "a 70.15, z de -40.5 a 1: es el mayor de sus cuerpos con la holgura. Los demás, o quedan "
    "dentro con su holgura o les abres paso.",
    ""])
"""La petición de la carcasa del banco 1114-0535, resumida."""


def test_una_cita_literal_de_lo_que_escribe_el_sistema_tampoco_es_un_requisito():
    """Encargo 16, corrida 1114-0535: a la carcasa se le dio al inicio dónde
    está el motor, y el modelo hizo de esa frase, citada al pie de la letra,
    un requisito «del usuario» de tipo encaje con sección 44.3 × 44.3. Al
    construir volvió «ninguna abertura pasante deja pasar 44.3 × 44.3»: una
    ventana que nadie pidió. Lo que va detrás del aviso no lo dijo el
    usuario, se cite entero o abreviado."""
    from orchestrator.schemas.spec import errores_de_requisitos, sin_lo_del_sistema
    suyo = Requisito(id="R2", tipo="fijacion", origen="usuario", valor=3.0, cantidad=4,
                     texto="se atornilla al soporte con cuatro tornillos M3")
    del_sistema = Requisito(id="R5", tipo="encaje", origen="usuario", seccion_mm=[44.3, 44.3],
                            texto=("El hueco de tu carcasa tiene que llegar, como poco, a: x de "
                                   "-22.15 a 22.15, y de 25.85 a 70.15, z de -40.5 a 1: es el "
                                   "mayor de sus cuerpos con la holgura."))
    assert errores_de_requisitos([suyo, del_sistema], DE_UNA_CARCASA) == []
    assert [r.id for r in sin_lo_del_sistema([suyo, del_sistema], DE_UNA_CARCASA)] == ["R2"]
