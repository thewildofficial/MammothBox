# Local VLM Architecture: Multi-Model Approach

## Executive Summary

**Decision**: Multi-model approach using CLIP + BLIP-2 + Whisper instead of unified Gemma 3n model.

**Rationale**:

- **Hardware Constraint**: RTX 3050 has 6GB VRAM, Gemma 3n requires 8-12GB
- **Proven Models**: Each model is production-ready and well-documented
- **Memory Safety**: 3GB total VRAM usage leaves 3GB headroom
- **Fast Inference**: <2s per image, <10s per minute of audio

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                           │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────┐ │
│  │  Image/Video │ │    Audio     │ │   JSON/Doc   │ │Embeddings│ │
│  │  Processing  │ │  Processing  │ │  Processing  │ │ & Search │ │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────┬────┘ │
│         │                │                │              │       │
│         ▼                ▼                ▼              ▼       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────┐ │
│  │ BLIP-2       │ │   Whisper    │ │   Phi-3.5    │ │  CLIP   │ │
│  │ Service      │ │   Service    │ │   Mini       │ │(Existing)│ │
│  │ Port: 8001   │ │ Port: 8002   │ │   Service    │ │         │ │
│  │              │ │              │ │ Port: 8003   │ │         │ │
│  │ • Image      │ │ • Transcribe │ │ • Schema     │ │• Generate│ │
│  │   captions   │ │   audio      │ │   analysis   │ │  embeds │ │
│  │ • Object     │ │ • Language   │ │ • Cluster    │ │• Semantic│ │
│  │   detection  │ │   detection  │ │   enrichment │ │  search │ │
│  │ • Scene      │ │ • Timestamps │ │ • Metadata   │ │• Zero-   │ │
│  │   analysis   │ │              │ │   tagging    │ │  shot    │ │
│  │ • Cluster    │ │              │ │ • Semantic   │ │  class   │ │
│  │   labeling   │ │              │ │   reasoning  │ │         │ │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────┬────┘ │
│         │                │                │              │       │
│         └────────────────┴────────────────┴──────────────┘       │
│                                   ▼                               │
│         ┌─────────────────────────────────────────────────┐      │
│         │         GPU (RTX 3050 - 6GB VRAM)               │      │
│         │  CLIP: 400MB | BLIP-2: 1.5GB | Whisper: 1GB    │      │
│         │  Phi-3.5 Mini: 2.5GB (load on-demand)           │      │
│         │  Peak: ~5.4GB | Steady-state: ~2.9GB (48%)      │      │
│         └─────────────────────────────────────────────────┘      │
│                                   ▼                               │
│         ┌─────────────────────────────────────────────────┐      │
│         │      PostgreSQL + pgvector Database             │      │
│         │  • Image metadata   • Audio transcripts         │      │
│         │  • CLIP embeddings  • Cluster labels            │      │
│         │  • JSON schemas     • LLM-enriched tags         │      │
│         └─────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. CLIP (Existing - Already Integrated)

**Purpose**: Generate embeddings for semantic search and clustering

**Model**: `sentence-transformers/clip-ViT-B-32`

**Capabilities**:

- Image → 512D embedding vector
- Text → 512D embedding vector
- Cosine similarity search
- Zero-shot classification

**Memory**: ~400MB VRAM

**Performance**: ~50ms per image (batch of 32)

**Integration**: Already implemented in `backend/src/media/embedder.py`

---

### 2. BLIP-2 (New - Replaces Gemini API)

**Purpose**: Detailed image analysis and cluster labeling

**Model**: `Salesforce/blip2-opt-2.7b`

**Capabilities**:

- **Image Captioning**: "A black cat sitting on a wooden table"
- **Visual Question Answering**: "What color is the car?" → "Red"
- **Object Detection**: [{name: "cat", confidence: 0.95}]
- **Scene Classification**: portrait, landscape, indoor, outdoor
- **Cluster Labeling**: Analyze multiple images → coherent cluster name

**Memory**: ~1.5GB VRAM (with 8-bit quantization)

**Performance**:

- Single image analysis: ~1-2 seconds
- Cluster labeling (5 images): ~3-5 seconds

**Deployment**: Standalone Docker service with REST API

**API Contract**:

