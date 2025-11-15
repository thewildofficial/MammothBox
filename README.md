# ⚠️ MammothBox (DEPRECATED)

> **⚠️ This project is archived and no longer maintained.**  
> **Reason:** Over-engineered for hackathon requirements - judges wanted simple storage/retrieval, we built an AI research project.
>
> **📖 [Read full deprecation notice →](./DEPRECATED.md)**

---

# MammothBox - Automated File Allocator

**Status:** 🗄️ Archived (November 2025)  
**Reason:** Rejected from hackathon for being too complex - they wanted simple storage, we built AI classification system

## What This Was

An over-engineered intelligent file organization system with:
- AI-powered image/video/audio analysis (BLIP-2, Whisper, Phi-3.5)
- Semantic clustering with CLIP embeddings
- VLM metadata extraction
- Automatic file organization
- Perceptual deduplication

## What They Actually Wanted

```python
@app.post("/upload")  # Upload file
@app.get("/download/{file_id}")  # Download file
@app.get("/search?q=filename")  # Search files
```

Yeah... we missed the mark. 🎯❌

## Lessons Learned

**Don't classify when they asked for storage.**

Read the full story and technical details in [DEPRECATED.md](./DEPRECATED.md).

---

<details>
<summary><b>📋 Original README (click to expand)</b></summary>

