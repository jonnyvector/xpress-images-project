from backend.coverage import extract_match_tokens


def test_extract_tokens_plain_wood_name():
    assert extract_match_tokens("Shaker Cabinet Door") == {"shaker"}


def test_extract_tokens_strips_size_prefix():
    assert extract_match_tokens('3/4" Heritage Cabinet Door') == {"heritage"}


def test_extract_tokens_includes_parenthetical_style():
    assert extract_match_tokens("Tacoma Cabinet Door (Plank Style)") == {"tacoma", "plank"}


def test_extract_tokens_thermofoil_sku_only():
    assert extract_match_tokens("AR756 Thermofoil Cabinet Door") == {"ar756"}


def test_extract_tokens_thermofoil_sku_plus_parenthetical():
    assert extract_match_tokens(
        "DRS131 Thermofoil Cabinet Door (Shaker Style)"
    ) == {"drs131", "shaker"}


def test_extract_tokens_drops_pure_digits_and_generic_words():
    # "Drawer Front", "Style", and bare size digits must not become tokens
    assert extract_match_tokens("Revere Drawer Front") == {"revere"}
