"""
Query processing and semantic search for asset retrieval.

This module handles:
- Text query encoding using CLIP
- Vector similarity search with pgvector
- Result filtering and ranking
- Query validation and optimization
"""

import logging
import time
from typing import List, Optional, Dict, Any
from uuid import UUID
from dataclasses import dataclass

import numpy as np
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from src.catalog.models import Asset, Cluster
from src.media.embedder import MediaEmbedder, EmbeddingError
from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class QueryError(Exception):
    """Exception raised during query processing."""
    pass


@dataclass
class SearchFilter:
    """Search filter parameters."""
    asset_type: Optional[str] = None  # 'media' or 'json'
    owner: Optional[str] = None
    cluster_id: Optional[UUID] = None
    tags: Optional[List[str]] = None
    min_similarity: float = 0.5
    limit: int = 10


@dataclass
class SearchResult:
    """Individual search result with metadata."""
    asset_id: str
    kind: str
    uri: str
    content_type: Optional[str]
    size_bytes: int
    owner: Optional[str]
    tags: List[str]
    similarity_score: float
    cluster_id: Optional[str]
    cluster_name: Optional[str]
    thumbnail_uri: Optional[str]
    created_at: str
    metadata: Optional[Dict[str, Any]]


@dataclass
class SearchResponse:
    """Complete search response with metadata."""
    query: str
    results: List[SearchResult]
    total: int
    query_time_ms: float
    filters_applied: Dict[str, Any]


