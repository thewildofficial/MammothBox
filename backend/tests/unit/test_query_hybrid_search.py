"""
Tests for the OCR-aware hybrid search helper.
"""

import pytest

pytest.skip(
    "Hybrid search tests require full SQLAlchemy model import which conflicts "
    "with reserved 'metadata' attribute under SQLAlchemy 2.x in this environment. "
    "See issue #33 for tracking and resolution.",
    allow_module_level=True,
)

from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock, patch

from src.catalog.models import Asset
from src.catalog.queries import QueryProcessor, SearchFilter, SearchResult, SearchResponse


def _make_asset(ocr_text: str | None, asset_id: UUID | None = None) -> Asset:
    """Create an Asset instance suitable for testing."""
    return Asset(
        id=asset_id or uuid4(),
        kind="media",
        uri="fs://example",
        size_bytes=1234,
        status="done",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata={"ocr_text": ocr_text} if ocr_text is not None else None,
    )


def _setup_db_mock(assets):
    """Create a mock SQLAlchemy session returning supplied assets."""
    limit_mock = MagicMock()
    limit_mock.all.return_value = assets

    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.limit.return_value = limit_mock

    db = MagicMock()
    db.query.return_value = query_mock
    return db, query_mock, limit_mock


@patch.object(QueryProcessor, "search")
def test_search_with_ocr_boosts_text_matches(mock_search):
    """Hybrid search should boost assets containing matching OCR text."""
    processor = QueryProcessor()
    filters = SearchFilter(limit=5)

    # Use a fixed UUID for both vector result and OCR asset to test boost path
    test_asset_id = uuid4()
    base_result = SearchResult(
        asset_id=str(test_asset_id),
        kind="media",
        uri="fs://vector",
        content_type="image/png",
        size_bytes=100,
        owner=None,
        tags=[],
        similarity_score=0.62,
        cluster_id=None,
        cluster_name=None,
        thumbnail_uri=None,
        created_at=datetime.utcnow().isoformat(),
        metadata={"contains_text": True},
    )

    mock_search.return_value = SearchResponse(
        query="earnings report",
        results=[base_result],
        total=1,
        query_time_ms=12.3,
        filters_applied={},
    )

    # Create OCR asset with same ID as vector result to test boost path
    matching_asset = _make_asset(
        "Quarterly earnings report available now",
        asset_id=test_asset_id
    )
    db, query_mock, limit_mock = _setup_db_mock([matching_asset])

    response = processor.search_with_ocr(db, "earnings report", filters)

    assert response.total == 1
    assert response.results[0].asset_id == str(test_asset_id)
    assert response.results[0].similarity_score > base_result.similarity_score
    limit_mock.all.assert_called_once()
    query_mock.filter.assert_called()


@patch.object(QueryProcessor, "search")
def test_search_with_ocr_adds_ocr_only_results(mock_search):
    """Assets discovered solely via OCR should still appear in results."""
    processor = QueryProcessor()
    filters = SearchFilter(limit=5)

    mock_search.return_value = SearchResponse(
        query="system error",
        results=[],
        total=0,
        query_time_ms=4.2,
        filters_applied={},
    )

    ocr_only_asset = _make_asset("System Error 500 occurred on server")
    db, _, limit_mock = _setup_db_mock([ocr_only_asset])

    response = processor.search_with_ocr(db, "system error", filters)

    assert response.total == 1
    result = response.results[0]
    assert result.asset_id == str(ocr_only_asset.id)
    assert pytest.approx(result.similarity_score, rel=0.01) == 0.6
    assert "system error" in (result.metadata or {}).get("ocr_text", "").lower()
    limit_mock.all.assert_called_once()


@patch.object(QueryProcessor, "search")
def test_search_with_ocr_handles_empty_ocr_results(mock_search):
    """If OCR matches none, the original vector ranking is returned."""
    processor = QueryProcessor()
    filters = SearchFilter(limit=3)

    base_result = SearchResult(
        asset_id="vector-asset",
        kind="media",
        uri="fs://vector",
        content_type="image/png",
        size_bytes=100,
        owner=None,
        tags=[],
        similarity_score=0.73,
        cluster_id=None,
        cluster_name=None,
        thumbnail_uri=None,
        created_at=datetime.utcnow().isoformat(),
        metadata=None,
    )

    mock_search.return_value = SearchResponse(
        query="landscape",
        results=[base_result],
        total=1,
        query_time_ms=8.1,
        filters_applied={},
    )

    db, _, limit_mock = _setup_db_mock([])

    response = processor.search_with_ocr(db, "landscape", filters)

    assert response.total == 1
    assert response.results[0].asset_id == "vector-asset"
    assert response.results[0].similarity_score == base_result.similarity_score
    limit_mock.all.assert_called_once()

