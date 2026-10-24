from rom_archive_grabber.domain.names import clean_title, is_game_file, safe_file_name


def test_is_game_file_case_insensitive() -> None:
    assert is_game_file("Tobu.GB")
    assert is_game_file("x.7z")
    assert not is_game_file("readme.txt")


def test_clean_title() -> None:
    assert clean_title("Tobu_Tobu_Girl  (v1.1).gb") == "Tobu Tobu Girl (v1.1)"


def test_safe_file_name_cases() -> None:
    assert safe_file_name("../../evil.zip") == "evil.zip"
    assert safe_file_name("a<b>:c?.gba") == "a b c.gba"
    assert safe_file_name("CON.nes") == "_CON.nes"
    assert safe_file_name("game.  ") == "game"
    long_name = safe_file_name("x" * 300 + ".gb")
    assert len(long_name) <= 150
    assert long_name.endswith(".gb")
    assert safe_file_name("") == "download"
