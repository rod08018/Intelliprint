"""Una pieza suelta desde la web o Telegram (F5.17 (pieza)), sin FreeCAD.

Antes solo se podían pedir mecanismos, que exigen dos piezas: un soporte o
un gancho no tenían por dónde entrar. Lo que se prueba aquí es que el
proyecto de una pieza deja en su carpeta lo que leen el registro, la web
y el canal, salga o no salga.
"""

import json

from orchestrator.build import ConstruccionFallida
from orchestrator.pieza import aprobar_concepto, concebir_pieza, disenar_pieza
from orchestrator.registry import estado_de
from orchestrator.schemas.part_result import PartResult
from orchestrator.schemas.recipe import Recipe
from orchestrator.schemas.slicing_report import SlicingReport
from orchestrator.schemas.concepto import Concepto, ConceptoComprobado
from orchestrator.schemas.spec import Spec

PETICION = "gancho de pared con dos agujeros de 4.5 mm separados 40 mm"


class Requisitos:
    def draft(self, peticion):
        return Spec(title="Gancho de pared", description="d", request=peticion,
                    product_class="static_part", printer="m5", material="PLA+")


def _disenar(untraced=(), defectos=()):
    def disenar(spec, carpeta, parte, concepto=None):
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / f"{parte}.stl").write_text("solid", encoding="utf-8")
        receta = Recipe(part=parte, steps=[{"generator": "generate_box", "params": {
            "length_mm": 60, "width_mm": 50, "height_mm": 10}}])
        return receta, PartResult(part=parte, volume_mm3=1234.0, bbox_mm=[60, 50, 10],
                                  solids=1, untraced_mm=list(untraced),
                                  defectos=list(defectos))
    return disenar


def _laminar(stl, gcode):
    return SlicingReport(plate=1, filament_mm=1000, grams=3.0, time_s=600,
                         needs_supports=False)


def test_una_pieza_que_sale_queda_aprobada_en_el_registro_con_su_titulo(tmp_path):
    informe = disenar_pieza(PETICION, tmp_path, requisitos=Requisitos(),
                            disenar=_disenar(), laminar=_laminar, log=lambda *_: None)

    assert informe.resuelto and informe.gramos == 3.0
    assert (tmp_path / "request.md").read_text(encoding="utf-8").strip() == PETICION
    assert json.loads((tmp_path / "fabrication" / "slicing_report.json").read_text())["grams"] == 3
    fila = estado_de(tmp_path)
    assert fila["estado"] == "aprobado"
    assert fila["titulo"] == "Gancho de pared"


def test_una_pieza_que_no_se_construye_deja_el_porque(tmp_path):
    def falla(spec, carpeta, parte, concepto=None):
        raise ConstruccionFallida("3 construcciones fallidas. Último motivo: sólido partido")

    informe = disenar_pieza(PETICION, tmp_path, requisitos=Requisitos(), disenar=falla,
                            laminar=_laminar, log=lambda *_: None)

    assert not informe.resuelto
    assert "sólido partido" in (tmp_path / "blocked.md").read_text(encoding="utf-8")
    assert estado_de(tmp_path)["estado"] == "fallido"


def test_una_cota_pedida_que_no_esta_en_la_pieza_no_sale_aprobada(tmp_path):
    """La trazabilidad solo avisaba al pie del informe por consola; desde la
    web nadie lo veía y la pieza salía como buena."""
    informe = disenar_pieza(PETICION, tmp_path, requisitos=Requisitos(),
                            disenar=_disenar(untraced=[40.0]), laminar=_laminar,
                            log=lambda *_: None)

    assert not informe.resuelto
    assert "40 mm" in informe.motivo
    assert estado_de(tmp_path)["estado"] == "fallido"


def test_un_laminado_que_falla_no_pierde_la_pieza_construida(tmp_path):
    """El 2026-11-05 el puente del host no encontró el STL y la excepción
    tumbó el proceso: nueve piezas construidas quedaron sin informe y el
    banco las contó como no hechas. La pieza existe; lo que falta es su
    laminado, y eso se dice."""
    from orchestrator.slicing import LaminadoFallido

    def revienta(stl, gcode):
        raise LaminadoFallido("no encuentro el STL")

    informe = disenar_pieza(PETICION, tmp_path, requisitos=Requisitos(),
                            disenar=_disenar(), laminar=revienta, log=lambda *_: None)

    assert informe.volumen_mm3 == 1234.0 and informe.gramos is None
    assert not informe.resuelto and "no encuentro el STL" in informe.motivo
    assert json.loads((tmp_path / "pieza_report.json").read_text())["volumen_mm3"] == 1234.0