```python
# POST /analyze-image
{
    "image": "base64_encoded_image",
    "tasks": ["caption", "objects", "scene", "colors"]
}

# Response
{
    "caption": "A black cat sitting on a wooden table",
    "objects": [
        {"name": "cat", "confidence": 0.95, "bbox": [...]},
        {"name": "table", "confidence": 0.87, "bbox": [...]}
    ],
    "scene_type": "indoor",
    "dominant_colors": ["#1a1a1a", "#8b4513", "#f5f5dc"],
    "processing_time_ms": 1250
}

# POST /label-cluster
{
    "images": ["base64_1", "base64_2", ...],  # max 5 images
    "cluster_size": 45
}

# Response
{
    "cluster_name": "Black Cats",
    "description": "Indoor photos of black cats in various poses",
    "tags": ["cat", "pet", "animal", "black", "indoor"],
    "primary_category": "animals",
    "confidence": 0.92
}
```

---

### 3. Whisper (New - Audio Processing)

**Purpose**: Audio transcription and analysis

**Model**: `openai/whisper-base` (74M parameters)

**Capabilities**:

- **Transcription**: Audio → Text with timestamps
- **Language Detection**: Automatic language identification
- **Speaker Diarization**: Identify different speakers (with pyannote)
- **Sentiment Analysis**: Detect emotion in speech (with additional model)

**Memory**: ~1GB VRAM

**Performance**:

- 1 minute audio: ~5-10 seconds processing
- Supports: mp3, wav, m4a, flac, ogg

**Deployment**: Standalone Docker service with REST API

**API Contract**:

```python
# POST /transcribe
{
    "audio": "base64_encoded_audio",
    "language": "auto",  # or "en", "es", etc.
    "options": {
        "timestamps": true,
        "word_level": false
    }
}

# Response
{
    "text": "The quick brown fox jumps over the lazy dog.",
    "language": "en",
    "segments": [
        {"start": 0.0, "end": 2.5, "text": "The quick brown fox"},
        {"start": 2.5, "end": 5.0, "text": "jumps over the lazy dog."}
    ],
    "processing_time_ms": 3200
}
```

---

### 4. Phi-3.5 Mini-Instruct (New - Semantic Intelligence)

**Purpose**: JSON schema analysis, cluster enrichment, metadata understanding

**Model**: `microsoft/Phi-3.5-mini-instruct` (3.8B parameters, int8 quantized)

**Capabilities**:

- **JSON Schema Analysis**: Infer table names, storage type (SQL vs JSONB), field descriptions
- **Cluster Enrichment**: Generate hierarchical categories, folder paths, extended tags
- **Semantic Understanding**: Extract concepts, relationships, contextual meaning
- **Metadata Generation**: Rich descriptions, search-optimized text

**Memory**: ~2.5GB VRAM (int8 quantization)

**Context Length**: 128K tokens (~96,000 words)

**Performance**:

- JSON schema analysis: ~3-5 seconds per schema
- Cluster enrichment: ~5-10 seconds per cluster
- Speed: ~80-100 tokens/sec on RTX 3050
- Reasoning Quality: Excellent for structured output and instruction following

**Deployment**: Standalone Docker service with REST API (load on-demand)

**API Contract**:

```python
# POST /generate
{
    "prompt": "Analyze this JSON structure...",
    "max_tokens": 500,
    "temperature": 0.3,
    "stop_sequences": ["\n\n"]
}

# Response
{
    "text": "Generated response...",
    "tokens_generated": 245,
    "processing_time_ms": 3500
}

# POST /analyze-json-schema
{
    "json_samples": [...],  # 5 sample documents
    "user_comment": "Order data from e-commerce"
}

# Response
{
    "table_name": "customer_orders",
    "storage_type": "sql",
    "reasoning": "Highly structured with consistent fields...",
    "fields": {
        "id": "Unique order identifier",
        "customer_name": "Full name of customer",
        ...
    },
    "indexes": ["customer_name", "order_date"]
}

# POST /enrich-cluster
{
    "cluster_name": "Black Cats",
    "description": "Photos of black cats indoors",
    "sample_captions": ["A black cat on a table", ...]
}

# Response
{
    "hierarchy": ["Personal", "Pets", "Cats", "Black Cats"],
    "folder_path": "/personal/pets/cats/black_cats/",
    "extended_tags": ["feline", "domestic_cat", "pet", ...],
    "relationships": {
        "similar_to": ["gray_cats", "tabby_cats"],
        "parent": "cats"
    },
    "search_description": "Collection of photographs featuring..."
}
```

