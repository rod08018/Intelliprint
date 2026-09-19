"""Informe de QA: el veredicto es aritmética, no criterio.

Ver SISTEMA_MULTIAGENTE.md § 7.1 y DECISIONES.md ADR-003.
"""

from orchestrator.schemas.qa_report import Assertion, DfmCheck, Defect, QaReport


def _asercion(measured: float) -> Assertion:
    return Assertion(
        name="hole_diameter",
        interface="IF-003",
        expected=22.10,
        tol=0.05,
        measured=measured,
    )


def test_una_asercion_fuera_de_tolerancia_da_fail_aunque_el_llm_calle():
    """Capa 1 manda. El silencio del modelo no aprueba nada."""
    informe = QaReport(
        part="base_giratoria",
        assertions=[_asercion(22.40)],
        dfm_checks=[DfmCheck(name="wall_thickness", passed=True)],
        llm_defects=[],
    )

    assert informe.verdict == "FAIL"


def test_un_defecto_del_llm_da_fail_con_todo_lo_determinista_en_verde():
    """Capa 3: la visión detecta lo que las cotas no ven.

    Todas las medidas correctas y el pocket en la cara equivocada. El
    modelo puede AÑADIR este defecto, y añadirlo tumba el veredicto.
    """
    informe = QaReport(
        part="dedo_der",
        assertions=[_asercion(22.10)],
        dfm_checks=[DfmCheck(name="wall_thickness", passed=True)],
        llm_defects=[
            Defect(description="el alojamiento del pasador está abierto por un lado")
        ],
    )

    assert informe.verdict == "FAIL"


def test_un_qa_agent_complaciente_no_puede_convertir_un_fail_en_pass():
    """F2.12 a nivel de esquema: la garantía es estructural, no de prompt.

    Simula el peor modelo posible: devuelve `verdict: PASS` y cero defectos
    sobre una pieza con una cota 0.30 mm fuera de tolerancia.

    Guard deliberado: hoy pasa porque `verdict` es una propiedad calculada
    y no un campo. Existe para que falle el día que alguien lo convierta en
    campo escribible, que es exactamente como se rompería ADR-003.
    """
    salida_del_modelo = {
        "part": "base_giratoria",
        "assertions": [_asercion(22.40).model_dump()],
        "dfm_checks": [DfmCheck(name="wall_thickness", passed=True).model_dump()],
        "llm_defects": [],
        "verdict": "PASS",
    }

    informe = QaReport(**salida_del_modelo)

    assert informe.verdict == "FAIL"
    assert "verdict" not in QaReport.model_fields


def test_un_chequeo_dfm_fallido_da_fail_con_las_cotas_en_verde():
    """Capa 2: una pieza puede cumplir el contrato y ser imprimible-imposible."""
    informe = QaReport(
        part="dedo_der",
        assertions=[_asercion(22.10)],
        dfm_checks=[
            DfmCheck(name="wall_thickness", passed=False, detail="0.9 mm < 1.2 mm"),
        ],
        llm_defects=[],
    )

    assert informe.verdict == "FAIL"


def test_una_asercion_no_encontrada_da_fail_y_nunca_queda_sin_comprobar():
    """ADR-011: no encontrar la geometría donde el contrato dice es FAIL.
    Si quedara como "no comprobada", aprobaría por omisión."""
    no_encontrada = Assertion(
        name="hole_diameter", interface="IF-003",
        expected=22.10, tol=0.05, measured=None,
    )
    informe = QaReport(part="base", assertions=[no_encontrada])

    assert no_encontrada.ok is False
    assert informe.verdict == "FAIL"
