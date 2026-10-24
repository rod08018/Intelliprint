"""Un solo perfil activo: qué impresora y material se diseñan y con qué se
lamina (F1.12 (laminado)).

El nombre del perfil de PETG estaba escrito en siete sitios del código.
Cuando el usuario calibró la M5 con eSun PLA+ (2026-10-24), cambiarlo
obligaba a acordarse de todos. Lo esperado sale de esa decisión, tal como
la dio el usuario.
"""

import re
from pathlib import Path

import pytest

from orchestrator.impresion import PerfilIncompleto, perfil_activo

RAIZ = Path(".")


def test_el_perfil_activo_es_la_m5_con_el_pla_calibrado():
    activo = perfil_activo(RAIZ)

    assert activo.impresora.id == "ankermake_m5_plamas"
    assert activo.laminado == "m5_esun_plamas_precision.ini"
    assert activo.material == "PLA+"


def test_las_holguras_siguen_sin_calibrar():
    """El usuario calibró el laminado, no las holguras. `M3_through_mm`
    solo cambia con la pieza de calibración impresa (F2.18 (calibración))."""
    impresora = perfil_activo(RAIZ).impresora

    assert impresora.calibrated is False
    assert impresora.hole_mm("M3_through") == pytest.approx(3.3)


def test_la_densidad_para_estimar_masa_es_la_del_filamento_que_se_lamina():
    """Dos archivos dicen la densidad: el de holguras (para estimar masas al
    diseñar) y el de laminado (para los gramos). Si discrepan, el diseño y
    el laminado hablan de piezas que pesan distinto."""
    activo = perfil_activo(RAIZ)
    ini = (Path("config/slicing") / activo.laminado).read_text(encoding="utf-8")
    densidad = float(re.search(r"^filament_density = ([\d.]+)$", ini, re.M).group(1))

    assert activo.densidad_g_cm3 == pytest.approx(densidad)
    assert densidad == pytest.approx(1.24)   # «esun pla+» en el paquete de eufyMake


def test_un_perfil_activo_que_nombra_archivos_que_no_existen_lo_dice(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "impresion.yaml").write_text(
        "impresora: no_existe\nlaminado: tampoco.ini\n", encoding="utf-8")

    with pytest.raises(PerfilIncompleto, match="no_existe"):
        perfil_activo(tmp_path)


def test_ningun_codigo_nombra_un_perfil_concreto():
    """Si alguien vuelve a escribir el nombre de un perfil en el código, el
    perfil activo deja de mandar en ese sitio y nadie se entera."""
    culpables = []
    for carpeta in ("orchestrator", "scripts"):
        for py in Path(carpeta).rglob("*.py"):
            texto = py.read_text(encoding="utf-8")
            if re.search(r"ankermake_m5_(petg|plamas)|m5_esun_plamas", texto):
                culpables.append(str(py))
    assert culpables == []


def test_el_agente_de_requisitos_propone_el_material_del_perfil_activo():
    """Si no dices material, se supone el del perfil activo, no el PETG que
    estaba escrito en el prompt."""
    from orchestrator.agents.requirements import RequirementsAgent

    class Eco:
        def complete(self, prompt):
            Eco.prompt = prompt
            return ('{"title": "t", "description": "d", "product_class": "static_part", '
                    '"printer": "ankermake_m5_plamas", "material": "PLA+", "estimated": []}')

    RequirementsAgent(Eco(), activo=perfil_activo(RAIZ)).draft("un soporte")

    assert "ankermake_m5_plamas" in Eco.prompt and "PLA+" in Eco.prompt
    assert "PETG" not in Eco.prompt.split("## Petición")[0].split("## Perfil activo")[1]
