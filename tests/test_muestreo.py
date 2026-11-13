"""Un barrido que escala (F10.5 (muestreo), ADR-021).

Entre dos piezas se barren los giros que hay entre ellas, en todas sus
combinaciones: 19 poses por giro con la rejilla de 10°. Con tres giros son
6 859 y caben; con cinco, 2 476 099, y un brazo de cinco ejes no se podría
ni empezar a mover. Cuando no caben se barre una rejilla más gruesa, que
lleva siempre los extremos y el reposo, y se dice cuántas poses se probaron
y cada cuántos grados: lo que cae entre dos puntos no se ha mirado.

Las cuentas son de cabeza: el mayor impar n con n⁵ ≤ 8 000 es 5 (3 125;
7⁵ son 16 807), y con cuatro giros, 9 (6 561; 11⁴ son 14 641).
"""

import json

import pytest

from tests.test_conjunto import _obra, _sg90, _sobre
from tests.test_tornilleria import _caja_stl

SERVO = (-90, 90)


def test_tres_giros_caben_enteros():
    from orchestrator.conjunto import rejilla_de_poses
    poses, muestreo = rejilla_de_poses({"a": SERVO, "b": SERVO, "c": SERVO}, 10)
    assert len(poses) == 19 ** 3 and muestreo is None
    assert {"a": 90, "b": -90, "c": 0} in poses


def test_cinco_giros_se_barren_cada_45_grados_y_se_dice():
    from orchestrator.conjunto import rejilla_de_poses
    juntas = {j: SERVO for j in "abcde"}
    poses, muestreo = rejilla_de_poses(juntas, 10)
    assert len(poses) == 5 ** 5 == 3125
    assert {p["c"] for p in poses} == {-90, -45, 0, 45, 90}
    assert muestreo == {"juntas": list("abcde"), "probadas": 3125, "de": 19 ** 5,
                        "cada_grados": {j: 45 for j in "abcde"}}


def test_cuatro_giros_se_barren_cada_22_5_grados():
    from orchestrator.conjunto import rejilla_de_poses
    poses, muestreo = rejilla_de_poses({j: SERVO for j in "abcd"}, 10)
    assert len(poses) == 9 ** 4 == 6561
    assert muestreo["cada_grados"]["a"] == 22.5 and muestreo["de"] == 19 ** 4


def test_un_giro_corto_no_se_barre_mas_fino_de_lo_que_ya_iba():
    """Cuatro servos y un dedo que cierra 20° (3 poses con la rejilla de
    10°): al dedo le bastan sus 3, no se le inventan 5."""
    from orchestrator.conjunto import rejilla_de_poses
    poses, muestreo = rejilla_de_poses({**{j: SERVO for j in "abcd"}, "dedo": (-10, 10)}, 10)
    assert {p["dedo"] for p in poses} == {-10, 0, 10}
    assert muestreo["cada_grados"]["dedo"] == 10
    assert len(poses) <= 8000


# --- una cadena de cinco giros, hecha a mano -----------------------------------------------------

def _cadena(tmp_path, giros=5):
    """Seis piezas iguales, cada una con su SG90 y montada en el eje de la
    anterior, como la base y el soporte del pan-tilt: cinco giros en serie."""
    piezas = {}
    for k in range(giros + 1):
        rasgos = [_sg90((23.6, 6, 0))] if k < giros else []
        if k:
            rasgos = [_sobre(f"p{k - 1}", (-29.4, -12.2, -27.6)), *rasgos]
        piezas[f"p{k}"] = ([f"p{k - 1}"] if k else [], rasgos, ([0, 0, 0], [70, 34, 18.5]))
    carpeta = _obra(tmp_path, piezas)
    for i in piezas:
        parte = carpeta / "nodos" / i / "parts" / i
        (parte / f"{i}.stl").write_text(
            "solid p\n" + _caja_stl((0, 0, 0), (70, 34, 18.5)) + "endsolid p\n", encoding="utf-8")
        (carpeta / "nodos" / i / "fabrication").mkdir()
        (carpeta / "nodos" / i / "fabrication" / "slicing_report.json").write_text(
            json.dumps({"grams": 20}), encoding="utf-8")
    return carpeta


