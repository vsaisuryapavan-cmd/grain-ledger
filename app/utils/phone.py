def normalize_phone_digits(raw_phone: str) -> str:
    digits = "".join(
        character for character in raw_phone
        if character.isdigit()
    )
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def extract_digits(raw_phone: str) -> str:
    return "".join(
        character for character in raw_phone
        if character.isdigit()
    )