def test_sin_laminador_la_pieza_sale_igual(tmp_path):
    informe = disenar_pieza(PETICION, tmp_path, requisitos=Requisitos(),
                            disenar=_disenar(), laminar=None, log=lambda *_: None)
    assert informe.resuelto and informe.gramos is None


# --- la puerta del concepto (F3.20 (concepto)) ------------------------------------

def _nada(*_):
    pass


class Ingeniero:
    def concebir(self, spec):
        return ConceptoComprobado(concepto=Concepto(
            idea="gancho en J con un nervio en la espalda", camino_de_carga="c",
            orientacion="de lado sobre la cama", preguntas=["¿cuánto pesa la mochila?"]))


def test_la_pieza_espera_el_visto_bueno_del_concepto_antes_de_modelar(tmp_path):
    """Modelar cuesta dinero y tiempo: si la idea no es la que quieres, se
    dice ANTES. Hasta ahora lo primero que veías era la pieza hecha."""
    concebir_pieza(PETICION, tmp_path, requisitos=Requisitos(), ingeniero=Ingeniero(),
                   log=_nada)

    fila = estado_de(tmp_path)
    assert fila["estado"] == "por aprobar"
    assert "concepto.md" in fila["archivos"]
    texto = (tmp_path / "concepto.md").read_text(encoding="utf-8")
    assert "gancho en J" in texto and "¿cuánto pesa la mochila?" in texto
    assert not (tmp_path / "parts").exists()


def test_el_concepto_se_juzga_y_el_veredicto_queda_en_la_carpeta(tmp_path):
    """El juez lee lo mismo que la persona: el concepto ya redactado."""
    leido = []

    def juez(texto):
        leido.append(texto)
        return {"suelto": 0.9}

    concebir_pieza(PETICION, tmp_path, requisitos=Requisitos(), ingeniero=Ingeniero(),
                   juez=juez, log=_nada)

    assert "gancho en J" in leido[0]
    assert json.loads((tmp_path / "juez.json").read_text(encoding="utf-8")) == {"suelto": 0.9}


def test_un_concepto_nuevo_no_hereda_el_juicio_del_anterior(tmp_path):
    (tmp_path / "juez.json").write_text('{"suelto": 0.9}', encoding="utf-8")
    concebir_pieza(PETICION, tmp_path, requisitos=Requisitos(), ingeniero=Ingeniero(),
                   juez=lambda texto: None, log=_nada)
    assert not (tmp_path / "juez.json").exists()


def test_aprobado_se_modela_ese_concepto_sin_volver_a_redactar_nada(tmp_path):
    """Lo que se aprobó es lo que se dibuja: redactar otra vez la spec
    podría dar otra distinta de la que viste."""
    concebir_pieza(PETICION, tmp_path, requisitos=Requisitos(), ingeniero=Ingeniero(),
                   log=_nada)
    aprobar_concepto(tmp_path, por="web")
    recibido = {}

    def disenar(spec, carpeta, parte, concepto=None):
        recibido["concepto"] = concepto
        return _disenar()(spec, carpeta, parte)

    class NoRedactes:
        def draft(self, peticion):
            raise AssertionError("ya había una especificación aprobada")

    informe = disenar_pieza(PETICION, tmp_path, requisitos=NoRedactes(), disenar=disenar,
                            laminar=_laminar, log=_nada)

    assert informe.resuelto
    assert recibido["concepto"].concepto.idea.startswith("gancho en J")
    assert estado_de(tmp_path)["estado"] == "aprobado"


