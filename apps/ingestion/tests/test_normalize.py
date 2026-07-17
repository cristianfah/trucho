from trucho_ingest.normalize import (
    campaign_slug,
    country_to_iso,
    is_same_campaign,
    slugify,
)


def test_slugify_strips_accents_and_symbols():
    assert slugify("Sweeter than the sweetest!") == "sweeter-than-the-sweetest"
    assert slugify("Verle la cara a Dios — versión 2") == "verle-la-cara-a-dios-version-2"


def test_campaign_slug():
    assert campaign_slug("Axe/Lynx", "Sweeter than the sweetest", 2025) == (
        "axe-lynx-sweeter-than-the-sweetest-2025"
    )


def test_country_to_iso():
    assert country_to_iso("España") == "ES"
    assert country_to_iso("chile") == "CL"
    assert country_to_iso("México") == "MX"
    assert country_to_iso("Otro") is None
    assert country_to_iso(None) is None


def test_is_same_campaign_fuzzy():
    assert is_same_campaign(
        "Coca-Cola", "Juntos en todas", 2025,
        "Coca Cola", "Juntos en Todas", 2025,
    )
    assert not is_same_campaign(
        "Coca-Cola", "Juntos en todas", 2025,
        "Pepsi", "Juntos en todas", 2025,
    )
    # años demasiado distantes: no es la misma campaña
    assert not is_same_campaign(
        "Coca-Cola", "Juntos en todas", 2020,
        "Coca-Cola", "Juntos en todas", 2025,
    )
