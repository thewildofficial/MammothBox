"""
Tests for search and query processing functionality.

Tests semantic search, query encoding, filtering, and result formatting.
"""

import pytest
import numpy as np
from uuid import uuid4, UUID
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from src.catalog.queries import (
    QueryProcessor,
    SearchFilter,
    QueryError,
    SearchResult,
    SearchResponse
)
from src.catalog.models import Asset, Cluster


class TestQueryValidation:
    """Test query validation and normalization."""

    def test_validate_empty_query(self):
        """Empty query should raise QueryError."""
        processor = QueryProcessor()

        with pytest.raises(QueryError, match="Query cannot be empty"):
            processor.validate_query("")

    def test_validate_whitespace_query(self):
        """Whitespace-only query should raise QueryError."""
        processor = QueryProcessor()

        with pytest.raises(QueryError, match="at least 2 characters"):
            processor.validate_query("   ")

    def test_validate_short_query(self):
        """Query < 2 characters should raise QueryError."""
        processor = QueryProcessor()

        with pytest.raises(QueryError, match="at least 2 characters"):
            processor.validate_query("a")

    def test_validate_long_query(self):
        """Query > 500 characters should raise QueryError."""
        processor = QueryProcessor()
        long_query = "a" * 501

        with pytest.raises(QueryError, match="less than 500 characters"):
            processor.validate_query(long_query)

    def test_validate_normal_query(self):
        """Valid query should be normalized."""
        processor = QueryProcessor()

        result = processor.validate_query("  dog playing  ")
        assert result == "dog playing"

    def test_validate_unicode_query(self):
        """Unicode query should be accepted."""
        processor = QueryProcessor()

        result = processor.validate_query("猫 🐱")
        assert result == "猫 🐱"


class TestQueryEncoding:
    """Test text query encoding to embeddings."""

    @patch('src.catalog.queries.MediaEmbedder')
    def test_encode_text_query_success(self, mock_embedder_class):
        """Successful query encoding."""
        # Mock embedder
        mock_model = Mock()
        mock_model.encode.return_value = np.random.randn(
            512).astype(np.float32)

        mock_embedder = Mock()
        mock_embedder._model = mock_model
        mock_embedder._load_model = Mock()
        mock_embedder_class.return_value = mock_embedder

        processor = QueryProcessor()
        processor._embedder = mock_embedder

        embedding = processor.encode_text_query("sunset beach")

        assert embedding.shape == (512,)
        assert embedding.dtype == np.float32
        mock_model.encode.assert_called_once()

    @patch('src.catalog.queries.MediaEmbedder')
    def test_encode_text_query_wrong_dimension(self, mock_embedder_class):
        """Query encoding with wrong dimension should raise error."""
        # Mock embedder returning wrong dimension
        mock_model = Mock()
        mock_model.encode.return_value = np.random.randn(
            256).astype(np.float32)

        mock_embedder = Mock()
        mock_embedder._model = mock_model
        mock_embedder._load_model = Mock()
        mock_embedder_class.return_value = mock_embedder

        processor = QueryProcessor()
        processor._embedder = mock_embedder

        with pytest.raises(QueryError, match="Unexpected embedding dimension"):
            processor.encode_text_query("test")

    @patch('src.catalog.queries.MediaEmbedder')
    def test_encode_text_query_model_error(self, mock_embedder_class):
        """Query encoding failure should raise QueryError."""
        mock_embedder = Mock()
        mock_embedder._model = None
        mock_embedder._load_model.side_effect = Exception("Model load failed")
        mock_embedder_class.return_value = mock_embedder

        processor = QueryProcessor()
        processor._embedder = mock_embedder

        with pytest.raises(QueryError, match="Failed to encode query"):
            processor.encode_text_query("test")


class TestSearchFilters:
    """Test search filter building."""

    def test_build_filters_no_filters(self):
        """No filters should only check for embeddings."""
        processor = QueryProcessor()

        filters = processor.build_search_filters()

        assert len(filters) == 1  # Only embedding check

    def test_build_filters_asset_type(self):
        """Asset type filter."""
        processor = QueryProcessor()

        filters = processor.build_search_filters(asset_type='media')

        assert len(filters) == 2  # Embedding + type

    def test_build_filters_invalid_asset_type(self):
        """Invalid asset type should raise error."""
        processor = QueryProcessor()

        with pytest.raises(QueryError, match="Invalid asset type"):
            processor.build_search_filters(asset_type='invalid')

    def test_build_filters_owner(self):
        """Owner filter."""
        processor = QueryProcessor()

        filters = processor.build_search_filters(owner='user123')

        assert len(filters) == 2  # Embedding + owner

    def test_build_filters_cluster(self):
        """Cluster filter."""
        processor = QueryProcessor()
        cluster_id = uuid4()

        filters = processor.build_search_filters(cluster_id=cluster_id)

        assert len(filters) == 2  # Embedding + cluster

    def test_build_filters_tags(self):
        """Tags filter."""
        processor = QueryProcessor()

        filters = processor.build_search_filters(tags=['cat', 'animal'])

        assert len(filters) == 2  # Embedding + tags

    def test_build_filters_all(self):
        """All filters combined."""
        processor = QueryProcessor()
        cluster_id = uuid4()

        filters = processor.build_search_filters(
            asset_type='media',
            owner='user123',
            cluster_id=cluster_id,
            tags=['cat', 'animal']
        )

        assert len(filters) == 5  # Embedding + all filters


