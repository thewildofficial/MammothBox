import io
from types import SimpleNamespace

from PIL import Image

from src.documents.media_extractor import EmbeddedMediaExtractor


def _make_image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


def test_extract_from_pdf_collects_images(monkeypatch):
    extractor = EmbeddedMediaExtractor()
    image_bytes = _make_image_bytes()

    class DummyElement:
        pass

    monkeypatch.setattr(
        "src.documents.media_extractor.extract_pages",
        lambda file_obj: [[DummyElement()]],
    )
    monkeypatch.setattr(
        EmbeddedMediaExtractor,
        "_collect_pdf_images",
        lambda self, element, page_number, images: images.append(
            {
                "image": Image.open(io.BytesIO(image_bytes)),
                "page_number": page_number,
                "width": 4,
                "height": 4,
                "format": "PNG",
            }
        ),
    )

    results = extractor.extract_from_pdf(io.BytesIO(b"pdf data"))
    assert len(results) == 1
    assert results[0]["width"] == 4
    assert results[0]["page_number"] == 1


def test_extract_from_docx_collects_images(monkeypatch):
    extractor = EmbeddedMediaExtractor()
    image_bytes = _make_image_bytes()

    class DummyRel:
        target_ref = "image/png"
        target_part = SimpleNamespace(blob=image_bytes)

    class DummyPart:
        rels = {"rId1": DummyRel()}

    class DummyDoc:
        part = DummyPart()

    import docx

    monkeypatch.setattr(docx, "Document", lambda file_obj: DummyDoc())

    results = extractor.extract_from_docx(io.BytesIO(b"docx data"))
    assert len(results) == 1
    assert results[0]["width"] == 4

