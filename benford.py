"""Leading-digit Benford analysis and Pearson goodness-of-fit calculation."""
from decimal import Decimal, InvalidOperation
from math import exp, log10


DIGITS = tuple(range(1, 10))
FIT_THRESHOLDS = {"moderate_p": 0.05, "strong_p": 0.01}
FIT_NOTE = (
    "Describe el ajuste de esta muestra a Benford, no si una cuenta es bot o humana. "
    "El p-valor no es una probabilidad de que sea bot. La interpretación supone "
    "datos adecuados para Benford e independencia; estos supuestos no se verifican automáticamente."
)


def first_significant_digit(value):
    """Return the first nonzero base-10 digit or None for invalid input."""
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    for character in format(number, "f"):
        if character in "123456789":
            return int(character)
    return None


def benford_proportions():
    """Theoretical first-significant-digit proportions for digits 1 to 9."""
    return {digit: log10(1 + 1 / digit) for digit in DIGITS}


def analyze_counts(values):
    """Compute the observed distribution, Pearson chi-square and p-value."""
    observed = {digit: 0 for digit in DIGITS}
    sample_size = 0
    for value in values:
        digit = first_significant_digit(value)
        if digit is not None:
            observed[digit] += 1
            sample_size += 1

    proportions = benford_proportions()
    expected = {digit: sample_size * proportions[digit] for digit in DIGITS}
    if sample_size == 0:
        return {
            "sample_size": 0,
            "observed": observed,
            "expected": expected,
            "proportions": proportions,
            "chi_square": None,
            "degrees_of_freedom": 8,
            "p_value": None,
        }

    chi_square = sum(
        (observed[digit] - expected[digit]) ** 2 / expected[digit]
        for digit in DIGITS
        if expected[digit] > 0
    )
    # Chi-square survival function with 8 degrees of freedom.
    x = chi_square / 2
    p_value = exp(-x) * (1 + x + x * x / 2 + x * x * x / 6)
    return {
        "sample_size": sample_size,
        "observed": observed,
        "expected": expected,
        "proportions": proportions,
        "chi_square": chi_square,
        "degrees_of_freedom": 8,
        "p_value": min(1.0, max(0.0, p_value)),
    }


def assess_fit(result, *, collection_complete=True, metrics_complete=True):
    """Describe statistical fit, never infer account automation from digits.

    The moderate/strong names are presentation conventions using p=.05/.01,
    not validated bot categories or sample-size-independent effect sizes.
    """
    assessment = {
        "code": "insufficient_data", "label": "No clasificable: datos insuficientes",
        "color": "#526579", "thresholds": dict(FIT_THRESHOLDS),
        "scope": "selected_dataset", "automation_verdict": "No determinable con Benford",
        "note": FIT_NOTE,
    }
    if not result.get("sample_size") or result.get("p_value") is None:
        assessment["reason"] = "No hay conteos positivos válidos para calcular el ajuste."
    elif not collection_complete or not metrics_complete:
        assessment.update(code="incomplete_data", label="No clasificable: muestra incompleta")
        assessment["reason"] = "La recopilación está incompleta, fue interrumpida o faltan métricas del conjunto seleccionado."
    elif min(result["expected"].values()) < 5:
        assessment["reason"] = "Hay frecuencias esperadas menores que 5; se requieren al menos 110 conteos positivos para este criterio."
    elif result["p_value"] >= FIT_THRESHOLDS["moderate_p"]:
        assessment.update(code="compatible", label="Compatible con Benford", color="#0f7255",
                          reason="p ≥ 0,05: no se rechaza el ajuste al nivel del 5 %. Esto no demuestra que la cuenta sea humana.")
    elif result["p_value"] >= FIT_THRESHOLDS["strong_p"]:
        assessment.update(code="moderate_deviation", label="Desviación estadística moderada", color="#946200",
                          reason="0,01 ≤ p < 0,05: se rechaza el ajuste al 5 %, pero no al 1 %.")
    else:
        assessment.update(code="strong_deviation", label="Desviación estadística fuerte", color="#b42318",
                          reason="p < 0,01: se rechaza el ajuste al 1 %. Esto no demuestra que la cuenta sea bot.")
    return assessment


def analyze_dataset(data, relationship, metric):
    """Shared GUI/export calculation with collection-quality safeguards."""
    rows = data.get(relationship) or []
    values = [row.get(metric) for row in rows]
    result = analyze_counts(values)
    collection = data.get("collection") or {}
    metrics_complete = not collection.get("metrics_interrupted") and all(
        not isinstance(value, bool) and value is not None
        and (value == 0 or first_significant_digit(value) is not None)
        for value in values
    )
    result["assessment"] = assess_fit(
        result,
        collection_complete=(collection.get(relationship) or {}).get("complete") is True,
        metrics_complete=metrics_complete,
    )
    return result
