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
from typing import List, Optional, Dict, Any, Callable
from uuid import UUID
from dataclasses import dataclass
from functools import wraps

import numpy as np
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from src.catalog.models import Asset, Cluster, DocumentChunk
from src.documents.embedder import DocumentEmbedder, DocumentEmbeddingError
from src.media.embedder import MediaEmbedder, EmbeddingError
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Performance monitoring threshold (milliseconds)
SLOW_QUERY_THRESHOLD_MS = 150


def log_query_time(func: Callable) -> Callable:
    """
    Decorator to log query execution time and warn on slow queries.
    
    Logs execution time for all decorated functions and emits warnings
    when queries exceed the performance threshold (150ms by default).
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with timing instrumentation
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration_ms = (time.perf_counter() - start) * 1000
        
        logger.info(f"Query {func.__name__} took {duration_ms:.2f}ms")
        
        if duration_ms > SLOW_QUERY_THRESHOLD_MS:
            logger.warning(
                f"SLOW QUERY: {func.__name__} exceeded {SLOW_QUERY_THRESHOLD_MS}ms target "
                f"(took {duration_ms:.2f}ms)"
            )
        
        return result
    return wrapper


class QueryError(Exception):
    """Exception raised during query processing."""
    pass


@dataclass
class SearchFilter:
    """Search filter parameters."""
    asset_type: Optional[str] = None  # 'media', 'document', or 'json'
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
        self._doc_embedder = None

    def _get_embedder(self) -> MediaEmbedder:
        """Lazy load embedder (for text encoding)."""
        if self._embedder is None:
            self._embedder = MediaEmbedder()
        return self._embedder

    def _get_document_embedder(self) -> DocumentEmbedder:
        """Lazy load document encoder."""
        if self._doc_embedder is None:
            self._doc_embedder = DocumentEmbedder(self.settings.text_embedding_model)
        return self._doc_embedder

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

    def encode_document_query(self, query: str) -> np.ndarray:
        """Encode text query for document chunk search."""
        try:
            embedder = self._get_document_embedder()
            return embedder.embed_query(query)
        except DocumentEmbeddingError as e:
            raise QueryError(f"Failed to encode document query: {e}") from e
        except Exception as e:
            logger.error(f"Document query encoding error: {e}")
            raise QueryError(f"Failed to encode document query: {e}") from e

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
            if asset_type not in ['media', 'json', 'document']:
                raise QueryError(
                    f"Invalid asset type: {asset_type}. Must be 'media', 'document', or 'json'")
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

    @log_query_time
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

    @log_query_time
    def unified_search(
        self,
        db: Session,
        query: str,
        filters: SearchFilter,
    ) -> SearchResponse:
        """Search across media assets and document chunks."""
        start_time = time.time()
        normalized_query = self.validate_query(query)
        combined_results: List[SearchResult] = []

        # Media (CLIP) search
        if filters.asset_type in (None, "media"):
            media_response = self.search(db, normalized_query, filters)
            combined_results.extend(media_response.results)

        # JSON assets should reuse the media search path to ensure parity
        if filters.asset_type == "json":
            media_response = self.search(db, normalized_query, filters)
            combined_results.extend(media_response.results)

        # Document chunk search
        if filters.asset_type in (None, "document"):
            doc_embedding = self.encode_document_query(normalized_query)
            similarity_expr = (
                1 - (DocumentChunk.embedding.cosine_distance(doc_embedding) / 2)
            ).label("similarity")

            chunk_query = (
                db.query(DocumentChunk, Asset, similarity_expr)
                .join(Asset, Asset.id == DocumentChunk.asset_id)
                .filter(DocumentChunk.embedding.isnot(None))
            )

            if filters.owner:
                chunk_query = chunk_query.filter(Asset.owner == filters.owner)

            if filters.cluster_id:
                chunk_query = chunk_query.filter(
                    Asset.cluster_id == filters.cluster_id
                )

            if filters.tags:
                chunk_query = chunk_query.filter(Asset.tags.overlap(filters.tags))

            max_distance = 2 * (1 - filters.min_similarity)
            chunk_query = chunk_query.filter(
                DocumentChunk.embedding.cosine_distance(doc_embedding) <= max_distance
            )

            chunk_query = chunk_query.order_by(desc("similarity")).limit(filters.limit)
            chunk_rows = chunk_query.all()

            for chunk, asset, similarity in chunk_rows:
                metadata = dict(asset.metadata) if asset.metadata else {}
                metadata.update(
                    {
                        "chunk_text": chunk.text,
                        "chunk_parent_heading": chunk.parent_heading,
                        "chunk_page_number": chunk.page_number,
                        "source_asset_id": str(asset.id),
                    }
                )

                combined_results.append(
                    SearchResult(
                        asset_id=str(chunk.id),
                        kind="document_chunk",
                        uri=asset.uri,
                        content_type=asset.content_type,
                        size_bytes=asset.size_bytes,
                        owner=asset.owner,
                        tags=asset.tags or [],
                        similarity_score=round(float(similarity), 4),
                        cluster_id=None,
                        cluster_name=None,
                        thumbnail_uri=None,
                        created_at=asset.created_at.isoformat(),
                        metadata=metadata,
                    )
                )

        sorted_results = sorted(
            combined_results, key=lambda r: r.similarity_score, reverse=True
        )[: filters.limit]

        total_time_ms = (time.time() - start_time) * 1000
        return SearchResponse(
            query=normalized_query,
            results=sorted_results,
            total=len(sorted_results),
            query_time_ms=round(total_time_ms, 2),
            filters_applied={
                "type": filters.asset_type,
                "owner": filters.owner,
                "cluster_id": str(filters.cluster_id) if filters.cluster_id else None,
                "tags": filters.tags,
                "min_similarity": filters.min_similarity,
                "limit": filters.limit,
            },
        )

    @log_query_time
    def search_in_document_images(
        self,
        db: Session,
        query: str,
        document_id: UUID,
        limit: int = 10,
    ) -> List[SearchResult]:
        """Search media assets derived from a specific document."""
        normalized_query = self.validate_query(query)
        query_embedding = self.encode_text_query(normalized_query)

        similarity_expr = (
            1 - (Asset.embedding.cosine_distance(query_embedding) / 2)
        ).label("similarity")

        query_obj = (
            db.query(Asset, similarity_expr)
            .filter(Asset.parent_asset_id == document_id)
            .filter(Asset.embedding.isnot(None))
            .order_by(desc("similarity"))
            .limit(limit)
        )

        results = []
        for asset, similarity in query_obj.all():
            results.append(
                SearchResult(
                    asset_id=str(asset.id),
                    kind=asset.kind,
                    uri=asset.uri,
                    content_type=asset.content_type,
                    size_bytes=asset.size_bytes,
                    owner=asset.owner,
                    tags=asset.tags or [],
                    similarity_score=round(float(similarity), 4),
                    cluster_id=str(asset.cluster_id) if asset.cluster_id else None,
                    cluster_name=None,
                    thumbnail_uri=self._get_thumbnail_uri(asset),
                    created_at=asset.created_at.isoformat(),
                    metadata=asset.metadata,
                )
            )

        return results

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

    @log_query_time
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
    
    @log_query_time
    def search_with_ocr(
        self,
        db: Session,
        query: str,
        filters: SearchFilter
    ) -> SearchResponse:
        """
        Hybrid search combining vector similarity and OCR text matching.
        
        This method performs a two-stage search:
        1. Vector similarity search using CLIP embeddings
        2. Keyword matching in OCR-extracted text
        
        Results from both stages are merged and re-ranked, with OCR matches
        receiving a relevance boost for better text-based search.
        
        Args:
            db: Database session
            query: Text query string
            filters: Search filters
            
        Returns:
            SearchResponse with hybrid-ranked results
        """
        import time
        start_time = time.perf_counter()
        
        try:
            # Stage 1: Vector similarity search
            vector_response = self.search(db, query, filters)
            vector_results = {r.asset_id: r for r in vector_response.results}
            
            # Stage 2: OCR text keyword matching
            # Build filter for assets with OCR text
            filter_conditions = self.build_search_filters(
                asset_type=filters.asset_type,
                owner=filters.owner,
                cluster_id=filters.cluster_id,
                tags=filters.tags
            )
            
            # Add OCR text filter using JSONB containment
            # Search for query text in metadata.ocr_text field (case-insensitive)
            ocr_query = db.query(Asset).filter(and_(*filter_conditions))
            ocr_query = ocr_query.filter(
                Asset.metadata['ocr_text'].astext.ilike(f"%{query}%")
            )
            ocr_assets = ocr_query.limit(filters.limit * 2).all()
            
            # Merge results with OCR boost
            merged_results = {}
            
            # Add vector results
            for asset_id, result in vector_results.items():
                merged_results[asset_id] = result
            
            # Add/boost OCR results
            for asset in ocr_assets:
                asset_id = str(asset.id)
                if asset_id in merged_results:
                    # Boost existing result
                    result = merged_results[asset_id]
                    # Apply OCR boost (increase similarity score)
                    boosted_score = min(1.0, result.similarity_score + 0.15)
                    merged_results[asset_id] = SearchResult(
                        asset_id=result.asset_id,
                        kind=result.kind,
                        uri=result.uri,
                        content_type=result.content_type,
                        size_bytes=result.size_bytes,
                        owner=result.owner,
                        tags=result.tags,
                        similarity_score=boosted_score,
                        cluster_id=result.cluster_id,
                        cluster_name=result.cluster_name,
                        thumbnail_uri=result.thumbnail_uri,
                        created_at=result.created_at,
                        metadata=result.metadata
                    )
                else:
                    # Add new OCR-only result with baseline similarity
                    cluster = None
                    if asset.cluster_id:
                        cluster = db.query(Cluster).filter(
                            Cluster.id == asset.cluster_id
                        ).first()
                    
                    merged_results[asset_id] = SearchResult(
                        asset_id=asset_id,
                        kind=asset.kind,
                        uri=asset.uri,
                        content_type=asset.content_type,
                        size_bytes=asset.size_bytes,
                        owner=asset.owner,
                        tags=asset.tags or [],
                        similarity_score=0.6,  # Baseline score for OCR matches
                        cluster_id=str(asset.cluster_id) if asset.cluster_id else None,
                        cluster_name=cluster.name if cluster else None,
                        thumbnail_uri=self._get_thumbnail_uri(asset),
                        created_at=asset.created_at.isoformat(),
                        metadata=asset.metadata
                    )
            
            # Sort by similarity score (descending) and limit
            sorted_results = sorted(
                merged_results.values(),
                key=lambda x: x.similarity_score,
                reverse=True
            )[:filters.limit]
            
            # Calculate total hybrid search time (not just vector search)
            total_time_ms = (time.perf_counter() - start_time) * 1000
            
            return SearchResponse(
                query=query,
                results=sorted_results,
                total=len(sorted_results),
                query_time_ms=round(total_time_ms, 2),
                filters_applied=filters.__dict__
            )
            
        except QueryError:
            raise
        except Exception as e:
            logger.error(f"Hybrid OCR search error: {e}", exc_info=True)
            raise QueryError(f"Hybrid search failed: {e}") from e
