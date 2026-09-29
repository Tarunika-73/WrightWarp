"""Small validation helpers shared across Pydantic schemas.

Kept here instead of duplicated in every schema that needs an IATA code
field (``CollectionRequest``, ``FlightQuoteBase``, ``RouteBase``).
"""

IATA_CODE_LENGTH = 3


def validate_iata_code(value: str) -> str:
    """Uppercase and validate a 3-letter IATA airport code."""
    value = value.upper()
    if len(value) != IATA_CODE_LENGTH or not value.isalpha():
        raise ValueError(f"airport code must be {IATA_CODE_LENGTH} alphabetic characters")
    return value