class TestSearchExecution:
    """Test search execution and result formatting."""

    @patch('src.catalog.queries.MediaEmbedder')
    def test_search_basic(self, mock_embedder_class):
        """Basic search with results."""
        # Mock embedder
        mock_model = Mock()
        mock_model.encode.return_value = np.random.randn(
            512).astype(np.float32)

        mock_embedder = Mock()
        mock_embedder._model = mock_model
        mock_embedder._load_model = Mock()
        mock_embedder_class.return_value = mock_embedder

        # Mock database session
        mock_db = Mock()

        # Mock asset with no cluster (to avoid cluster query)
        mock_asset = Mock(spec=Asset)
        mock_asset.id = uuid4()
        mock_asset.kind = 'media'
        mock_asset.uri = 'fs://media/test.jpg'
        mock_asset.content_type = 'image/jpeg'
        mock_asset.size_bytes = 1024
        mock_asset.owner = 'user1'
        mock_asset.tags = ['cat', 'animal']
        mock_asset.cluster_id = None  # No cluster to avoid cluster query complexity
        mock_asset.created_at = datetime.utcnow()
        mock_asset.metadata = {'test': 'data'}

        # Mock query result (Asset, similarity)
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [(mock_asset, 0.85)]

        mock_db.query.return_value = mock_query

        # Execute search
        processor = QueryProcessor()
        processor._embedder = mock_embedder

        filters = SearchFilter(limit=10)
        response = processor.search(mock_db, "cat", filters)

        # Verify response
        assert isinstance(response, SearchResponse)
        assert response.query == "cat"
        assert response.total == 1
        assert len(response.results) == 1
        assert response.results[0].similarity_score == 0.85
        assert response.query_time_ms > 0

    @patch('src.catalog.queries.MediaEmbedder')
    def test_search_no_results(self, mock_embedder_class):
        """Search with no results."""
        # Mock embedder
        mock_model = Mock()
        mock_model.encode.return_value = np.random.randn(
            512).astype(np.float32)

        mock_embedder = Mock()
        mock_embedder._model = mock_model
        mock_embedder._load_model = Mock()
        mock_embedder_class.return_value = mock_embedder

        # Mock database session
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        mock_db.query.return_value = mock_query

        # Execute search
        processor = QueryProcessor()
        processor._embedder = mock_embedder

        filters = SearchFilter(limit=10)
        response = processor.search(mock_db, "unicorn", filters)

        # Verify response
        assert response.total == 0
        assert len(response.results) == 0

    @patch('src.catalog.queries.MediaEmbedder')
    def test_search_with_cluster_info(self, mock_embedder_class):
        """Search results should include cluster information."""
        # Mock embedder
        mock_model = Mock()
        mock_model.encode.return_value = np.random.randn(
            512).astype(np.float32)

        mock_embedder = Mock()
        mock_embedder._model = mock_model
        mock_embedder._load_model = Mock()
        mock_embedder_class.return_value = mock_embedder

        # Mock database session
        cluster_id = uuid4()
        mock_cluster = Mock(spec=Cluster)
        mock_cluster.id = cluster_id
        mock_cluster.name = "Cats"

        mock_asset = Mock(spec=Asset)
        mock_asset.id = uuid4()
        mock_asset.kind = 'media'
        mock_asset.uri = 'fs://media/test.jpg'
        mock_asset.content_type = 'image/jpeg'
        mock_asset.size_bytes = 1024
        mock_asset.owner = 'user1'
        mock_asset.tags = ['cat']
        mock_asset.cluster_id = cluster_id
        mock_asset.created_at = datetime.utcnow()
        mock_asset.metadata = {}

        mock_db = Mock()

        # Setup query mocks
        asset_query = Mock()
        asset_query.filter.return_value = asset_query
        asset_query.order_by.return_value = asset_query
        asset_query.limit.return_value = asset_query
        asset_query.all.return_value = [(mock_asset, 0.9)]

        cluster_query = Mock()
        cluster_query.filter.return_value = cluster_query
        # Cluster query returns list of cluster objects, not tuples
        # Mock db.query to return different mocks based on argument
        cluster_query.all.return_value = [mock_cluster]

        def query_side_effect(model, *args):
            if len(args) > 0:  # Asset query with similarity
                return asset_query
            elif model == Cluster:
                return cluster_query
            return asset_query

        mock_db.query.side_effect = query_side_effect

        # Execute search
        processor = QueryProcessor()
        processor._embedder = mock_embedder

        filters = SearchFilter(limit=10)
        response = processor.search(mock_db, "cat", filters)

        # Verify cluster info
        assert len(response.results) == 1
        assert response.results[0].cluster_name == "Cats"
        assert response.results[0].cluster_id == str(cluster_id)

    @patch('src.catalog.queries.MediaEmbedder')
    def test_search_invalid_query(self, mock_embedder_class):
        """Invalid query should raise error."""
        mock_db = Mock()
        processor = QueryProcessor()
        filters = SearchFilter(limit=10)

        with pytest.raises(QueryError):
            processor.search(mock_db, "", filters)


