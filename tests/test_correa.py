"""La correa GT2 y sus poleas (F10.3 (correa), ADR-021).

Los dientes los genera el código, no el modelo: una polea sale de una
fórmula con parámetros y tiene oráculo. Los de aquí no salen del sistema:

- **Diámetros**, de la tabla «2mm - PowerGrip GT / 2MR» de Pfeifer
  Industries (pfeiferindustries.com, «Timing Belt Pulley PD and OD»):
  20 dientes, 12,73 de primitivo y 12,22 de exterior; 60 dientes, 38,20 y
  37,69; 80 dientes, 50,93 y 50,42.
- **La correa**, del manual técnico de SDP/SI (sdp-si.com,
  D820 «Technical Section», sección 22): con dos poleas iguales,
  C = p·(NB − N1)/2; con dos distintas, 2C·sen φ = L − π(R1 + R2) −
  (π − 2φ)(R1 − R2), con C·cos φ = R1 − R2.
- **Los volúmenes**, a mano, con el área de la lente que dos círculos se
  quitan uno a otro. Van en el docstring de su test.
"""

import math
from pathlib import Path

import pytest
import yaml

from tests.test_generators import _freecadcmd

PERFIL = yaml.safe_load(Path("config/printers/ankermake_m5_plamas.yaml").read_text(encoding="utf-8"))


# --- las cuentas ----------------------------------------------------------------------------

@pytest.mark.parametrize("dientes, primitivo, exterior", [
    (20, 12.73, 12.22), (60, 38.20, 37.69), (80, 50.93, 50.42)])
def test_los_diametros_de_una_polea_son_los_de_la_tabla(dientes, primitivo, exterior):
    from mech_toolkit.transmisiones import diametro_exterior, diametro_primitivo
    assert diametro_primitivo(dientes) == pytest.approx(primitivo, abs=0.006)
    assert diametro_exterior(dientes) == pytest.approx(exterior, abs=0.006)


def test_con_dos_poleas_iguales_la_correa_son_dos_tramos_y_una_vuelta():
    """Dos poleas de 20 dientes a 80 mm: dos tramos rectos de 80 y media
    vuelta en cada una, 160 + 20 × 2 = 200 mm, 100 dientes. Y al revés,
    como lo da el manual: C = p·(NB − N1)/2 = 2 × (100 − 20)/2 = 80."""
    from mech_toolkit.transmisiones import distancia_entre_ejes, largo_de_correa
    assert largo_de_correa(20, 20, 80) == pytest.approx(200)
    assert distancia_entre_ejes(20, 20, 100) == pytest.approx(80)


def test_el_largo_de_la_correa_entre_una_polea_de_20_y_una_de_80():
    """A 60 mm entre ejes, a mano. Radios primitivos: 80/π = 25,465 y
    20/π = 6,366; su diferencia, 19,099.

    - cos φ = 19,099 / 60 = 0,31831 → φ = 1,24685 rad; sen φ = 0,94799.
    - L = 2 × 60 × 0,94799 + π × 31,831 + (π − 2 × 1,24685) × 19,099
        = 113,759 + 100,000 + 12,374 = 226,13 mm.

    La fórmula corta de los libros, 2C + π(D + d)/2 + (D − d)²/(4C), da
    120 + 100 + 38,197² / 240 = 226,08: lo mismo con medio diente de
    diferencia en cien."""
    from mech_toolkit.transmisiones import largo_de_correa
    assert largo_de_correa(20, 80, 60) == pytest.approx(226.13, abs=0.01)
    assert largo_de_correa(80, 20, 60) == pytest.approx(226.13, abs=0.01)


