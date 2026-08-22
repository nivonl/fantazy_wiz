from fantasy_app.providers.fpl_history import normalize_person_name


def test_normalize_person_name_strips_accents_and_case():
    assert normalize_person_name("David Raya Martín") == "david raya martin"
    assert normalize_person_name("  Extra   Space ") == "extra space"


def test_normalize_person_name_handles_non_decomposable_letters():
    # Regression: plain NFKD + ascii-ignore silently DROPS these letters (Ø has no
    # base+combining-mark decomposition) rather than transliterating them — "Martin Ødegaard"
    # became "martin degaard", which would fail to match Arsenal's real captain.
    assert normalize_person_name("Martin Ødegaard") == "martin odegaard"
    assert normalize_person_name("Christian Nørgaard") == "christian norgaard"
    assert normalize_person_name("Æthelstan") == "aethelstan"
