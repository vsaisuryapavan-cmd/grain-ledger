from decimal import Decimal


def to_decimal(value) -> Decimal:
    return Decimal(str(value or 0))
