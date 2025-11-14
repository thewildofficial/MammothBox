"""Real-world regression tests that exercise the multimodal pipeline."""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, Generator, Set
from uuid import UUID, uuid4

import pytest

from src.catalog.database import Base, SessionLocal, engine
from src.catalog.models import (
    Asset,
    AssetRaw,
    Cluster,
    DocumentChunk,
    Lineage,
    VideoFrame,
)
from src.catalog.queries import QueryProcessor, SearchFilter
from src.documents.service import DocumentService
from src.media.service import MediaService
from src.storage.filesystem import FilesystemStorage

REAL_DATA_ENV = "MAMMOTHBOX_REAL_DATA_DIR"
DEFAULT_DATA_ROOT = Path.home() / "Downloads"
DOCUMENT_EXTENSIONS = (".pdf", ".docx")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv")
JSON_EXTENSIONS = (".json",)

pytestmark = pytest.mark.realdata


@pytest.fixture(scope="session")
def _ensure_schema() -> Generator[None, None, None]:
    """Make sure all tables exist before running the real-data suite."""
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(scope="session")
def real_data_paths() -> Dict[str, Optional[Path]]:
    """Locate real-world files inside the configured Downloads folder."""
    candidates = []
    env_override = os.environ.get(REAL_DATA_ENV)
    if env_override:
        candidates.append(Path(env_override).expanduser())
    candidates.append(DEFAULT_DATA_ROOT)

    data_root: Optional[Path] = None
    for candidate in candidates:
        try:
            if candidate.exists():
                data_root = candidate
                break
        except PermissionError:
            # Some CI environments may block access to ~/Downloads
            continue

    if data_root is None:
        pytest.skip(
            "Real dataset directory not found. Set MAMMOTHBOX_REAL_DATA_DIR to an alternate folder"
            " or ensure ~/Downloads is accessible and contains sample documents/media."
        )

    def _pick(first_extensions: tuple[str, ...]) -> Optional[Path]:
        for ext in first_extensions:
            matches = sorted(data_root.rglob(f"*{ext}"))
            if matches:
                return matches[0]
        return None

    document = _pick(DOCUMENT_EXTENSIONS)
    image = _pick(IMAGE_EXTENSIONS)

    if not document or not image:
        pytest.skip(
            "Real dataset is missing at least one PDF/DOCX and one image file."
        )

    return {
        "root": data_root,
        "document": document,
        "image": image,
        "video": _pick(VIDEO_EXTENSIONS),
        "json": _pick(JSON_EXTENSIONS),
    }