def test_un_concepto_nuevo_parte_del_anterior_y_de_los_cambios(tmp_path):
    """La base del pan-tilt (2026-11-09): cada vuelta el ingeniero partía de
    cero y decidía otra vez lo que nadie había pedido. Con un concepto
    anterior en la carpeta, lo recibe junto con los cambios; y los cambios no
    pasan por el agente de requisitos, que leyó la descripción de un defecto
    («un bloque de unos 8 mm») como una cota que cumplir."""
    anterior = ConceptoComprobado(concepto=Concepto(
        idea="gancho en J", camino_de_carga="c", orientacion="o",
        fijaciones=["2 tornillos M4 a la pared"]))
    (tmp_path / "concepto_anterior.json").write_text(anterior.model_dump_json(),
                                                     encoding="utf-8")
    (tmp_path / "cambios.md").write_text("el bloque de unos 8 mm sobra\n", encoding="utf-8")
    recibido = {}

    class Recuerda(Ingeniero):
        def concebir(self, spec, anterior=None, cambios=""):
            recibido.update(anterior=anterior, cambios=cambios)
            return super().concebir(spec)

    class Mira(Requisitos):
        def draft(self, peticion):
            recibido["peticion"] = peticion
            return super().draft(peticion)

    concebir_pieza(PETICION, tmp_path, requisitos=Mira(), ingeniero=Recuerda(), log=_nada)

    assert recibido["anterior"].concepto.fijaciones == ["2 tornillos M4 a la pared"]
    assert "unos 8 mm" in recibido["cambios"]
    assert "8 mm" not in recibido["peticion"]


def test_las_uniones_del_plan_van_al_ingeniero_y_no_a_la_peticion(tmp_path):
    """F9.4 (canal). En un backlog, lo que el plan decidió de esta pieza
    (sobre qué gira, cuánto sitio deja) está en `uniones.json`. Va al
    ingeniero; si fuera en la petición, «25 mm» saldría de requisito."""
    import json
    (tmp_path / "uniones.json").write_text(json.dumps([
        {"id": "u2", "texto": "«Plataforma» girará 180° sobre el sg90 que monta esta pieza: "
                              "deja libre un cilindro de radio 25 mm"}]), encoding="utf-8")
    recibido = {}

    class Recuerda(Ingeniero):
        def concebir(self, spec, uniones=""):
            recibido["uniones"] = uniones
            return super().concebir(spec)

    class Mira(Requisitos):
        def draft(self, peticion):
            recibido["peticion"] = peticion
            return super().draft(peticion)

    concebir_pieza(PETICION, tmp_path, requisitos=Mira(), ingeniero=Recuerda(), log=_nada)

    assert "radio 25 mm" in recibido["uniones"]
    assert "25 mm" not in recibido["peticion"]


def test_con_un_retoque_el_disenador_parte_del_programa_construido(tmp_path):
    """Corregir una pieza no vuelve a redactar ni a concebir: se modela con
    la spec y el concepto aprobados, partiendo del programa que ya había."""
    concebir_pieza(PETICION, tmp_path, requisitos=Requisitos(), ingeniero=Ingeniero(),
                   log=_nada)
    aprobar_concepto(tmp_path, por="web")
    (tmp_path / "retoque.json").write_text(json.dumps(
        {"programa": "CODIGO", "cambio": "la tuerca más adentro"}), encoding="utf-8")
    recibido = {}

    def disenar(spec, carpeta, parte, concepto=None, partida=None):
        recibido["partida"] = partida
        return _disenar()(spec, carpeta, parte)

    class NoRedactes:
        def draft(self, peticion):
            raise AssertionError("ya había una especificación aprobada")

    disenar_pieza(PETICION, tmp_path, requisitos=NoRedactes(), disenar=disenar,
                  laminar=_laminar, log=_nada)
    assert recibido["partida"] == ("CODIGO", "la tuerca más adentro")


def test_un_concepto_que_no_sale_deja_el_porque(tmp_path):
    class NoSale:
        def concebir(self, spec):
            raise ValueError("el concepto no se sostiene: brazo NO aguanta")

    concebir_pieza(PETICION, tmp_path, requisitos=Requisitos(), ingeniero=NoSale(), log=_nada)

    assert estado_de(tmp_path)["estado"] == "fallido"
    assert "NO aguanta" in (tmp_path / "blocked.md").read_text(encoding="utf-8")


