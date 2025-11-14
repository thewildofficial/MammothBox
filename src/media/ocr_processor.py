"""
OCR text extraction from images using Tesseract.

Extracts text content with bounding box metadata for searchability and
text positioning information.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)

# OCR confidence threshold for word inclusion
WORD_CONFIDENCE_THRESHOLD = 60


@dataclass
class BoundingBox:
    """Bounding box for a detected word."""
    word: str
    x: int
    y: int
    width: int
    height: int
    confidence: float


@dataclass
class OCRResult:
    """
    Result of OCR text extraction.
    
    Attributes:
        text: Extracted text content (all detected words joined)
        confidence: Average confidence score across all detected words (0-100)
        bounding_boxes: List of bounding boxes for each detected word
        language: Language code used for OCR (default: 'eng')
        word_count: Number of words extracted
    """
    text: str
    confidence: float
    bounding_boxes: List[BoundingBox]
    language: str = "eng"
    word_count: int = 0


class OCRProcessor:
    """
    Extracts text from images using Tesseract OCR.
    
    Provides text extraction with confidence scoring and bounding box metadata
    for use in search and text positioning applications.
    """
    
    def __init__(
        self,
        language: str = "eng",
        confidence_threshold: int = WORD_CONFIDENCE_THRESHOLD
    ):
        """
        Initialize OCR processor.
        
        Args:
            language: Tesseract language code (default: 'eng')
            confidence_threshold: Minimum confidence score for word inclusion (0-100)
        """
        self.language = language
        self.confidence_threshold = confidence_threshold
    
    def _process_ocr_data(self, ocr_data: dict) -> OCRResult:
        """
        Process OCR data dictionary and extract text with bounding boxes.
        
        Common logic shared by extract_text and extract_text_from_pil.
        
        Args:
            ocr_data: Dictionary from pytesseract.image_to_data()
            
        Returns:
            OCRResult containing extracted text and metadata
        """
        confident_words = []
        bounding_boxes = []
        all_confidences = []
        
        for i, word in enumerate(ocr_data['text']):
            word_stripped = word.strip()
            
            # Skip empty words
            if not word_stripped:
                continue
            
            # Parse confidence value (pytesseract returns strings)
            try:
                confidence_raw = ocr_data['conf'][i]
                # Handle string or numeric confidence values
                if isinstance(confidence_raw, str):
                    confidence = float(confidence_raw) if confidence_raw.strip() else -1.0
                else:
                    confidence = float(confidence_raw)
            except (ValueError, TypeError):
                # Skip invalid confidence values
                continue
            
            # Handle negative confidence: Tesseract returns -1 for unreliable detections
            # Treat -1 as 0 for average calculation but exclude from confident words
            if confidence < 0:
                # Include as 0 in average calculation for accuracy
                all_confidences.append(0.0)
                continue
            
            all_confidences.append(confidence)
            
            if confidence >= self.confidence_threshold:
                confident_words.append(word_stripped)
                
                # Create bounding box
                bbox = BoundingBox(
                    word=word_stripped,
                    x=ocr_data['left'][i],
                    y=ocr_data['top'][i],
                    width=ocr_data['width'][i],
                    height=ocr_data['height'][i],
                    confidence=float(confidence)
                )
                bounding_boxes.append(bbox)
        
        # Aggregate text
        full_text = " ".join(confident_words)
        
        # Calculate average confidence
        avg_confidence = float(np.mean(all_confidences)) if all_confidences else 0.0
        
        return OCRResult(
            text=full_text,
            confidence=avg_confidence,
            bounding_boxes=bounding_boxes,
            language=self.language,
            word_count=len(confident_words)
        )
    
    def extract_text(self, image_path: str) -> OCRResult:
        """
        Extract text from image with bounding box metadata.
        
        Args:
            image_path: Path to image file
            
        Returns:
            OCRResult containing extracted text, confidence scores, and bounding boxes
            
        Raises:
            Exception: If OCR processing fails
        """
        try:
            # Load image
            img = Image.open(image_path)
            
            # Perform OCR with bounding box data
            # PSM 6: Assume uniform text block
            # Output includes word-level bounding boxes and confidence scores
            ocr_data = pytesseract.image_to_data(
                img,
                lang=self.language,
                output_type=pytesseract.Output.DICT,
                config='--psm 6'
            )
            
            # Process OCR data using shared logic
            result = self._process_ocr_data(ocr_data)
            
            logger.info(
                f"OCR extracted {result.word_count} words "
                f"(avg confidence: {result.confidence:.2f})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"OCR extraction failed for {image_path}: {e}")
            raise
    
    def extract_text_from_pil(self, img: Image.Image) -> OCRResult:
        """
        Extract text from PIL Image object.
        
        Args:
            img: PIL Image object
            
        Returns:
            OCRResult containing extracted text and metadata
        """
        try:
            # Perform OCR
            ocr_data = pytesseract.image_to_data(
                img,
                lang=self.language,
                output_type=pytesseract.Output.DICT,
                config='--psm 6'
            )
            
            # Process OCR data using shared logic
            return self._process_ocr_data(ocr_data)
            
        except Exception as e:
            logger.error(f"OCR extraction from PIL image failed: {e}")
            raise
    
    def batch_extract(self, image_paths: List[str]) -> List[OCRResult]:
        """
        Extract text from multiple images.
        
        Args:
            image_paths: List of image file paths
            
        Returns:
            List of OCRResult objects (one per image)
        """
        results = []
        for image_path in image_paths:
            try:
                result = self.extract_text(image_path)
                results.append(result)
            except Exception as e:
                logger.warning(f"Failed to extract text from {image_path}: {e}")
                # Return empty result on failure
                results.append(OCRResult(
                    text="",
                    confidence=0.0,
                    bounding_boxes=[],
                    language=self.language,
                    word_count=0
                ))
        
        return results