def test_la_distancia_entre_ejes_que_pide_una_correa():
    """Una correa de 140 dientes (280 mm) entre una polea de 20 y una de 80.
    Con la fórmula corta: 280 = 2C + 100 + 1459,0/(4C) → 2C² − 180C +
    364,75 = 0 → C = (180 + √(32400 − 2918)) / 4 = 87,93 mm. La exacta
    tiene que devolver los 280 mm al volver a medir la correa."""
    from mech_toolkit.transmisiones import distancia_entre_ejes, largo_de_correa
    c = distancia_entre_ejes(20, 80, 140)
    assert c == pytest.approx(87.93, abs=0.05)
    assert largo_de_correa(20, 80, c) == pytest.approx(280, abs=1e-6)


def test_una_correa_que_no_abraza_las_dos_poleas_no_tiene_distancia():
    """Con las poleas de 20 y 80 tocándose (ejes a 31,83 mm, la suma de sus
    radios primitivos) la correa ya mide 175,5 mm: una de 80 dientes,
    160 mm, no llega."""
    from mech_toolkit.transmisiones import distancia_entre_ejes
    assert distancia_entre_ejes(20, 80, 80) is None


def test_la_polea_conducida_sale_de_la_relacion():
    """4:1 con la polea de 20 del motor son 80 dientes. Una relación que no
    da dientes enteros no existe: 20 × 2,33 = 46,6."""
    from mech_toolkit.transmisiones import dientes_de_la_conducida
    assert dientes_de_la_conducida(20, 4) == 80
    assert dientes_de_la_conducida(20, 2.5) == 50
    with pytest.raises(ValueError, match="46.6"):
        dientes_de_la_conducida(20, 2.33)


def test_la_correa_que_cabe_en_una_distancia_con_su_ajuste():
    """Los ejes a 88 mm con ±2 mm de colisa: entre 86 y 90 mm. La de 140
    dientes pide 87,93 (cabe); la de 139, 86,90 (cabe); la de 141, 88,95
    (cabe). Se elige la que queda más cerca del centro del ajuste: 140."""
    from mech_toolkit.transmisiones import correa_para
    c = correa_para(20, 80, 88, ajuste=2)
    assert c["dientes"] == 140 and c["largo_mm"] == 280
    assert c["entre_ejes_mm"] == pytest.approx(87.93, abs=0.05)
    # Sin ajuste no hay correa que dé 88,5 mm justos: ninguna cae a ±0,2.
    assert correa_para(20, 80, 88.45, ajuste=0.2) is None


# --- la polea, construida de verdad ---------------------------------------------------------

con_freecad = pytest.mark.skipif(_freecadcmd() is None, reason="sin freecadcmd")


def _construir(codigo: str, tmp_path: Path):
    from orchestrator.build import build_part
    from orchestrator.schemas.programa import Programa
    return build_part(Programa(part="p", codigo=codigo), None, tmp_path, _freecadcmd(),
                      perfil=PERFIL)


def _lente(R: float, r: float) -> float:
    """El área que un círculo de radio r con el centro en el borde de otro
    de radio R le quita a este: r²·acos(r/2R) + R²·acos(1 − r²/2R²) −
    (r/2)·√(4R² − r²)."""
    return (r * r * math.acos(r / (2 * R)) + R * R * math.acos(1 - r * r / (2 * R * R))
            - r / 2 * math.sqrt(4 * R * R - r * r))


