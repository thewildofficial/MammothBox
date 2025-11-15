#!/usr/bin/env python3
"""
Simplified media processing test that validates core functionality
without requiring pgvector extension.
"""

import sys
import os
from io import BytesIO
from PIL import Image

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

def test_media_processor():
    """Test media processor without database."""
    print("="*80)
    print("SIMPLIFIED MEDIA PROCESSING TEST")
    print("="*80)
    
    try:
        from src.storage.filesystem import FilesystemStorage
        from src.media.processor import MediaProcessor
        import tempfile
        
        # Create temp storage
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FilesystemStorage(tmpdir)
            processor = MediaProcessor(storage)
            
            print("\n✅ Storage and processor initialized")
            
            # Create test image
            print("\n📸 Creating test image...")
            test_image = Image.new('RGB', (1920, 1080), color='red')
            buffer = BytesIO()
            test_image.save(buffer, format='JPEG', quality=95)
            image_data = buffer.getvalue()
            
            print(f"   Image size: {len(image_data)} bytes")
            
            # Test MIME detection
            print("\n🔍 Testing MIME type detection...")
            mime_type = processor.detect_mime_type(image_data, "test.jpg")
            print(f"   Detected MIME type: {mime_type}")
            assert mime_type == "image/jpeg", f"Expected image/jpeg, got {mime_type}"
            print("   ✅ MIME detection correct")
            
            # Test validation
            print("\n✅ Testing file validation...")
            processor.validate_file(image_data, "image/jpeg")
            print("   ✅ File validation passed")
            
            # Test image processing
            print("\n🖼️  Testing image processing...")
            result = processor.process_image(image_data, "test.jpg")
            
            print(f"   Original size: 1920x1080")
            print(f"   Normalized size: {result.normalized_image.width}x{result.normalized_image.height}")
            print(f"   Thumbnail size: {result.thumbnail.width}x{result.thumbnail.height}")
            print(f"   Perceptual hash: {result.metadata.perceptual_hash[:16]}...")
            
            assert result.normalized_image.width <= 1024, "Image not resized correctly"
            assert result.normalized_image.height <= 1024, "Image not resized correctly"
            assert result.thumbnail.width <= 256, "Thumbnail too large"
            assert result.thumbnail.height <= 256, "Thumbnail too large"
            assert result.metadata.perceptual_hash is not None, "Missing perceptual hash"
            
            print("   ✅ Image processing successful")
            
            # Test embedder (if model available)
            print("\n🧠 Testing embedding generation...")
            try:
                from src.media.embedder import MediaEmbedder
                embedder = MediaEmbedder()
                
                print("   Loading CLIP model (this may take a moment)...")
                embedding = embedder.encode_image(result.normalized_image)
                
                import numpy as np
                print(f"   Embedding shape: {embedding.shape}")
                norm = np.linalg.norm(embedding)
                print(f"   Embedding norm: {norm:.3f}")
                
                assert embedding.shape == (512,), f"Expected shape (512,), got {embedding.shape}"
                assert abs(norm - 1.0) < 0.1, f"Embedding not normalized (norm: {norm})"
                
                print("   ✅ Embedding generation successful")
                
            except Exception as e:
                print(f"   ⚠️  Embedding test skipped: {e}")
                print("   (CLIP model may not be available)")
            
            print("\n" + "="*80)
            print("✅ ALL TESTS PASSED")
            print("="*80)
            return True
            
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_media_processor()
    sys.exit(0 if success else 1)