def _barrer_con_un_choque_en(carpeta, monkeypatch, plantado):
    """Barre la cadena con un FreeCAD de mentira que solo «ve» chocar la
    primera pieza con la última cuando la última está donde la deja la pose
    `plantado`. Dónde es eso se calcula aquí, con la cinemática, no con la
    rejilla."""
    from orchestrator import assembly, conjunto
    from orchestrator.conjunto import _barrer, _placement, _solidos, articulaciones_de
    from orchestrator.conjunto import leer_piezas, poses

    piezas = leer_piezas(carpeta, "conjunto")
    arts = {a.pieza: a for a in articulaciones_de(carpeta, piezas)}
    assert len(arts) == 5
    ultima = list(piezas)[-1]
    donde = {i: _placement(t) for i, t in poses(piezas, arts, plantado).items()}
    llamadas = []

    def de_mentira(parts, pins, frames, min_gap, freecadcmd, rules=None, solidos=None):
        llamadas.append(len(frames))
        if "p0" not in parts or ultima not in parts or (rules or {}).get(("p0", ultima)):
            return []
        return [assembly.Collision(angle=k, a="p0", b=ultima, gap_mm=-5.0, min_gap_mm=min_gap,
                                   kind="choque")
                for k, f in frames.items()
                if all(f[i].origin == pytest.approx(donde[i].origin, abs=1e-6)
                       and f[i].rotation == pytest.approx(donde[i].rotation, abs=1e-6)
                       for i in f if i in donde)]

    monkeypatch.setattr(assembly, "sweep_collisions", de_mentira)
    duenos, solidos, steps = _solidos(piezas, arts)
    muestreo = []
    choques = _barrer(piezas, arts, duenos, {}, steps, "freecadcmd", 0.1, muestreo=muestreo)
    return choques, muestreo, llamadas, conjunto


def test_un_choque_plantado_en_una_pose_de_cinco_giros_se_encuentra(tmp_path, monkeypatch):
    """La primera pieza y la última, con cinco giros entre las dos, chocan
    con los giros en (90, −45, 0, 45, −90). Antes ese par pedía 2 476 099
    poses; ahora se prueban 3 125 y esa está entre ellas. Los cinco ejes
    son paralelos, así que hay otras combinaciones que dejan la última pieza
    en el mismo sitio: también chocan, y también salen."""
    plantado = {"p1": 90.0, "p2": -45.0, "p3": 0.0, "p4": 45.0, "p5": -90.0}
    choques, muestreo, llamadas, _ = _barrer_con_un_choque_en(_cadena(tmp_path), monkeypatch,
                                                              plantado)
    assert plantado in [c["angulos"] for c in choques]
    # Todas las que salen suman lo mismo: con ejes paralelos, la última pieza
    # queda igual de girada.
    assert {sum(c["angulos"].values()) for c in choques} == {sum(plantado.values())}
    assert 3125 in llamadas and max(llamadas) <= 8000   # ninguna pasa del tope
    [lejos] = [m for m in muestreo if len(m["juntas"]) == 5]
    assert (lejos["probadas"], lejos["de"]) == (3125, 19 ** 5)
    # Las vecinas, con un solo giro entre las dos, se siguen barriendo enteras.
    assert 19 in llamadas and not [m for m in muestreo if len(m["juntas"]) == 1]


def test_lo_que_cae_entre_dos_puntos_de_la_rejilla_no_se_ve_y_se_dice(tmp_path, monkeypatch):
    """Con todos los giros a 10° no hay punto en la rejilla de 45°: ese
    choque se escapa. No se oculta: queda dicho cuántas poses se probaron."""
    plantado = {f"p{k}": 10.0 for k in range(1, 6)}
    choques, muestreo, _, _ = _barrer_con_un_choque_en(_cadena(tmp_path), monkeypatch, plantado)
    assert choques == []
    assert any(m["probadas"] < m["de"] for m in muestreo)


def test_el_resumen_dice_que_no_se_probo_todo():
    from orchestrator.conjunto import muestreo_en_palabras
    texto = muestreo_en_palabras([{"juntas": list("abcde"), "probadas": 3125, "de": 19 ** 5,
                                   "cada_grados": {j: 45 for j in "abcde"}}])
    assert "3125" in texto and "2476099" in texto and "45°" in texto


def test_el_estudio_de_cinco_giros_prueba_la_rejilla_gruesa_y_no_un_giro_cada_vez(tmp_path):
    """Con más de 8 000 poses el estudio movía cada giro por turno con los
    demás en 0°: 5 × 19 = 95 poses, entre las que puede no estar la peor.
    Ahora, las 3 125 de la rejilla de 45°, con los extremos de todos."""
    from orchestrator.estudio import estudiar
    e = estudiar(_cadena(tmp_path), "conjunto")
    assert e["poses"] == 3125
    assert any("45°" in a for a in e["avisos"])
