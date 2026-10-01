# Data directory

- `raw/` — parquet files produced by `generate_data.py`.
- `processed/` — DuckDB file, data-quality report, funnel validation report.

Both subdirectories are git-ignored. Regenerate with:

    python generate_data.py
    python run_pipeline.py