@pytest.fixture(scope="session")
def real_data_context(_ensure_schema, real_data_paths, tmp_path_factory):
    """Ingest a handful of real files so downstream tests can query them."""
    storage_root = tmp_path_factory.mktemp("realdata_storage")
    storage = FilesystemStorage(str(storage_root))
    session = SessionLocal()
    created_assets = []
    created_raw_assets = []
    created_clusters = []
    created_requests = []

    context: Dict[str, Dict[str, object]] = {}
    query_processor = QueryProcessor()

    try:
        # Create a dedicated cluster for the document asset so we can filter chunk queries.
        document_cluster = Cluster(
            name=f"real-doc-{uuid4()}",
            threshold=0.72,
            provisional=True,
        )
        session.add(document_cluster)
        session.commit()
        created_clusters.append(document_cluster.id)

        doc_info = _ingest_document(
            session=session,
            storage=storage,
            file_path=real_data_paths["document"],
            cluster_id=document_cluster.id,
        )
        created_assets.append(doc_info["asset_id"])
        created_raw_assets.append(doc_info["asset_raw_id"])
        created_requests.append(doc_info["request_id"])
        created_assets.extend(doc_info["derived_assets"])
        created_raw_assets.extend(doc_info["derived_raw_assets"])
        created_clusters.extend(
            [cid for cid in doc_info["derived_clusters"] if cid]
        )
        context["document"] = doc_info

        image_info = _ingest_media(
            session=session,
            storage=storage,
            file_path=real_data_paths["image"],
        )
        created_assets.append(image_info["asset_id"])
        created_raw_assets.append(image_info["asset_raw_id"])
        created_requests.append(image_info["request_id"])
        if image_info["cluster_id"]:
            created_clusters.append(image_info["cluster_id"])
        context["image"] = image_info

        if real_data_paths.get("video"):
            video_info = _ingest_media(
                session=session,
                storage=storage,
                file_path=real_data_paths["video"],
            )
            created_assets.append(video_info["asset_id"])
            created_raw_assets.append(video_info["asset_raw_id"])
            created_requests.append(video_info["request_id"])
            if video_info["cluster_id"]:
                created_clusters.append(video_info["cluster_id"])
            context["video"] = video_info
        else:
            context["video"] = None

        if real_data_paths.get("json"):
            json_info = _ingest_json_asset(
                session=session,
                storage=storage,
                file_path=real_data_paths["json"],
                query_processor=query_processor,
            )
            created_assets.append(json_info["asset_id"])
            created_raw_assets.append(json_info["asset_raw_id"])
            created_requests.append(json_info["request_id"])
            context["json"] = json_info
        else:
            context["json"] = None

        context["storage_root"] = storage_root
        yield context
    finally:
        # Clean up database rows created for the regression dataset
        processed_assets: Set[UUID] = set()
        processed_raw_assets: Set[UUID] = set()

        for asset_id in created_assets:
            _purge_asset(session, asset_id, processed_assets, processed_raw_assets)

        for raw_id in created_raw_assets:
            if raw_id not in processed_raw_assets:
                session.query(AssetRaw).filter(AssetRaw.id == raw_id).delete(
                    synchronize_session=False
                )
                processed_raw_assets.add(raw_id)

        for cluster_id in created_clusters:
            dangling_assets = [
                row[0]
                for row in session.query(Asset.id)
                .filter(Asset.cluster_id == cluster_id)
                .all()
            ]
            for asset_id in dangling_assets:
                _purge_asset(session, asset_id, processed_assets, processed_raw_assets)

            session.query(Cluster).filter(Cluster.id == cluster_id).delete(
                synchronize_session=False
            )
        for request_id in created_requests:
            session.query(Lineage).filter(Lineage.request_id == request_id).delete(
                synchronize_session=False
            )
        session.commit()
        session.close()

        # Remove temporary storage artifacts
        shutil.rmtree(storage_root, ignore_errors=True)


def _guess_mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _store_raw_file(storage: FilesystemStorage, request_id: str, path: Path) -> str:
    with path.open("rb") as f:
        data = f.read()
    return storage.store_raw(request_id, path.stem, BytesIO(data), path.name)


def _purge_asset(
    session,
    asset_id: UUID,
    processed_assets: Set[UUID],
    processed_raw_assets: Set[UUID],
) -> None:
    if asset_id in processed_assets:
        return

    raw_id = (
        session.query(Asset.raw_asset_id)
        .filter(Asset.id == asset_id)
        .scalar()
    )

    session.query(VideoFrame).filter(VideoFrame.asset_id == asset_id).delete(
        synchronize_session=False
    )
    session.query(DocumentChunk).filter(
        DocumentChunk.asset_id == asset_id
    ).delete(synchronize_session=False)
    session.query(Lineage).filter(Lineage.asset_id == asset_id).delete(
        synchronize_session=False
    )
    session.query(Asset).filter(Asset.id == asset_id).delete(
        synchronize_session=False
    )
    processed_assets.add(asset_id)

    if raw_id and raw_id not in processed_raw_assets:
        session.query(AssetRaw).filter(AssetRaw.id == raw_id).delete(
            synchronize_session=False
        )
        processed_raw_assets.add(raw_id)