def test_un_concepto_que_no_sale_guarda_cada_intento_y_su_porque(tmp_path):
    """Banco 1110-0128: el concepto de la plataforma del pan-tilt murió en tres
    intentos y solo quedó el último error; de los otros dos no había rastro.
    Archivar no es borrar: un intento descartado es la única prueba de por qué
    no valía, y sin ella hay que volver a pedir la pieza para verlo."""
    from orchestrator.llm.structured import SalidaInvalida
    intentos = [{"intento": n, "respuesta": f'{{"idea": "forma {n}"}}', "error": f"fallo {n}",
                 "reserva": False} for n in (1, 2, 3)]

    class SinConcepto:
        def concebir(self, spec, **_):
            raise SalidaInvalida("Concepto: 3 intentos sin salida válida", intentos)

    concebir_pieza(PETICION, tmp_path, requisitos=Requisitos(), ingeniero=SinConcepto(),
                   log=_nada)
    motivos = (tmp_path / "intentos" / "concepto" / "motivos.md").read_text(encoding="utf-8")
    assert all(f"fallo {n}" in motivos for n in (1, 2, 3))
    assert (tmp_path / "intentos" / "concepto" / "intento_1.json").is_file()


def test_una_pieza_con_defectos_sale_pero_no_aprobada(tmp_path):
    """F6.8 (mejor): se entrega la mejor que salió, y se dice qué no cumple."""
    falta = "R2 («uno de 5 mm»): pide 1 agujero(s) de Ø5 y hay 0"
    informe = disenar_pieza(PETICION, tmp_path, requisitos=Requisitos(),
                            disenar=_disenar(defectos=[falta]), laminar=_laminar,
                            log=lambda *_: None)
    assert not informe.resuelto and informe.gramos == 3.0
    assert falta in informe.motivo
    assert falta in (tmp_path / "blocked.md").read_text(encoding="utf-8")


def test_lo_buscado_en_internet_llega_a_los_requisitos_y_al_concepto(tmp_path):
    """F3.21 (investigar): la petición nombra una Raspberry Pi 4 sin medidas.
    Lo encontrado va a los requisitos aparte de la petición (como catálogo,
    no como palabra del usuario), y quien aprueba ve el dato con su fuente.
    La petición que queda escrita es la del usuario, tal cual."""
    from orchestrator.investigar import Dato, Investigacion

    url = "https://www.raspberrypi.com/pi4"
    dato = Dato(componente="Raspberry Pi 4", medida="agujeros de montaje", valor=2.7,
                fuente=url, cita="hole diameter 2.7 mm")

    class Investigador:
        def investigar(self, peticion):
            return Investigacion(datos=[dato], sin_encontrar=["alto de los USB"])

    recibido = {}

    class ConExternos(Requisitos):
        def draft(self, peticion, externos=""):
            recibido["externos"] = externos
            return super().draft(peticion)

    peticion = "soporte para una Raspberry Pi 4 en un perfil 2020"
    concebir_pieza(peticion, tmp_path, requisitos=ConExternos(), ingeniero=Ingeniero(),
                   investigador=Investigador(), log=_nada)

    assert "2.7 mm" in recibido["externos"] and url in recibido["externos"]
    assert (tmp_path / "request.md").read_text(encoding="utf-8") == peticion + "\n"
    concepto = (tmp_path / "concepto.md").read_text(encoding="utf-8")
    assert "hole diameter 2.7 mm" in concepto and url in concepto
    assert "alto de los USB" in concepto


def test_intelliprint_pieza_no_lamina(tmp_path, monkeypatch):
    """Laminar al diseñar es tiempo perdido: no se sabe en qué impresora se
    va a imprimir. Se lamina cuando la persona abre PrusaSlicer (decidido
    por el usuario, 2026-11-09)."""
    import argparse
    from pathlib import Path

    from orchestrator import cli, pieza
    from orchestrator.pieza import APROBADO, InformePieza

    def no_lamines(*a, **k):
        raise AssertionError("el diseño no debe laminar")

    recibido = {}

    def disenar_pieza_falso(peticion, carpeta, **kw):
        recibido.update(kw)
        return InformePieza(titulo="t", pieza="p", resuelto=True, bbox_mm=[1, 1, 1])

    monkeypatch.setattr(cli, "elegir_laminador", no_lamines)
    monkeypatch.setattr(cli, "_disenar_con_kit", lambda *a, **k: None)
    monkeypatch.setattr(pieza, "disenar_pieza", disenar_pieza_falso)
    (tmp_path / APROBADO).write_text("{}", encoding="utf-8")
    args = argparse.Namespace(peticion=["un gancho"], archivo=False, carpeta=str(tmp_path),
                              aprobar_concepto=False, comando="pieza")
    cli._pieza(args, Path("."), {"DEEPSEEK_API_KEY": "x", "INTELLIPRINT_WORKSPACE": str(tmp_path)},
               "t")
    assert recibido["laminar"] is None