@con_freecad
def test_una_polea_de_80_dientes_tiene_80_ranuras(tmp_path):
    """Sin pestañas, para una correa de 6 mm: 9 mm de ancho (el manual pide
    3 mm más que la correa si no hay pestañas). Es un cilindro del diámetro
    exterior, 50,42 mm, con 80 ranuras semicirculares con el centro en su
    borde y el radio del alto del diente de la correa, 0,76 mm (manual de
    SDP/SI, figura 19g). Entre ranura y ranura quedan 0,46 mm de cresta.

    Cada ranura quita una lente de 0,9015 mm²: (π × 25,211² − 80 × 0,9015)
    × 9 = 17 321,6 mm³. Con 79 u 81 ranuras saldrían 8 mm³ de más o de
    menos."""
    r = _construir("""
def construir(kit):
    return kit.polea_gt2("polea", 80, pestanas=False)
""", tmp_path)
    R = (160 / math.pi - 0.508) / 2
    assert r.volume_mm3 == pytest.approx(17321.6, abs=1.5)
    assert (math.pi * R * R - 80 * _lente(R, 0.76)) * 9 == pytest.approx(17321.6, abs=0.1)
    [polea] = [x for x in r.rasgos if x["tipo"] == "polea_gt2"]
    assert polea["dientes"] == 80 and polea["ancho_mm"] == 9
    assert polea["primitivo_mm"] == pytest.approx(50.93, abs=0.006)
    assert polea["centro"] == [0, 0, 0] and polea["eje"] == [0, 0, 1]


@con_freecad
def test_las_pestanas_son_dos_conos_que_se_imprimen_sin_soportes(tmp_path):
    """Con pestañas la cara de los dientes mide 7 mm (1 más que la correa,
    según el manual) y a cada lado va un cono de 1,5 mm de alto —la altura
    nominal de pestaña para 2 mm GT— que sube a 45° del diámetro exterior a
    3 mm más. Un tronco de cono: π·h/3·(R² + R·r + r²).

    Con 20 dientes (R = 6,112): dientes, (π × 6,112² − 20 × 0,8833) × 7 =
    697,9 mm³; cada cono, π × 1,5/3 × (7,612² + 7,612 × 6,112 + 6,112²) =
    222,8 mm³. En total, 1 143,5 mm³, y 10 mm de alto."""
    r = _construir("""
def construir(kit):
    return kit.polea_gt2("polea", 20, en=(10, 0, 5))
""", tmp_path)
    R = (40 / math.pi - 0.508) / 2
    cono = math.pi * 1.5 / 3 * ((R + 1.5) ** 2 + (R + 1.5) * R + R * R)
    assert r.volume_mm3 == pytest.approx(1143.5, abs=1.0)
    assert (math.pi * R * R - 20 * _lente(R, 0.76)) * 7 + 2 * cono == pytest.approx(1143.5,
                                                                                    abs=0.1)
    [polea] = [x for x in r.rasgos if x["tipo"] == "polea_gt2"]
    assert polea["ancho_mm"] == 7 and polea["alto_mm"] == 10
    assert polea["centro"] == [10, 0, 5]


@con_freecad
def test_una_polea_con_muy_pocos_dientes_no_se_hace(tmp_path):
    """Menos de 12 dientes no está ni en la tabla del fabricante: la correa
    no se dobla tanto."""
    from orchestrator.build import ConstruccionFallida
    with pytest.raises(ConstruccionFallida, match="12"):
        _construir("""
def construir(kit):
    return kit.polea_gt2("polea", 8)
""", tmp_path)


# --- lo que se compra ------------------------------------------------------------------------

def test_la_polea_del_motor_tiene_ficha_con_lo_que_dice_su_tienda():
    """Adafruit 1251: 16 mm de largo, 16 mm de diámetro mayor, agujero de
    5 mm y 6 g. Con el agujero de 5: la atraviesa el eje del NEMA 17, que
    mide eso."""
    from orchestrator.componentes import cargar, envolvente
    f = cargar("polea-gt2-20")
    assert envolvente(f) == ([-8, -8, 0], [8, 8, 16])
    assert f.cuerpos[0].cilindro.interior == 5 == cargar("nema17").cuerpos[2].cilindro.diametro
    assert f.masa_g == 6 and not f.da_par()


# --- la correa en un backlog: lo que se dice, lo que se mide y lo que se compra ---------------