def _ingest_document(
    session,
    storage,
    file_path: Path,
    cluster_id,
) -> Dict[str, object]:
    request_id = str(uuid4())
    raw_uri = _store_raw_file(storage, request_id, file_path)

    asset_raw = AssetRaw(
        request_id=request_id,
        part_id=file_path.stem,
        uri=raw_uri,
        size_bytes=file_path.stat().st_size,
        content_type=_guess_mime_type(file_path),
    )
    session.add(asset_raw)
    session.flush()

    tags = [file_path.parent.name, "real-document"]
    asset = Asset(
        kind="document",
        uri=raw_uri,
        size_bytes=file_path.stat().st_size,
        content_type=asset_raw.content_type,
        owner="realdata",
        status="queued",
        raw_asset_id=asset_raw.id,
        cluster_id=cluster_id,
        tags=tags,
    )
    session.add(asset)
    asset.metadata = {"source_path": str(file_path)}
    session.commit()

    service = DocumentService(session, storage)
    result = service.process_asset(asset.id, request_id)

    # Grab a representative chunk for later search queries
    first_chunk = (
        session.query(DocumentChunk)
        .filter(DocumentChunk.asset_id == asset.id)
        .order_by(DocumentChunk.chunk_index)
        .first()
    )
    chunk_preview = first_chunk.text[:256] if first_chunk else ""

    derived_assets = (
        session.query(Asset)
        .filter(Asset.parent_asset_id == asset.id)
        .all()
    )
    derived_asset_ids = [child.id for child in derived_assets]
    derived_raw_ids = [child.raw_asset_id for child in derived_assets if child.raw_asset_id]
    derived_cluster_ids = [child.cluster_id for child in derived_assets if child.cluster_id]

    return {
        "asset_id": asset.id,
        "asset_raw_id": asset_raw.id,
        "request_id": request_id,
        "cluster_id": asset.cluster_id,
        "tags": tags,
        "chunk_preview": chunk_preview,
        "chunk_count": result["chunk_count"],
        "derived_assets": derived_asset_ids,
        "derived_raw_assets": derived_raw_ids,
        "derived_clusters": derived_cluster_ids,
    }


def _ingest_media(session, storage, file_path: Path) -> Dict[str, object]:
    request_id = str(uuid4())
    raw_uri = _store_raw_file(storage, request_id, file_path)

    asset_raw = AssetRaw(
        request_id=request_id,
        part_id=file_path.stem,
        uri=raw_uri,
        size_bytes=file_path.stat().st_size,
        content_type=_guess_mime_type(file_path),
    )
    session.add(asset_raw)
    session.flush()

    tags = [file_path.parent.name, "real-media"]
    asset = Asset(
        kind="media",
        uri=raw_uri,
        size_bytes=file_path.stat().st_size,
        content_type=asset_raw.content_type,
        owner="realdata",
        status="queued",
        raw_asset_id=asset_raw.id,
        tags=tags,
    )
    session.add(asset)
    session.commit()

    service = MediaService(session, storage)
    media_result = service.process_asset(asset.id, request_id)

    session.refresh(asset)
    return {
        "asset_id": asset.id,
        "asset_raw_id": asset_raw.id,
        "request_id": request_id,
        "cluster_id": asset.cluster_id,
        "tags": tags,
        "metadata": asset.metadata,
        "result": media_result,
    }


