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


def test_un_concepto_que_no_sale_deja_el_porque(tmp_path):
    class NoSale:
        def concebir(self, spec):
            raise ValueError("el concepto no se sostiene: brazo NO aguanta")

    concebir_pieza(PETICION, tmp_path, requisitos=Requisitos(), ingeniero=NoSale(), log=_nada)

    assert estado_de(tmp_path)["estado"] == "fallido"
    assert "NO aguanta" in (tmp_path / "blocked.md").read_text(encoding="utf-8")


def test_una_pieza_con_defectos_sale_pero_no_aprobada(tmp_path):
    """F6.8 (mejor): se entrega la mejor que salió, y se dice qué no cumple."""
    falta = "R2 («uno de 5 mm»): pide 1 agujero(s) de Ø5 y hay 0"
    informe = disenar_pieza(PETICION, tmp_path, requisitos=Requisitos(),
                            disenar=_disenar(defectos=[falta]), laminar=_laminar,
                            log=lambda *_: None)
    assert not informe.resuelto and informe.gramos == 3.0
    assert falta in informe.motivo
    assert falta in (tmp_path / "blocked.md").read_text(encoding="utf-8")