def _con_correa(tmp_path, motor_en=(-87.9, 10, 25), motor_giros=(("x", 90),), polea=80,
                polea_en=(0, -1, 25)):
    """La articulación de `test_transmision`: el 608ZZ tumbado, con su eje
    por (0, ·, 25) hacia −y, y el brazo saliendo en x. Aquí el motor va
    también tumbado, con el eje hacia −y, a 87,9 mm del rodamiento; y el
    brazo lleva una polea de 80 dientes en el eje, cuya banda dentada (de
    1,5 a 8,5 mm de su base) queda entre y = −2,5 e y = −9,5. El eje del
    motor, de 24 mm, va de y = 10 a y = −14: la correa tiene sus 6 mm."""
    import json
    from tests.test_transmision import _articulacion
    carpeta = _articulacion(tmp_path)
    rasgos = carpeta / "nodos" / "soporte" / "parts" / "soporte" / "rasgos.json"
    suyos = json.loads(rasgos.read_text(encoding="utf-8"))
    suyos[1].update(en=list(motor_en), giros=[list(g) for g in motor_giros])
    rasgos.write_text(json.dumps(suyos), encoding="utf-8")
    if polea:
        rasgos = carpeta / "nodos" / "brazo" / "parts" / "brazo" / "rasgos.json"
        suyos = json.loads(rasgos.read_text(encoding="utf-8"))
        suyos.append({"nombre": "polea", "tipo": "polea_gt2", "dientes": polea,
                      "centro": list(polea_en), "eje": [0, -1, 0], "ancho_mm": 7, "alto_mm": 10,
                      "primitivo_mm": polea * 2 / math.pi, "correa_mm": 6})
        rasgos.write_text(json.dumps(suyos), encoding="utf-8")
    return carpeta


def test_las_distancias_entre_ejes_que_se_ofrecen_dan_correas_enteras():
    """Con poleas de 20 y 80. Lo menos que pueden separarse los ejes: el
    radio de la grande con sus pestañas (50,42 + 3)/2, el de la comprada
    (16/2) y 2 mm entre las dos: 36,7 mm. La primera correa que lo pasa, de
    las que van de 5 en 5 dientes, es la de 95 (190 mm), con los ejes a
    40,39; la siguiente, la de 100, a 45,97. (La de 90 pide 34,58: las
    poleas se tocarían.)"""
    from orchestrator.transmision import distancias_posibles
    primera, segunda, *resto = distancias_posibles(20, 80)
    assert (primera["dientes"], segunda["dientes"]) == (95, 100)
    assert primera["entre_ejes_mm"] == pytest.approx(40.39, abs=0.01)
    assert segunda["entre_ejes_mm"] == pytest.approx(45.97, abs=0.01)
    assert len(resto) == 2


def test_una_relacion_que_no_da_dientes_enteros_no_pasa_el_plan():
    from orchestrator.plan import validar_plan
    from orchestrator.schemas.obra import Obra
    from tests.test_plan_mecanico import AGUJEROS
    from tests.test_transmision import _plan
    errores, _ = validar_plan(Obra(**_plan(movido_por={"relacion": 2.33})), AGUJEROS)
    assert len(errores) == 1 and "46.6" in errores[0] and "u2" in errores[0]


def test_la_articulacion_bien_hecha_no_tiene_defectos_de_correa(tmp_path):
    from orchestrator.transmision import defectos_de_transmision
    carpeta = _con_correa(tmp_path)
    assert defectos_de_transmision(carpeta, "soporte") == []
    assert defectos_de_transmision(carpeta, "brazo") == []


def test_el_motor_tiene_que_ir_paralelo_al_rodamiento(tmp_path):
    """De pie, con el eje hacia +z, cuando el del rodamiento va hacia −y:
    una correa no tuerce."""
    from orchestrator.transmision import defectos_de_transmision
    [d] = defectos_de_transmision(_con_correa(tmp_path, motor_giros=()), "soporte")
    assert "paralelo" in d and "u1" in d


