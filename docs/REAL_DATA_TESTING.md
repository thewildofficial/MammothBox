# Real-Data Regression Testing

These tests exercise the full multimodal ingestion and search stack using production-like
artifacts. By default, they scan your `~/Downloads` folder for sample files, making it easy to
validate the system with documents and media you already have on your machine.

## Preparing the dataset

The test suite automatically searches `~/Downloads` (recursively) for:
- **At least one PDF or DOCX** document (required)
- **At least one JPEG/PNG** image (required)
- **Optional:** one MP4/MOV video file
- **Optional:** one JSON file

You don't need to organize files in any specific way—the tests will find the first matching file
of each type. If you prefer to use a different directory, set the `MAMMOTHBOX_REAL_DATA_DIR`
environment variable to point to your custom folder.

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

## Using a custom data directory

If you want to use a dedicated test dataset instead of scanning `~/Downloads`:

```bash
export MAMMOTHBOX_REAL_DATA_DIR=~/path/to/test/data
pytest tests/integration/test_real_data_regression.py -m realdata
```