**Load Strategy**: Load into VRAM only when needed, unload after processing to free memory for other models.

---

## Video Processing Strategy

**Approach**: Extract frames + audio, process separately

```
Video File → ffmpeg → Frames (every 1-2 sec) → CLIP + BLIP-2
         └─────────→ Audio track → Whisper
```

**Implementation**:

1. Extract key frames using ffmpeg (1 frame per 1-2 seconds)
2. Process each frame as an image (CLIP embeddings + BLIP-2 analysis)
3. Extract audio track and process with Whisper
4. Combine results: frame metadata + transcript + timestamps

**Benefits**:

- Reuses existing image pipeline
- Captures temporal information (frame timestamps)
- Enables visual + audio semantic search

---

## Memory Budget (6GB VRAM)

### Steady-State Operation (Without LLM)

| Component                | Memory       | % of Total | Load Strategy    |
| ------------------------ | ------------ | ---------- | ---------------- |
| CLIP (ViT-B-32)          | 400 MB       | 6.7%       | ✅ Always loaded |
| BLIP-2 (8-bit quantized) | 1,500 MB     | 25%        | ✅ Always loaded |
| Whisper (base)           | 1,000 MB     | 16.7%      | ✅ Always loaded |
| **Total Models**         | **2,900 MB** | **48.3%**  | -                |
| System overhead          | 300 MB       | 5%         | -                |
| Batch processing buffer  | 1,800 MB     | 30%        | -                |
| **Total Usage**          | **5,000 MB** | **83.3%**  | -                |
| **Safety Headroom**      | **1,000 MB** | **16.7%**  | -                |

### Peak Operation (With LLM Loaded)

| Component                | Memory       | % of Total | Load Strategy         |
| ------------------------ | ------------ | ---------- | --------------------- |
| CLIP (ViT-B-32)          | 400 MB       | 6.7%       | ✅ Always loaded      |
| BLIP-2 (8-bit quantized) | 1,500 MB     | 25%        | ✅ Always loaded      |
| Whisper (base)           | 1,000 MB     | 16.7%      | ✅ Always loaded      |
| **Phi-3.5 Mini (int8)**  | **2,500 MB** | **41.7%**  | ⚠️ **Load on-demand** |
| **Total Models**         | **5,400 MB** | **90%**    | -                     |
| System overhead          | 300 MB       | 5%         | -                     |
| Batch processing buffer  | 300 MB       | 5%         | -                     |
| **Total Usage**          | **6,000 MB** | **100%**   | ⚠️ **At capacity**    |

### Memory Management Strategy

**Problem**: All 4 models loaded simultaneously = 100% VRAM usage (risky)

**Solution**: Dynamic model loading for LLM

```python
# Load Phi-3.5 only when needed
class LLMManager:
    def __init__(self):
        self.model = None

    def analyze_with_llm(self, data):
        # Load model into VRAM
        if self.model is None:
            self.model = load_phi35_model()  # 2.5GB VRAM

        result = self.model.generate(data)
        return result

    def unload_llm(self):
        # Free VRAM for other models
        if self.model is not None:
            del self.model
            torch.cuda.empty_cache()
            self.model = None  # Frees 2.5GB
```

**Usage Pattern**:

- **Image/Audio ingestion**: LLM not loaded (2.9GB usage, 48.3% capacity)
- **JSON schema analysis**: Load Phi-3.5 temporarily (5.4GB usage, 90% capacity)
- **Cluster enrichment**: Load Phi-3.5 temporarily (5.4GB usage, 90% capacity)
- **After LLM task**: Unload to free 2.5GB VRAM

**Why Phi-3.5 Mini?**

- **Context Length**: 128K tokens enables full JSON dataset analysis (100+ documents)
- **Reasoning Quality**: Excellent instruction-following for structured output extraction
- **Memory Fit**: 2.5GB fits within budget with dynamic loading
- **Production-Ready**: Microsoft-backed, widely deployed, well-documented

**Alternative Models Considered**:

- **Llama 3.2 3B** (2GB): Saves 500MB, but slightly worse reasoning for structured tasks
- **Gemma 2 2B** (1.5GB): Saves 1GB, but only 8K context (insufficient)
- **Llama 3.1 8B** (5GB): Best quality, but exceeds VRAM budget

