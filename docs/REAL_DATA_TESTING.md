# Real-Data Regression Testing

These tests exercise the full multimodal ingestion and search stack using production-like
artifacts. Because they rely on non-public assets, the test harness expects you to point it to
files that live outside of the repository (for example inside `~/Downloads`).

## Preparing the dataset

1. Create a folder on your workstation (default: `~/Downloads/MammothBoxRealData`).
2. Populate it with at least the following real-world samples:
   - One PDF or DOCX document that contains several pages of text. Documents with embedded
     illustrations are ideal because they verify the embedded-media extraction path.
   - One JPEG/PNG image (high resolution works best).
   - Optional but recommended: one short MP4/MOV video and one representative JSON payload.
3. (Optional) Organize files into subfolders such as `documents/`, `media/images/`,
   `media/videos/`, and `json/`. The discovery logic simply walks the entire tree and grabs the
   first file matching each required extension.
4. If you store the assets somewhere other than `~/Downloads/MammothBoxRealData`, set the
   `MAMMOTHBOX_REAL_DATA_DIR` environment variable to the folder you created.

## Running the tests

1. Ensure PostgreSQL is running and that the database URL in `.env` points to a writable test
   database (these tests will insert and clean up their own data).
2. Activate the project virtual environment.
3. Run the real-data suite (markers keep the tests opt-in by default):

```bash
pytest tests/integration/test_real_data_regression.py -m realdata
```

The test module automatically skips specific scenarios when a required asset type is missing
(e.g., no video sample present). When assets exist, the suite validates:

- Document parsing, chunking, and 768-dimension embedding generation.
- Unified search chunk filtering by owner, tags, and cluster ID.
- Delegation of JSON asset searches through the media search path.
- Video frame extraction plus frame-level embedding storage.
- Rich metadata collection for media assets.

If you prefer to run every real-data test regardless of marker selection, remove the
`-m realdata` flag or set `PYTEST_ADDOPTS="-m realdata"` globally.
