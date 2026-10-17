import argparse
import asyncio
from src.ingestion.pipeline import run_ingestion_pipeline

def main():
    parser = argparse.ArgumentParser(description="Asset Intelligence Copilot - CLI Entry Point")
    parser.add_argument("--ingest", action="store_true", help="Run the full dataset ingestion pipeline")
    parser.add_argument("--data-dir", type=str, default=None, help="Custom data directory for ingestion")
    args = parser.parse_args()

    if args.ingest:
        from pathlib import Path
        data_dir = Path(args.data_dir) if args.data_dir else None
        if data_dir:
            asyncio.run(run_ingestion_pipeline(data_dir))
        else:
            asyncio.run(run_ingestion_pipeline())
    else:
        print("=== Asset Intelligence Copilot ===")
        print("Run with --ingest to load or reload datasets.")
        print("Run 'uv run pytest tests/phase1 -v' to execute Phase 1 tests.")

if __name__ == "__main__":
    main()
