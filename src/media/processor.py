"""
Media processor for normalization and preprocessing.

Handles MIME type detection, file validation, and type-specific normalization
for images, videos, and audio files.
"""

import hashlib
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID

import cv2
import imagehash
import numpy as np
from PIL import Image, ExifTags
import ffmpeg

from src.config.settings import get_settings
from src.storage.adapter import StorageAdapter

logger = logging.getLogger(__name__)


@dataclass
class MediaMetadata:
    """Metadata extracted from media file."""
    content_type: str
    file_size: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None  # For video/audio
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None  # For audio
    exif: Optional[Dict[str, Any]] = None
    perceptual_hash: Optional[str] = None


@dataclass
class ProcessedImage:
    """Processed image data."""
    normalized_image: Image.Image
    thumbnail: Image.Image
    metadata: MediaMetadata


@dataclass
class ProcessedVideo:
    """Processed video data."""
    keyframes: List[Image.Image]  # Up to 3 keyframes
    thumbnail: Image.Image
    metadata: MediaMetadata


@dataclass
class ProcessedAudio:
    """Processed audio data."""
    metadata: MediaMetadata
    waveform_image: Optional[Image.Image] = None


class MediaProcessingError(Exception):
    """Exception raised during media processing."""
    pass


class MediaProcessor:
    """
    Media processor for classification, validation, and normalization.
    
    Handles images, videos, and audio files according to the spec.
    """
    
    # Size limits (bytes)
    MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500MB
    MAX_AUDIO_SIZE = 100 * 1024 * 1024  # 100MB
    
    def __init__(self, storage: StorageAdapter):
        """
        Initialize media processor.
        
        Args:
            storage: Storage adapter for file operations
        """
        self.storage = storage
        self.settings = get_settings()
    
    def detect_mime_type(self, file_content: bytes, filename: str) -> str:
        """
        Detect MIME type from magic bytes and filename.
        
        Args:
            file_content: File bytes
            filename: Original filename
            
        Returns:
            MIME type string
        """
        # Check magic bytes
        if file_content.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        elif file_content.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        elif file_content.startswith(b'GIF87a') or file_content.startswith(b'GIF89a'):
            return 'image/gif'
        elif file_content.startswith(b'RIFF') and b'WEBP' in file_content[:12]:
            return 'image/webp'
        elif file_content.startswith(b'\x00\x00\x00 ftyp') or file_content.startswith(b'ftyp'):
            return 'video/mp4'
        elif file_content.startswith(b'RIFF') and b'WAVE' in file_content[:12]:
            return 'audio/wav'
        elif file_content.startswith(b'\xff\xfb') or file_content.startswith(b'\xff\xf3'):
            return 'audio/mpeg'
        
        # Fallback to extension-based detection
        ext = Path(filename).suffix.lower()
        mime_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
        }
        return mime_map.get(ext, 'application/octet-stream')
    
    def validate_file(self, file_content: bytes, content_type: str) -> None:
        """
        Validate file size and type.
        
        Args:
            file_content: File bytes
            content_type: MIME type
            
        Raises:
            MediaProcessingError: If validation fails
        """
        size = len(file_content)
        
        if content_type.startswith('image/'):
            if size > self.MAX_IMAGE_SIZE:
                raise MediaProcessingError(
                    f"Image size {size} exceeds maximum {self.MAX_IMAGE_SIZE}"
                )
        elif content_type.startswith('video/'):
            if size > self.MAX_VIDEO_SIZE:
                raise MediaProcessingError(
                    f"Video size {size} exceeds maximum {self.MAX_VIDEO_SIZE}"
                )
        elif content_type.startswith('audio/'):
            if size > self.MAX_AUDIO_SIZE:
                raise MediaProcessingError(
                    f"Audio size {size} exceeds maximum {self.MAX_AUDIO_SIZE}"
                )
        else:
            raise MediaProcessingError(f"Unsupported content type: {content_type}")
    
    def extract_exif(self, image: Image.Image) -> Optional[Dict[str, Any]]:
        """
        Extract EXIF metadata from image.
        
        Args:
            image: PIL Image
            
        Returns:
            Dictionary of EXIF data or None
        """
        try:
            exif_data = image.getexif()
            if not exif_data:
                return None
            
            exif_dict = {}
            for tag_id, value in exif_data.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                try:
                    # Try to serialize value
                    if isinstance(value, (str, int, float)):
                        exif_dict[tag] = value
                    else:
                        exif_dict[tag] = str(value)
                except Exception:
                    pass
            
            return exif_dict if exif_dict else None
        except Exception as e:
            logger.warning(f"Failed to extract EXIF: {e}")
            return None
    
    def process_image(self, file_content: bytes, filename: str) -> ProcessedImage:
        """
        Process and normalize image.
        
        Args:
            file_content: Image file bytes
            filename: Original filename
            
        Returns:
            ProcessedImage with normalized image, thumbnail, and metadata
        """
        try:
            # Load image
            image = Image.open(BytesIO(file_content))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Extract EXIF before resizing
            exif = self.extract_exif(image)
            
            # Resize to max 1024px (maintain aspect ratio)
            max_size = self.settings.max_image_size
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # Generate thumbnail (256x256)
            thumbnail = image.copy()
            thumbnail.thumbnail((256, 256), Image.Resampling.LANCZOS)
            
            # Compute perceptual hash
            phash = imagehash.phash(image)
            
            # Create metadata
            metadata = MediaMetadata(
                content_type='image/jpeg',
                file_size=len(file_content),
                width=image.width,
                height=image.height,
                exif=exif,
                perceptual_hash=str(phash)
            )
            
            return ProcessedImage(
                normalized_image=image,
                thumbnail=thumbnail,
                metadata=metadata
            )
            
        except Exception as e:
            raise MediaProcessingError(f"Failed to process image: {e}") from e
    
    def extract_video_keyframes(self, file_path: str, max_keyframes: int = 3) -> List[Tuple[Image.Image, float]]:
        """
        Extract keyframes from video using scene detection.
        
        Args:
            file_path: Path to video file
            max_keyframes: Maximum number of keyframes to extract
            
        Returns:
            List of (frame_image, timestamp) tuples
        """
        try:
            # Use ffmpeg to extract keyframes with scene detection
            probe = ffmpeg.probe(file_path)
            duration = float(probe['format'].get('duration', 0))
            
            if duration == 0:
                # Fallback: extract evenly spaced frames
                timestamps = [duration * i / (max_keyframes + 1) for i in range(1, max_keyframes + 1)]
            else:
                # Use scene detection (simplified: evenly spaced for now)
                # In production, use ffmpeg scene detection filter
                timestamps = [duration * i / (max_keyframes + 1) for i in range(1, max_keyframes + 1)]
            
            keyframes = []
            for timestamp in timestamps[:max_keyframes]:
                try:
                    # Extract frame at timestamp
                    out, _ = (
                        ffmpeg
                        .input(file_path, ss=timestamp)
                        .output('pipe:', vframes=1, format='image2', vcodec='png')
                        .run(capture_stdout=True, quiet=True)
                    )
                    frame_image = Image.open(BytesIO(out))
                    if frame_image.mode != 'RGB':
                        frame_image = frame_image.convert('RGB')
                    keyframes.append((frame_image, timestamp))
                except Exception as e:
                    logger.warning(f"Failed to extract frame at {timestamp}s: {e}")
                    continue
            
            return keyframes
            
        except Exception as e:
            logger.warning(f"Failed to extract keyframes using ffmpeg: {e}")
            # Fallback: use OpenCV
            return self._extract_keyframes_opencv(file_path, max_keyframes)
    
    def _extract_keyframes_opencv(self, file_path: str, max_keyframes: int) -> List[Tuple[Image.Image, float]]:
        """Fallback keyframe extraction using OpenCV."""
        try:
            cap = cv2.VideoCapture(file_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            
            if duration == 0:
                return []
            
            # Extract evenly spaced frames
            timestamps = [duration * i / (max_keyframes + 1) for i in range(1, max_keyframes + 1)]
            keyframes = []
            
            for timestamp in timestamps[:max_keyframes]:
                frame_number = int(timestamp * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                ret, frame = cap.read()
                if ret:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_image = Image.fromarray(frame_rgb)
                    keyframes.append((frame_image, timestamp))
            
            cap.release()
            return keyframes
            
        except Exception as e:
            logger.error(f"OpenCV keyframe extraction failed: {e}")
            return []
    
    def process_video(self, file_content: bytes, filename: str, temp_path: Optional[str] = None) -> ProcessedVideo:
        """
        Process video and extract keyframes.
        
        Args:
            file_content: Video file bytes
            filename: Original filename
            temp_path: Optional temporary path to save video for processing
            
        Returns:
            ProcessedVideo with keyframes, thumbnail, and metadata
        """
        try:
            # Save to temp file for ffmpeg processing
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
                tmp_file.write(file_content)
                tmp_path = tmp_file.name
            
            try:
                # Probe video metadata
                probe = ffmpeg.probe(tmp_path)
                video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
                duration = float(probe['format'].get('duration', 0))
                
                width = int(video_stream.get('width', 0)) if video_stream else None
                height = int(video_stream.get('height', 0)) if video_stream else None
                codec = video_stream.get('codec_name') if video_stream else None
                bitrate = int(probe['format'].get('bit_rate', 0)) if probe['format'].get('bit_rate') else None
                
                # Extract keyframes
                max_keyframes = self.settings.video_keyframes
                keyframe_data = self.extract_video_keyframes(tmp_path, max_keyframes)
                keyframes = [frame for frame, _ in keyframe_data]
                
                if not keyframes:
                    raise MediaProcessingError("Failed to extract any keyframes")
                
                # Generate thumbnail from first keyframe
                thumbnail = keyframes[0].copy()
                thumbnail.thumbnail((256, 256), Image.Resampling.LANCZOS)
                
                # Create metadata
                metadata = MediaMetadata(
                    content_type='video/mp4',
                    file_size=len(file_content),
                    width=width,
                    height=height,
                    duration=duration,
                    codec=codec,
                    bitrate=bitrate
                )
                
                return ProcessedVideo(
                    keyframes=keyframes,
                    thumbnail=thumbnail,
                    metadata=metadata
                )
                
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            raise MediaProcessingError(f"Failed to process video: {e}") from e
    
    def process_audio(self, file_content: bytes, filename: str) -> ProcessedAudio:
        """
        Process audio and extract metadata.
        
        Args:
            file_content: Audio file bytes
            filename: Original filename
            
        Returns:
            ProcessedAudio with metadata
        """
        try:
            import tempfile
            import os
            
            # Save to temp file for ffprobe
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
                tmp_file.write(file_content)
                tmp_path = tmp_file.name
            
            try:
                # Probe audio metadata
                probe = ffmpeg.probe(tmp_path)
                audio_stream = next((s for s in probe['streams'] if s['codec_type'] == 'audio'), None)
                duration = float(probe['format'].get('duration', 0))
                
                codec = audio_stream.get('codec_name') if audio_stream else None
                bitrate = int(probe['format'].get('bit_rate', 0)) if probe['format'].get('bit_rate') else None
                sample_rate = int(audio_stream.get('sample_rate', 0)) if audio_stream and audio_stream.get('sample_rate') else None
                
                # Generate waveform (optional, simplified)
                waveform_image = None
                try:
                    # Extract audio data and create simple waveform visualization
                    out, _ = (
                        ffmpeg
                        .input(tmp_path)
                        .output('pipe:', format='wav', acodec='pcm_s16le', ac=1, ar='44100')
                        .run(capture_stdout=True, quiet=True)
                    )
                    # Convert to numpy array and create simple waveform
                    audio_data = np.frombuffer(out, dtype=np.int16)
                    if len(audio_data) > 0:
                        # Create simple waveform visualization
                        waveform_image = self._create_waveform_image(audio_data)
                except Exception as e:
                    logger.warning(f"Failed to generate waveform: {e}")
                
                metadata = MediaMetadata(
                    content_type='audio/mpeg',
                    file_size=len(file_content),
                    duration=duration,
                    codec=codec,
                    bitrate=bitrate,
                    sample_rate=sample_rate
                )
                
                return ProcessedAudio(
                    metadata=metadata,
                    waveform_image=waveform_image
                )
                
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            raise MediaProcessingError(f"Failed to process audio: {e}") from e
    
    def _create_waveform_image(self, audio_data: np.ndarray, width: int = 800, height: int = 200) -> Image.Image:
        """Create a simple waveform visualization."""
        try:
            # Downsample for visualization
            step = max(1, len(audio_data) // width)
            samples = audio_data[::step][:width]
            
            # Normalize
            samples = samples.astype(np.float32)
            samples = samples / np.max(np.abs(samples)) if np.max(np.abs(samples)) > 0 else samples
            
            # Create image
            img = Image.new('RGB', (width, height), color='white')
            pixels = img.load()
            
            for x in range(len(samples)):
                y_center = height // 2
                amplitude = int(abs(samples[x]) * (height // 2 - 10))
                for y in range(max(0, y_center - amplitude), min(height, y_center + amplitude)):
                    pixels[x, y] = (0, 0, 0)
            
            return img
        except Exception as e:
            logger.warning(f"Failed to create waveform image: {e}")
            return None