def test_el_motor_tiene_que_salir_hacia_el_mismo_lado(tmp_path):
    """Tumbado al revés, con el eje hacia +y: las poleas quedarían una a
    cada lado del soporte."""
    from orchestrator.transmision import defectos_de_transmision
    [d] = defectos_de_transmision(_con_correa(tmp_path, motor_giros=(("x", -90),)), "soporte")
    assert "mismo lado" in d


def test_los_ejes_van_a_la_distancia_de_una_correa_que_exista(tmp_path):
    """A 84,3 mm no hay correa: la de 136 dientes pide 83,81 y la de 137,
    84,84; las dos quedan a más de 0,2 mm, que es lo que el manual admite."""
    from orchestrator.transmision import defectos_de_transmision
    [d] = defectos_de_transmision(_con_correa(tmp_path, motor_en=(-84.3, 10, 25)), "soporte")
    assert "84.3" in d and "83.8" in d and "84.8" in d


def test_los_ejes_no_pueden_ir_tan_juntos_que_las_poleas_se_toquen(tmp_path):
    from orchestrator.transmision import defectos_de_transmision
    [d] = defectos_de_transmision(_con_correa(tmp_path, motor_en=(-30, 10, 25)), "soporte")
    assert "30" in d and "36.7" in d


def test_el_eje_del_motor_tiene_que_asomar_por_donde_va_la_polea(tmp_path):
    """En la corrida 1113-0216 el motor iba por detrás de una placa de 40 mm
    y su eje, de 24, no llegaba a salir: la polea del brazo, que va por
    delante del rodamiento, no tenía correa posible, y el defecto se le dio
    al brazo.

    Aquí el rodamiento va de y = 3,5 a y = −3,5 y el brazo sale por −y. Con
    el motor en y = 25, su eje acaba en y = 1: se queda 4,5 mm antes de la
    cara del rodamiento. La polea necesita 8,5 mm de eje por delante de esa
    cara: 1,5 de su pestaña, los 6 de la correa y 1 de holgura."""
    from orchestrator.transmision import defectos_de_transmision
    [d] = defectos_de_transmision(_con_correa(tmp_path, motor_en=(-87.9, 25, 25)), "soporte")
    assert "asom" in d and "8.5 mm" in d and "4.5 mm" in d


def test_a_quien_monta_el_motor_se_le_dice_cuanto_tiene_que_asomar_su_eje(tmp_path):
    from orchestrator.obra import uniones_del_nodo
    [soporte] = uniones_del_nodo(_con_correa(tmp_path), "soporte")
    assert "8.5 mm" in soporte["texto"] and "asom" in soporte["texto"]


def test_la_pieza_que_gira_lleva_la_polea(tmp_path):
    from orchestrator.transmision import defectos_de_transmision
    [d] = defectos_de_transmision(_con_correa(tmp_path, polea=None), "brazo")
    assert "polea_gt2" in d and "80" in d


def test_la_polea_tiene_los_dientes_de_la_relacion(tmp_path):
    """4:1 con la de 20 del motor son 80: una de 60 da 3:1."""
    from orchestrator.transmision import defectos_de_transmision
    [d] = defectos_de_transmision(_con_correa(tmp_path, polea=60), "brazo")
    assert "60" in d and "80" in d


def test_la_polea_va_en_el_eje_del_giro(tmp_path):
    """Con el centro 3 mm por encima del eje del rodamiento, la polea
    cabecearía al girar."""
    from orchestrator.transmision import defectos_de_transmision
    [d] = defectos_de_transmision(_con_correa(tmp_path, polea_en=(0, -1, 28)), "brazo")
    assert "3.0 mm" in d and "eje" in d


def test_la_polea_queda_a_la_altura_del_eje_del_motor(tmp_path):
    """Con el motor 30 mm más atrás, su eje va de y = 40 a y = 16 y los
    dientes de la polea siguen entre −2,5 y −9,5: la correa no llega."""
    from orchestrator.transmision import defectos_de_transmision
    [d] = defectos_de_transmision(_con_correa(tmp_path, motor_en=(-87.9, 40, 25)), "brazo")
    assert "correa" in d and "6 mm" in d