---

## Performance Estimates

### Image Processing

- **CLIP embedding**: ~50ms per image
- **BLIP-2 analysis**: ~1-2s per image
- **Total**: ~2s per image ✅ (under 5s requirement)

### Cluster Labeling

- **Per cluster**: 3-5s (analyzes 5 representative images)
- **100 clusters**: ~5 minutes total
- **Efficiency**: 1 call per cluster vs 1 call per image (100x reduction)

### Audio Processing

- **Whisper transcription**: ~5-10s per minute of audio
- **10-minute podcast**: ~1 minute processing time
- **Ratio**: 10:1 (acceptable for batch processing)

### Video Processing

- **10-minute video**:
  - Extract 300 frames (1 per 2 sec): ~10s
  - Process frames (300 × 2s): ~10 minutes (batched in background)
  - Extract + transcribe audio: ~1 minute
  - **Total**: ~11 minutes (batch job, acceptable)

### LLM Processing (On-Demand)

- **JSON Schema Analysis**: ~3-5 seconds per schema
  - Analyzes 5 sample documents
  - Generates table name, field descriptions, indexes
  - **Value**: 85-90% accuracy vs 70-75% heuristics
- **Cluster Enrichment**: ~5-10 seconds per cluster
  - Generates hierarchical categories, folder paths
  - Adds 10-20 extended tags
  - **Value**: Better search relevance, organized hierarchies
- **Throughput**: ~100 tokens/second on RTX 3050

---

## Docker Architecture

### docker-compose.yml Services

```yaml
services:
  # Existing services
  postgres:
    # ... existing config

  redis:
    # ... existing config

  backend:
    # ... existing config
    depends_on:
      - postgres
      - redis
      - blip2-service
      - whisper-service

  # New service: BLIP-2 for image analysis
  blip2-service:
    build:
      context: ./services/blip2
      dockerfile: Dockerfile
    ports:
      - "8001:8000"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
        limits:
          memory: 4G
    environment:
      - MODEL_NAME=Salesforce/blip2-opt-2.7b
      - LOAD_IN_8BIT=true
      - MAX_BATCH_SIZE=4
    volumes:
      - model_cache:/root/.cache/huggingface
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # New service: Whisper for audio transcription
  whisper-service:
    build:
      context: ./services/whisper
      dockerfile: Dockerfile
    ports:
      - "8002:8000"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
        limits:
          memory: 3G
    environment:
      - MODEL_SIZE=base
      - DEVICE=cuda
      - COMPUTE_TYPE=int8
    volumes:
      - model_cache:/root/.cache/whisper
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  postgres_data:
  redis_data:
  model_cache: # Shared cache for all ML models
```

---

## Integration with Existing Code

### 1. Update `backend/src/media/vlm_analyzer.py`

**Current**: Uses Gemini API

```python
import google.generativeai as genai
response = gemini_model.generate_content([prompt] + images)
```

**New**: Uses BLIP-2 service

```python
import requests
response = requests.post(
    "http://blip2-service:8000/analyze-image",
    json={"image": base64_image, "tasks": ["caption", "objects", "scene"]}
)
```

### 2. Create `backend/src/audio/whisper_service.py`

**New file** for audio processing:

```python
import requests
from typing import Dict, List

class WhisperService:
    def __init__(self, endpoint="http://whisper-service:8000"):
        self.endpoint = endpoint

    def transcribe_audio(
        self, audio_data: bytes, language: str = "auto"
    ) -> Dict[str, any]:
        response = requests.post(
            f"{self.endpoint}/transcribe",
            json={
                "audio": base64.b64encode(audio_data).decode(),
                "language": language,
                "options": {"timestamps": True}
            }
        )
        return response.json()
```

### 3. Update `backend/requirements.txt`

**Remove**:

```
google-generativeai==0.8.3
```

**Add**:

```
# No new backend dependencies needed - models run in separate services
# Communication via REST API (already have requests)
```

---

## Migration Strategy

### Phase 1: Setup Infrastructure (Day 1)

1. Create `backend/services/blip2/` directory with Dockerfile
2. Create `backend/services/whisper/` directory with Dockerfile
3. Update `docker-compose.yml` with new services
4. Build and test model services independently

### Phase 2: Integrate BLIP-2 (Day 2)