def _ingest_json_asset(
    session,
    storage,
    file_path: Path,
    query_processor: QueryProcessor,
) -> Dict[str, object]:
    request_id = str(uuid4())
    raw_uri = _store_raw_file(storage, request_id, file_path)

    asset_raw = AssetRaw(
        request_id=request_id,
        part_id=file_path.stem,
        uri=raw_uri,
        size_bytes=file_path.stat().st_size,
        content_type="application/json",
    )
    session.add(asset_raw)
    session.flush()

    text_payload = file_path.read_text(encoding="utf-8", errors="ignore")
    snippet = text_payload[:512] or file_path.stem
    embedding = query_processor.encode_text_query(snippet)

    tags = [file_path.parent.name, "real-json"]
    asset = Asset(
        kind="json",
        uri=raw_uri,
        size_bytes=file_path.stat().st_size,
        content_type="application/json",
        owner="realdata",
        status="done",
        raw_asset_id=asset_raw.id,
        embedding=embedding.tolist(),
        tags=tags,
    )
    session.add(asset)
    asset.metadata = {"source_path": str(file_path)}
    session.commit()

    return {
        "asset_id": asset.id,
        "asset_raw_id": asset_raw.id,
        "request_id": request_id,
        "tags": tags,
        "search_text": snippet,
    }


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.slow
@pytest.mark.usefixtures("real_data_context")
def test_document_chunks_have_expected_embeddings(real_data_context, db_session):
    doc_info = real_data_context["document"]
    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.asset_id == doc_info["asset_id"])
        .all()
    )
    assert chunks, "Document processing should create at least one chunk"
    assert doc_info["chunk_count"] == len(chunks)
    for chunk in chunks:
        assert len(chunk.embedding) == 768, "Chunk embeddings must match schema dimension"


@pytest.mark.slow
@pytest.mark.usefixtures("real_data_context")
def test_chunk_search_respects_tags_and_cluster(real_data_context, db_session):
    doc_info = real_data_context["document"]
    processor = QueryProcessor()
    filters = SearchFilter(
        asset_type="document",
        owner="realdata",
        cluster_id=doc_info["cluster_id"],
        tags=doc_info["tags"],
        min_similarity=0.3,
        limit=5,
    )
    response = processor.unified_search(
        db_session,
        doc_info["chunk_preview"],
        filters,
    )
    assert response.results, "Document chunks should be returned when filters match"

    mismatched_filters = SearchFilter(
        asset_type="document",
        owner="realdata",
        cluster_id=uuid4(),
        tags=["non-existent-tag"],
        min_similarity=0.1,
        limit=5,
    )
    empty_response = processor.unified_search(
        db_session,
        doc_info["chunk_preview"],
        mismatched_filters,
    )
    assert empty_response.total == 0


@pytest.mark.slow
@pytest.mark.usefixtures("real_data_context")
def test_json_assets_use_media_search_path(real_data_context, db_session):
    json_info = real_data_context.get("json")
    if not json_info:
        pytest.skip("No JSON file present in the real dataset")

    processor = QueryProcessor()
    filters = SearchFilter(
        asset_type="json",
        owner="realdata",
        tags=json_info["tags"],
        min_similarity=0.2,
        limit=3,
    )
    response = processor.unified_search(
        db_session,
        json_info["search_text"],
        filters,
    )
    assert any(result.asset_id == str(json_info["asset_id"]) for result in response.results)


@pytest.mark.slow
@pytest.mark.usefixtures("real_data_context")
def test_video_frame_diversity(real_data_context, db_session):
    video_info = real_data_context.get("video")
    if not video_info:
        pytest.skip("No video sample found in the real dataset")

    frames = (
        db_session.query(VideoFrame)
        .filter(VideoFrame.asset_id == video_info["asset_id"])
        .order_by(VideoFrame.frame_idx)
        .all()
    )
    assert len(frames) >= 1, "Video ingestion should capture keyframes"
    timestamps = [frame.timestamp_ms for frame in frames]
    assert timestamps == sorted(timestamps), "Frame timestamps must be monotonic"
    for frame in frames:
        assert len(frame.embedding) == 512


@pytest.mark.slow
@pytest.mark.usefixtures("real_data_context")
def test_media_metadata_contains_dimensions(real_data_context, db_session):
    image_info = real_data_context["image"]
    asset = (
        db_session.query(Asset)
        .filter(Asset.id == image_info["asset_id"])
        .first()
    )
    assert asset and asset.metadata, "Processed media should include metadata"
    assert asset.metadata.get("width"), "Width should be captured"
    assert asset.metadata.get("height"), "Height should be captured"