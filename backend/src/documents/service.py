"""Document processing service."""

from __future__ import annotations

import logging
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, List
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from src.catalog.models import Asset, AssetRaw, DocumentChunk, Lineage
from src.config.settings import get_settings
from src.documents.parser import DocumentParser, DocumentParserError
from src.documents.chunker import DocumentChunker
from src.documents.embedder import DocumentEmbedder, DocumentEmbeddingError
from src.documents.media_extractor import EmbeddedMediaExtractor
from src.media.service import MediaService, MediaServiceError
from src.storage.adapter import StorageAdapter, StorageError

logger = logging.getLogger(__name__)


class DocumentServiceError(Exception):
    """Raised when document processing fails."""


class DocumentService:
    """Coordinate parsing, chunking, and embedding for document assets."""

    def __init__(self, db: Session, storage: StorageAdapter):
        self.db = db
        self.storage = storage
        self.settings = get_settings()
        self.parser = DocumentParser()
        self.chunker = DocumentChunker(
            chunk_size=self.settings.doc_chunk_size,
            chunk_overlap=self.settings.doc_chunk_overlap,
        )
        self.embedder = DocumentEmbedder(self.settings.text_embedding_model)
        self.extractor = EmbeddedMediaExtractor()
        self.media_service = MediaService(db, storage)

    def process_asset(self, asset_id: UUID, request_id: str) -> Dict[str, Any]:
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise DocumentServiceError(f"Asset {asset_id} not found")
        if asset.kind != "document":
            raise DocumentServiceError(
                f"Asset {asset_id} is not a document (kind={asset.kind})"
            )

        logger.info("Processing document asset %s", asset_id)

        try:
            asset.status = "processing"
            self.db.commit()

            original_bytes = self.storage.retrieve(asset.uri).read()
            filename = Path(asset.uri).name

            parsed_elements = self.parser.parse(BytesIO(original_bytes), filename)
            if not parsed_elements:
                raise DocumentServiceError("No textual content extracted from document.")

            chunk_dicts = [
                {"type": element.type, "text": element.text, "metadata": element.metadata}
                for element in parsed_elements
            ]
            chunks = self.chunker.chunk_elements(chunk_dicts, str(asset.id))
            if not chunks:
                raise DocumentServiceError("Document produced zero chunks after processing.")

            embeddings = self.embedder.embed_chunks(chunks)
            if embeddings.shape[0] != len(chunks):
                raise DocumentServiceError("Mismatch between chunk count and embeddings.")

            # Remove existing chunks in case of reprocessing
            self.db.query(DocumentChunk).filter(
                DocumentChunk.asset_id == asset.id
            ).delete(synchronize_session=False)

            chunk_records: List[DocumentChunk] = []
            for chunk, vector in zip(chunks, embeddings):
                chunk_records.append(
                    DocumentChunk(
                        asset_id=asset.id,
                        chunk_index=chunk["chunk_index"],
                        text=chunk["text"],
                        parent_heading=chunk.get("parent_heading"),
                        page_number=chunk.get("page_number"),
                        element_type=chunk.get("element_type", "Paragraph"),
                        embedding=vector.tolist(),
                    )
                )

            self.db.add_all(chunk_records)

            heading_order: List[str] = []
            for chunk in chunks:
                heading = chunk.get("parent_heading")
                if heading and heading not in heading_order:
                    heading_order.append(heading)

            embedded_count = self._extract_and_process_embedded_media(
                asset, original_bytes, request_id
            )

            metadata = asset.metadata or {}
            metadata.update(
                {
                    "document_chunk_count": len(chunk_records),
                    "document_parent_headings": heading_order,
                    "embedded_media_count": embedded_count,
                }
            )
            asset.metadata = metadata
            asset.status = "done"
            self.db.commit()

            self._log_lineage(
                request_id=request_id,
                asset_id=asset_id,
                stage="document_processing_complete",
                detail={
                    "chunk_count": len(chunk_records),
                    "embedding_dim": self.embedder.embedding_dim,
                    "embedded_media": embedded_count,
                },
            )

            return {
                "success": True,
                "asset_id": str(asset.id),
                "chunk_count": len(chunk_records),
                "embedded_media": embedded_count,
            }
        except (
            StorageError,
            DocumentParserError,
            DocumentEmbeddingError,
            MediaServiceError,
        ) as exc:
            asset.status = "failed"
            self.db.commit()
            self._log_lineage(
                request_id=request_id,
                asset_id=asset_id,
                stage="document_processing_error",
                detail={"error": str(exc)},
                success=False,
                error_message=str(exc),
            )
            raise DocumentServiceError(str(exc)) from exc
        except DocumentServiceError:
            asset.status = "failed"
            self.db.commit()
            raise
        except Exception as exc:  # pragma: no cover - unexpected failure path
            asset.status = "failed"
            self.db.commit()
            self._log_lineage(
                request_id=request_id,
                asset_id=asset_id,
                stage="document_processing_error",
                detail={"error": str(exc)},
                success=False,
                error_message=str(exc),
            )
            raise DocumentServiceError(f"Unexpected error: {exc}") from exc

    def _extract_and_process_embedded_media(
        self,
        parent_asset: Asset,
        file_bytes: bytes,
        request_id: str,
    ) -> int:
        """Extract embedded media and send them through the media pipeline."""
        content_type = (parent_asset.content_type or "").lower()
        if not content_type:
            return 0

        images: List[Dict[str, Any]] = []
        if "pdf" in content_type:
            images = self.extractor.extract_from_pdf(BytesIO(file_bytes))
        elif "wordprocessingml.document" in content_type or parent_asset.uri.endswith(
            ".docx"
        ):
            images = self.extractor.extract_from_docx(BytesIO(file_bytes))
        else:
            return 0

        created = 0
        for idx, image_data in enumerate(images):
            try:
                derived_asset_id = self._create_embedded_asset(
                    parent_asset=parent_asset,
                    image_data=image_data,
                    request_id=request_id,
                    index=idx,
                )
                self.media_service.process_asset(derived_asset_id, request_id)
                created += 1
            except Exception as exc:  # pragma: no cover - downstream errors logged
                logger.error(
                    "Failed to process embedded image %s for asset %s: %s",
                    idx,
                    parent_asset.id,
                    exc,
                    exc_info=True,
                )
        return created

    def _create_embedded_asset(
        self,
        parent_asset: Asset,
        image_data: Dict[str, Any],
        request_id: str,
        index: int,
    ) -> UUID:
        """Persist embedded image as a media asset and return its ID."""
        image = image_data["image"]
        img_format = (image_data.get("format") or "PNG").lower()
        filename = f"embedded_{parent_asset.id}_{index}.{img_format}"

        buffer = BytesIO()
        image.save(buffer, format=img_format.upper())
        buffer.seek(0)

        sha256 = hashlib.sha256(buffer.getvalue()).hexdigest()
        size_bytes = buffer.getbuffer().nbytes

        part_id = str(uuid4())
        uri = self.storage.store_raw(
            request_id=request_id,
            part_id=part_id,
            file=BytesIO(buffer.getvalue()),
            filename=filename,
        )

        asset_raw = AssetRaw(
            id=uuid4(),
            request_id=request_id,
            part_id=part_id,
            uri=uri,
            size_bytes=size_bytes,
            content_type=f"image/{img_format}",
        )
        self.db.add(asset_raw)

        derived_asset = Asset(
            id=uuid4(),
            kind="media",
            uri=uri,
            sha256=sha256,
            content_type=f"image/{img_format}",
            size_bytes=size_bytes,
            owner=parent_asset.owner,
            status="queued",
            raw_asset_id=asset_raw.id,
            parent_asset_id=parent_asset.id,
            metadata={
                "extracted_from": str(parent_asset.id),
                "page_number": image_data.get("page_number"),
                "extraction_method": "embedded_media",
                "source_width": image.width,
                "source_height": image.height,
            },
        )
        self.db.add(derived_asset)
        self.db.flush()

        self._log_lineage(
            request_id=request_id,
            asset_id=derived_asset.id,
            stage="embedded_media_created",
            detail={
                "parent_asset_id": str(parent_asset.id),
                "page_number": image_data.get("page_number"),
            },
        )

        return derived_asset.id

    def _log_lineage(
        self,
        request_id: str,
        asset_id: UUID,
        stage: str,
        detail: Dict[str, Any],
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        entry = Lineage(
            request_id=request_id,
            asset_id=asset_id,
            stage=stage,
            detail=detail,
            success=success,
            error_message=error_message,
        )
        self.db.add(entry)
        self.db.commit()