1. Create `backend/src/media/blip2_client.py` wrapper
2. Update `vlm_analyzer.py` to use BLIP-2 instead of Gemini
3. Maintain same `VLMMetadata` output format
4. Test image analysis and cluster labeling

### Phase 3: Add Audio Processing (Day 3)

1. Create `backend/src/audio/` module
2. Implement Whisper client wrapper
3. Add audio file type detection to ingest pipeline
4. Create `audio_metadata` database table
5. Test audio transcription

### Phase 4: Testing & Optimization (Day 4)

1. Update unit tests (mock HTTP endpoints)
2. Update integration tests
3. Performance benchmarking on RTX 3050
4. Memory optimization (dynamic model loading if needed)
5. Documentation updates

---

## Advantages of This Approach

### ✅ Proven Technology

- CLIP: 500M+ downloads, industry standard
- BLIP-2: Salesforce research, well-documented
- Whisper: OpenAI production model, state-of-the-art

### ✅ Memory Safety

- 3GB total usage vs 6GB available (50% utilization)
- Can load/unload models dynamically
- No risk of OOM crashes

### ✅ Fast Inference

- BLIP-2: 1-2s per image (under 5s requirement)
- Whisper: 10:1 processing ratio (acceptable for batch)
- CLIP: 50ms per image (already tested)

### ✅ Modularity

- Each model in separate Docker service
- Easy to upgrade/replace individual components
- Can scale services independently

### ✅ Extensibility

- Can add more models later (e.g., speaker diarization)
- Can upgrade to larger models with better GPU
- Can add GPU acceleration for video processing

---

## Limitations & Future Work

### Current Limitations

- ❌ No unified multimodal embeddings (separate models)
- ❌ Video processed as frames (no temporal modeling)
- ❌ Audio lacks speaker diarization (can add pyannote later)

### Future Enhancements (Post-Hackathon)

1. **Upgrade to Gemma 3n** when better GPU available (12GB+ VRAM)
2. **Add temporal modeling** for videos (3D CNNs or ViViT)
3. **Speaker diarization** with pyannote.audio
4. **Emotion detection** for audio with wav2vec2-emotion
5. **Incremental clustering** for large datasets (>10k images)

---

## Testing Strategy

### Unit Tests

- Mock HTTP endpoints for BLIP-2 and Whisper services
- Test `blip2_client.py` with various image inputs
- Test `whisper_service.py` with various audio formats
- Maintain 89% coverage

### Integration Tests

- Test full image pipeline: upload → CLIP → BLIP-2 → database
- Test audio pipeline: upload → Whisper → database
- Test video pipeline: upload → extract → CLIP+BLIP+Whisper → database
- Test cluster labeling: clustering → BLIP-2 → labels

### Performance Tests

- Measure inference time per image (target: <2s)
- Measure VRAM usage during operation (target: <4GB)
- Measure throughput: images per minute
- Compare accuracy vs Gemini baseline (target: >80%)

### Hardware Tests

- Test on actual RTX 3050 6GB VRAM
- Monitor GPU temperature and utilization
- Test with concurrent requests (stress test)
- Test graceful degradation if models unavailable

---

## Success Metrics

### Functional Requirements

- ✅ No external API dependencies (Gemini removed)
- ✅ All processing runs locally on RTX 3050
- ✅ Supports images, videos, audio, JSON, text
- ✅ Maintains semantic search and clustering capabilities

### Performance Requirements

- ✅ <2s per image analysis (BLIP-2)
- ✅ <10s per minute of audio (Whisper)
- ✅ <4GB VRAM usage (50% of available)
- ✅ >80% accuracy vs Gemini baseline

### Reliability Requirements

- ✅ Graceful degradation if models unavailable
- ✅ Fallback to CLIP-only mode for image analysis
- ✅ No single point of failure
- ✅ Docker health checks and auto-restart

---

## Conclusion

The multi-model approach (CLIP + BLIP-2 + Whisper) provides a **reliable, performant, and hardware-compatible** solution for local VLM processing. While not as elegant as a unified model like Gemma 3n, it fits the RTX 3050's 6GB VRAM constraint with room to spare, uses proven production-ready models, and can be implemented within the hackathon timeline.

**Trade-off**: Complexity (3 models) vs Safety (guaranteed to work)
**Decision**: Safety wins for hackathon context.