def test_a_cada_pieza_se_le_dice_su_parte_de_la_correa(tmp_path):
    from orchestrator.obra import uniones_del_nodo
    carpeta = _con_correa(tmp_path)
    [soporte] = uniones_del_nodo(carpeta, "soporte")
    assert "20 dientes" in soporte["texto"] and "80" in soporte["texto"]
    assert "40.4 mm" in soporte["texto"] and "95 dientes" in soporte["texto"]
    assert "mismo lado" in soporte["texto"]
    [brazo] = uniones_del_nodo(carpeta, "brazo")
    assert 'kit.polea_gt2("polea", 80' in brazo["texto"] and "nema17" in brazo["texto"]


def test_a_lo_que_gira_en_un_rodamiento_se_le_dice_como_entra_en_el(tmp_path):
    """El texto del giro está escrito para un servo: «toda la pieza va por
    delante de la cara». En un rodamiento la pieza lo atraviesa con un eje,
    y ese eje no puede entrar justo: hecha a mano (2026-11-12), con un eje
    de Ø7,9 en el agujero de 8 el barrido la dio por choque (0,05 mm), y con
    la holgura deslizante del perfil (Ø7,8, 0,1 mm) pasó."""
    from orchestrator.obra import uniones_del_nodo
    [brazo] = uniones_del_nodo(_con_correa(tmp_path), "brazo")
    assert "atraviesa" in brazo["texto"] and "«slide»" in brazo["texto"]
    assert "7 mm" in brazo["texto"]


def test_la_correa_y_la_polea_del_motor_salen_en_las_compras(tmp_path):
    """Los ejes a 87,9 mm: la correa de 140 dientes (280 mm), que pide
    87,92. Y la polea de 20 del motor, que nadie coloca en el dibujo."""
    from orchestrator.materiales import materiales
    comprado = {c["id"]: c for c in materiales(_con_correa(tmp_path))["comprado"]}
    assert comprado["polea-gt2-20"]["cuantos"] == 1
    [correa] = [c for c in comprado.values() if c["tipo"] == "transmision"]
    assert "140 dientes" in correa["nombre"] and "280 mm" in correa["nombre"]
    assert "6 mm" in correa["nombre"] and correa["cuantos"] == 1


@pytest.mark.parametrize("polea, estado, dice", [
    (80, "cumple", "80 dientes"),
    (60, "no_cumple", "60"),
    (None, "no_cumple", "polea"),
])
def test_el_banco_cuenta_la_reduccion_por_dientes(tmp_path, monkeypatch, polea, estado, dice):
    """80 dientes en la pieza que gira y 20 en el motor: 4:1. Con 60, 3:1."""
    from tests.test_banco import _juzgar_brazo
    [r] = _juzgar_brazo(tmp_path, monkeypatch, [{"tipo": "reduccion", "relacion": 4}],
                        "una articulación con correa 4:1",
                        brazo=lambda p: _con_correa(p, polea=polea))
    assert r.estado == estado, r.detalle
    assert dice in r.detalle


def test_el_encargo_14_pide_lo_que_dice_su_peticion():
    """«un motor NEMA 17 por una correa 4:1», «gira 180°», «levanta 300 g a
    150 mm del eje»."""
    from orchestrator.banco import cargar_encargos
    [e] = [e for e in cargar_encargos(Path("tests/banco/encargos"))
           if e.nombre == "articulacion_correa_nema17"]
    por_tipo = {a.tipo: a for a in e.oraculo}
    assert por_tipo["reduccion"].relacion == 4
    assert por_tipo["carga"].minimo_g == 300 and por_tipo["alcance"].minimo_mm == 150
    assert "4:1" in e.peticion and "300 g" in e.peticion and "150 mm" in e.peticion
