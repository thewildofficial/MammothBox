from PIL import Image

from src.media.processor import MediaProcessor


def _make_frame(color):
    return Image.new("RGB", (8, 8), color=color)


class DummyStorage:
    pass


def test_filter_diverse_frames_returns_different_colors():
    processor = MediaProcessor(storage=DummyStorage())
    frames = [
        _make_frame((255, 0, 0)),
        _make_frame((254, 10, 10)),
        _make_frame((0, 255, 0)),
        _make_frame((0, 0, 255)),
    ]

    diverse = processor.filter_diverse_frames(frames, target_count=2)
    assert len(diverse) == 2
    colors = {frame.getpixel((0, 0)) for frame in diverse}
    assert len(colors) == 2


def test_filter_diverse_frames_handles_small_inputs():
    processor = MediaProcessor(storage=DummyStorage())
    frames = [_make_frame((10, 10, 10))]

    assert processor.filter_diverse_frames(frames, target_count=3) == frames