class TestThumbnailGeneration:
    """Test thumbnail URI generation."""

    def test_thumbnail_uri_media_with_cluster(self):
        """Media asset with cluster should have thumbnail URI."""
        processor = QueryProcessor()

        asset = Mock(spec=Asset)
        asset.kind = 'media'
        asset.cluster_id = uuid4()
        asset.id = uuid4()

        uri = processor._get_thumbnail_uri(asset)

        assert uri is not None
        assert uri.startswith('fs://derived/')
        assert str(asset.cluster_id) in uri
        assert str(asset.id) in uri
        assert uri.endswith('/thumb.jpg')

    def test_thumbnail_uri_media_without_cluster(self):
        """Media asset without cluster should have no thumbnail."""
        processor = QueryProcessor()

        asset = Mock(spec=Asset)
        asset.kind = 'media'
        asset.cluster_id = None

        uri = processor._get_thumbnail_uri(asset)

        assert uri is None

    def test_thumbnail_uri_json(self):
        """JSON asset should have no thumbnail."""
        processor = QueryProcessor()

        asset = Mock(spec=Asset)
        asset.kind = 'json'
        asset.cluster_id = uuid4()

        uri = processor._get_thumbnail_uri(asset)

        assert uri is None


class TestTagSearch:
    """Test tag-based search without vectors."""

    def test_search_by_tags_only(self):
        """Tag-only search."""
        processor = QueryProcessor()

        # Mock database
        mock_asset = Mock(spec=Asset)
        mock_asset.id = uuid4()
        mock_asset.kind = 'media'
        mock_asset.uri = 'fs://test.jpg'
        mock_asset.tags = ['cat', 'animal']
        mock_asset.owner = 'user1'
        mock_asset.created_at = datetime.utcnow()

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_asset]

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        results = processor.search_by_tags_only(mock_db, ['cat'], limit=10)

        assert len(results) == 1
        assert results[0]['id'] == str(mock_asset.id)
        assert results[0]['tags'] == ['cat', 'animal']

    def test_search_by_tags_no_results(self):
        """Tag search with no matches."""
        processor = QueryProcessor()

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        results = processor.search_by_tags_only(
            mock_db, ['nonexistent'], limit=10)

        assert len(results) == 0


class TestSearchFilter:
    """Test SearchFilter dataclass."""

    def test_default_values(self):
        """SearchFilter should have correct defaults."""
        filter = SearchFilter()

        assert filter.asset_type is None
        assert filter.owner is None
        assert filter.cluster_id is None
        assert filter.tags is None
        assert filter.min_similarity == 0.5
        assert filter.limit == 10

    def test_custom_values(self):
        """SearchFilter with custom values."""
        cluster_id = uuid4()
        filter = SearchFilter(
            asset_type='media',
            owner='user1',
            cluster_id=cluster_id,
            tags=['cat'],
            min_similarity=0.7,
            limit=50
        )

        assert filter.asset_type == 'media'
        assert filter.owner == 'user1'
        assert filter.cluster_id == cluster_id
        assert filter.tags == ['cat']
        assert filter.min_similarity == 0.7
        assert filter.limit == 50


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_search_result_creation(self):
        """Create SearchResult with all fields."""
        result = SearchResult(
            asset_id=str(uuid4()),
            kind='media',
            uri='fs://test.jpg',
            content_type='image/jpeg',
            size_bytes=1024,
            owner='user1',
            tags=['cat'],
            similarity_score=0.85,
            cluster_id=str(uuid4()),
            cluster_name='Cats',
            thumbnail_uri='fs://thumb.jpg',
            created_at='2025-01-01T00:00:00',
            metadata={'test': 'data'}
        )

        assert result.similarity_score == 0.85
        assert result.kind == 'media'
        assert result.cluster_name == 'Cats'
