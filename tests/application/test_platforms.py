from importlib.resources import files

from rom_archive_grabber.application.platforms import load_platforms


def test_load_shipped_platforms_has_other_and_unknown_falls_back() -> None:
    text = files("rom_archive_grabber.data").joinpath("platforms.toml").read_text()
    catalog = load_platforms(text)
    assert catalog.get("gba").folder == "game-boy-advance"
    assert catalog.get("nope").key == "other"
    assert len(catalog.all()) == 12