class QueryProcessor:
    """
    Process text queries and perform semantic search.

    Uses CLIP text encoder to convert queries to embeddings,
    then performs ANN search using pgvector HNSW indexes.
    """

    def __init__(self):
        """Initialize query processor."""
        self.settings = get_settings()
        self._embedder = None

    def _get_embedder(self) -> MediaEmbedder:
        """Lazy load embedder (for text encoding)."""
        if self._embedder is None:
            self._embedder = MediaEmbedder()
        return self._embedder

    def validate_query(self, query: str) -> str:
        """
        Validate and normalize query text.

        Args:
            query: Raw query string

        Returns:
            Normalized query string

        Raises:
            QueryError: If query is invalid
        """
        if not query:
            raise QueryError("Query cannot be empty")

        # Strip whitespace
        query = query.strip()

        # Check length
        if len(query) < 2:
            raise QueryError("Query must be at least 2 characters")

        if len(query) > 500:
            raise QueryError("Query must be less than 500 characters")

        return query

    def encode_text_query(self, query: str) -> np.ndarray:
        """
        Encode text query to embedding vector using CLIP text encoder.

        Args:
            query: Text query string

        Returns:
            512-dimensional normalized embedding vector

        Raises:
            QueryError: If encoding fails
        """
        try:
            embedder = self._get_embedder()

            # Load model if not loaded
            if embedder._model is None:
                embedder._load_model()

            # Encode text query
            embedding = embedder._model.encode(
                query,
                batch_size=1,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )

            # Ensure 1D array
            if embedding.ndim > 1:
                embedding = embedding.flatten()

            # Validate dimension
            if len(embedding) != 512:
                raise QueryError(
                    f"Unexpected embedding dimension: {len(embedding)}")

            return embedding.astype(np.float32)

        except EmbeddingError as e:
            raise QueryError(f"Failed to encode query: {e}") from e
        except Exception as e:
            logger.error(f"Query encoding error: {e}")
            raise QueryError(f"Failed to encode query: {e}") from e

    def build_search_filters(
        self,
        asset_type: Optional[str] = None,
        owner: Optional[str] = None,
        cluster_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None
    ) -> List:
        """
        Build SQLAlchemy filter expressions.

        Args:
            asset_type: Filter by 'media' or 'json'
            owner: Filter by owner
            cluster_id: Filter by cluster
            tags: Filter by tags (any match)

        Returns:
            List of filter expressions
        """
        filters = []

        # Only search assets with embeddings (processed media)
        filters.append(Asset.embedding.isnot(None))

        # Asset type filter
        if asset_type:
            if asset_type not in ['media', 'json']:
                raise QueryError(
                    f"Invalid asset type: {asset_type}. Must be 'media' or 'json'")
            filters.append(Asset.kind == asset_type)

        # Owner filter
        if owner:
            filters.append(Asset.owner == owner)

        # Cluster filter
        if cluster_id:
            filters.append(Asset.cluster_id == cluster_id)

        # Tags filter (any tag matches)
        if tags:
            # PostgreSQL array overlap operator
            filters.append(Asset.tags.overlap(tags))

        return filters

    def search(
        self,
        db: Session,
        query: str,
        filters: SearchFilter
    ) -> SearchResponse:
        """
        Perform semantic search with filters.

        Args:
            db: Database session
            query: Text query string
            filters: Search filters

        Returns:
            SearchResponse with ranked results

        Raises:
            QueryError: If search fails
        """
        start_time = time.time()

        try:
            # Validate query
            normalized_query = self.validate_query(query)

            # Encode query to embedding
            query_embedding = self.encode_text_query(normalized_query)

            # Build filter conditions
            filter_conditions = self.build_search_filters(
                asset_type=filters.asset_type,
                owner=filters.owner,
                cluster_id=filters.cluster_id,
                tags=filters.tags
            )

            # Build base query
            # Use pgvector cosine distance operator (<=>)
            # Lower distance = higher similarity
            # Calculate similarity as label
            similarity_expr = (
                1 - (Asset.embedding.cosine_distance(query_embedding) / 2)).label('similarity')

            query_obj = db.query(
                Asset,
                similarity_expr
            )

            # Apply filters
            query_obj = query_obj.filter(and_(*filter_conditions))

            # Filter by similarity threshold
            # Note: We compute similarity after distance, so we need to use the formula
            # similarity >= threshold => distance <= 2 * (1 - threshold)
            max_distance = 2 * (1 - filters.min_similarity)
            query_obj = query_obj.filter(
                Asset.embedding.cosine_distance(
                    query_embedding) <= max_distance
            )

            # Sort by similarity (descending)
            query_obj = query_obj.order_by(desc('similarity'))

            # Limit results
            query_obj = query_obj.limit(min(filters.limit, 100))  # Max 100

            # Execute query
            results_raw = query_obj.all()

            # Get cluster info for results (batch query)
            cluster_ids = [asset.cluster_id for asset,
                           _ in results_raw if asset.cluster_id]
            clusters_map = {}
            if cluster_ids:
                clusters = db.query(Cluster).filter(
                    Cluster.id.in_(cluster_ids)).all()
                clusters_map = {c.id: c for c in clusters}

            # Format results
            results = []
            for asset, similarity in results_raw:
                cluster = clusters_map.get(
                    asset.cluster_id) if asset.cluster_id else None

                result = SearchResult(
                    asset_id=str(asset.id),
                    kind=asset.kind,
                    uri=asset.uri,
                    content_type=asset.content_type,
                    size_bytes=asset.size_bytes,
                    owner=asset.owner,
                    tags=asset.tags or [],
                    similarity_score=round(float(similarity), 4),
                    cluster_id=str(
                        asset.cluster_id) if asset.cluster_id else None,
                    cluster_name=cluster.name if cluster else None,
                    thumbnail_uri=self._get_thumbnail_uri(asset),
                    created_at=asset.created_at.isoformat(),
                    metadata=asset.metadata
                )
                results.append(result)

            # Calculate query time
            query_time_ms = (time.time() - start_time) * 1000

            # Build response
            response = SearchResponse(
                query=normalized_query,
                results=results,
                total=len(results),
                query_time_ms=round(query_time_ms, 2),
                filters_applied={
                    'type': filters.asset_type,
                    'owner': filters.owner,
                    'cluster_id': str(filters.cluster_id) if filters.cluster_id else None,
                    'tags': filters.tags,
                    'min_similarity': filters.min_similarity,
                    'limit': filters.limit
                }
            )

            logger.info(
                f"Search completed: query='{normalized_query}', "
                f"results={len(results)}, time={query_time_ms:.2f}ms"
            )

            return response

        except QueryError:
            raise
        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            raise QueryError(f"Search failed: {e}") from e

    def _get_thumbnail_uri(self, asset: Asset) -> Optional[str]:
        """
        Generate thumbnail URI for asset.

        Args:
            asset: Asset object

        Returns:
            Thumbnail URI or None
        """
        # For media assets, construct derived thumbnail path
        if asset.kind == 'media' and asset.cluster_id:
            # Thumbnail stored at: media/derived/{cluster_id}/{asset_id}/thumb.jpg
            return f"fs://derived/{asset.cluster_id}/{asset.id}/thumb.jpg"
        return None

    def search_by_tags_only(
        self,
        db: Session,
        tags: List[str],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Simple tag-based search without vector similarity.

        Useful for quick filtering when no text query provided.

        Args:
            db: Database session
            tags: Tags to search for
            limit: Max results

        Returns:
            List of matching assets
        """
        try:
            # Query assets with overlapping tags
            results = db.query(Asset).filter(
                Asset.tags.overlap(tags)
            ).limit(limit).all()

            return [
                {
                    'id': str(asset.id),
                    'kind': asset.kind,
                    'uri': asset.uri,
                    'tags': asset.tags or [],
                    'owner': asset.owner,
                    'created_at': asset.created_at.isoformat()
                }
                for asset in results
            ]
        except Exception as e:
            logger.error(f"Tag search error: {e}")
            raise QueryError(f"Tag search failed: {e}") from e
