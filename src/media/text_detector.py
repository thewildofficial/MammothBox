"""
Text-in-image detection for routing images to OCR processing.

Uses edge density heuristics to efficiently filter images that likely contain text
before running expensive OCR operations.
"""

import logging
from typing import Tuple

import cv2
import numpy as np
from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)

# Heuristic thresholds
EDGE_DENSITY_THRESHOLD = 0.15
OCR_CONFIDENCE_THRESHOLD = 60
MIN_WORD_COUNT = 5


class TextInImageDetector:
    """
    Detects images that contain significant text content.
    
    Uses a two-stage heuristic:
    1. Edge density check (fast filter) - detects high-contrast areas typical of text
    2. OCR confidence check (slower validation) - verifies actual text presence
    
    This approach minimizes expensive OCR operations on natural photos while
    accurately identifying screenshots, diagrams, memes, and other text-heavy images.
    """
    
    def __init__(
        self,
        edge_threshold: float = EDGE_DENSITY_THRESHOLD,
        ocr_confidence_threshold: int = OCR_CONFIDENCE_THRESHOLD,
        min_word_count: int = MIN_WORD_COUNT
    ):
        """
        Initialize text-in-image detector.
        
        Args:
            edge_threshold: Edge density threshold (0.0-1.0) for stage 1 filtering
            ocr_confidence_threshold: Minimum OCR confidence score (0-100) for word detection
            min_word_count: Minimum number of confident words to consider image as text-containing
        """
        self.edge_threshold = edge_threshold
        self.ocr_confidence_threshold = ocr_confidence_threshold
        self.min_word_count = min_word_count
    
    def contains_text(self, image_path: str) -> Tuple[bool, float]:
        """
        Detect if an image contains significant text content.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Tuple of (has_text: bool, confidence_score: float)
            - has_text: True if image likely contains text
            - confidence_score: Average OCR confidence (0-100), or 0 if skipped
            
        Raises:
            Exception: If image cannot be loaded or processed
        """
        try:
            # Load image
            img = Image.open(image_path).convert('RGB')
            img_array = np.array(img)
            
            # Stage 1: Edge density heuristic (fast filter)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            edge_density = np.count_nonzero(edges) / edges.size
            
            logger.debug(f"Edge density: {edge_density:.4f} (threshold: {self.edge_threshold})")
            
            if edge_density < self.edge_threshold:
                # Low edge density suggests natural photo without text
                logger.debug("Low edge density - likely natural photo, skipping OCR")
                return False, 0.0
            
            # Stage 2: OCR confidence check (slower validation)
            ocr_data = pytesseract.image_to_data(
                img,
                output_type=pytesseract.Output.DICT,
                config='--psm 6'  # Assume uniform text block
            )
            
            # Parse confidence values (pytesseract returns strings)
            confidences_float = []
            confident_words = []
            
            for word, conf_raw in zip(ocr_data['text'], ocr_data['conf']):
                if not word.strip():
                    continue
                
                try:
                    # Convert string confidence to float
                    if isinstance(conf_raw, str):
                        conf_float = float(conf_raw) if conf_raw.strip() else -1.0
                    else:
                        conf_float = float(conf_raw)
                except (ValueError, TypeError):
                    # Skip invalid confidence values
                    continue
                
                # Include in average calculation (treat negative as 0)
                confidences_float.append(max(0.0, conf_float))
                
                # Filter confident words
                if conf_float > self.ocr_confidence_threshold:
                    confident_words.append(word.strip())
            
            # Calculate average confidence from valid float values
            avg_confidence = float(np.mean(confidences_float)) if confidences_float else 0.0
            
            has_text = len(confident_words) >= self.min_word_count
            
            logger.debug(
                f"OCR results: {len(confident_words)} confident words, "
                f"avg confidence: {avg_confidence:.2f}"
            )
            
            return has_text, avg_confidence
            
        except Exception as e:
            logger.error(f"Text detection failed for {image_path}: {e}")
            raise
    
    def batch_detect(self, image_paths: list[str]) -> list[Tuple[str, bool, float]]:
        """
        Detect text in multiple images.
        
        Args:
            image_paths: List of image file paths
            
        Returns:
            List of tuples (image_path, has_text, confidence_score)
        """
        results = []
        for image_path in image_paths:
            try:
                has_text, confidence = self.contains_text(image_path)
                results.append((image_path, has_text, confidence))
            except Exception as e:
                logger.warning(f"Failed to process {image_path}: {e}")
                results.append((image_path, False, 0.0))
        
        return results

