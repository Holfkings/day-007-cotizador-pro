"""Aritmetica monetaria exacta.

Todos los montos se manejan con :class:`decimal.Decimal` cuantizado a centavos.
Nunca se usa ``float`` para dinero: un error de 1 centavo repetido 10.000 veces
son $100.000 de diferencia en una factura.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
CERO = Decimal("0.00")


def a_decimal(valor: object) -> Decimal:
    """Convierte ``valor`` a ``Decimal`` sin pasar por ``float``.

    Acepta ``int``, ``str``, ``float`` y ``Decimal``. Los ``float`` se traducen
    via ``repr`` para evitar el ruido binario (``0.1`` -> ``Decimal('0.1')``).
    """
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, float):
        return Decimal(repr(valor))
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, str):
        texto = valor.strip().replace("$", "").replace(" ", "").replace(",", ".")
        if not texto:
            return CERO
        return Decimal(texto)
    raise TypeError(f"valor no numerico: {valor!r}")


def a_centavos(valor: object) -> int:
    """Redondea a centavos enteros (unidad de almacenamiento en SQLite)."""
    return int(a_decimal(valor).quantize(CENT, rounding=ROUND_HALF_UP) * 100)


def de_centavos(centavos: int) -> Decimal:
    return (Decimal(int(centavos)) / Decimal(100)).quantize(CENT)


def q2(valor: Decimal) -> Decimal:
    """Cuantiza a dos decimales con redondeo comercial (half-up)."""
    return a_decimal(valor).quantize(CENT, rounding=ROUND_HALF_UP)


def pct(parte: Decimal, total: Decimal) -> Decimal:
    """Porcentaje que representa ``parte`` sobre ``total`` (0-100)."""
    if total == 0:
        return CERO
    return q2((parte / total) * Decimal(100))


# --- Formato regional (es-CO / es-MX: 1.234.567,89) -----------------------
def formatear(valor: object, simbolo: str = "$") -> str:
    entero, _, frac = f"{q2(a_decimal(valor)):.2f}".partition(".")
    negativo = entero.startswith("-")
    entero = entero.lstrip("-")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    miles = ".".join(grupos)
    return f"{'-' if negativo else ''}{simbolo}{miles},{frac}"