from rom_archive_grabber.ui.downloads.speed_meter import SpeedMeter


def test_speed_is_unknown_until_two_samples() -> None:
    meter = SpeedMeter()
    assert meter.rate() is None
    meter.add(10.0, 1_000)
    assert meter.rate() is None


def test_speed_uses_only_the_last_two_seconds() -> None:
    meter = SpeedMeter()
    meter.add(0.0, 0)
    meter.add(1.0, 100_000)
    meter.add(2.5, 400_000)
    meter.add(3.0, 500_000)
    # The sample at 0.0 is older than two seconds and no longer counts.
    assert meter.rate() == 200_000


def test_bytes_going_back_start_a_new_measurement() -> None:
    meter = SpeedMeter()
    meter.add(0.0, 500)
    meter.add(1.0, 100)
    assert meter.rate() is None
    meter.reset()
    assert meter.rate() is None
