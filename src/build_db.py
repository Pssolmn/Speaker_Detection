"""CLI for enrollment. Run from the project root: python -m src.build_db.

Image sources: io/reference_images.py
Workflow: pipeline/reference_enrollment.py
PKL storage: io/character_db.py
"""

import argparse
from pathlib import Path
import sys

from src.core import config
from src.io.reference_images import read_reference_image, download_reference_image, fetch_anilist_reference
from src.pipeline.reference_enrollment import add_character_reference, build_character_database

import cv2
import requests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or extend the character reference database")
    parser.add_argument("--name", help="Character name for a single reference")
    parser.add_argument("--series", help="Extra AniList search text (not an exact series filter)")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--fetch-api", action="store_true", help="Download a character image from AniList")
    sources.add_argument("--url", help="Download a reference image from this URL")
    sources.add_argument("--file", type=Path, help="Read a local reference image")
    parser.add_argument("--reference-dir", type=Path, default=config.REFERENCES_DIR)
    parser.add_argument("--database", type=Path, default=config.DATABASE_PATH)
    args = parser.parse_args(argv)
    single_reference = args.fetch_api or args.url is not None or args.file is not None
    if single_reference and not args.name:
        parser.error("--name is required with --file, --url, or --fetch-api")
    if args.name and not single_reference:
        parser.error("--name requires --file, --url, or --fetch-api")
    if args.series and not args.fetch_api:
        parser.error("--series can only be used with --fetch-api")

    cv2.setNumThreads(config.CV_THREADS)
    try:
        if single_reference:
            if args.fetch_api:
                image = fetch_anilist_reference(args.name, args.series)
            elif args.url:
                image = download_reference_image(args.url)
            else:
                image = read_reference_image(args.file)
            path = add_character_reference(args.name, image, args.reference_dir, args.database)
            print(f"Status: Enrolled {args.name}: {path}")
        else:
            print("Status: Running batch enrollment from references directory...")
            database = build_character_database(args.reference_dir, args.database)
            print("Status: Batch processing completed.")
            for name, references in sorted(database.items()):
                print(f"{name}: {len(references)} reference(s)")
            total = sum(len(refs) for refs in database.values())
            print(f"Total: {len(database)} character(s), {total} reference image(s)")
    except (OSError, ValueError, requests.RequestException, cv2.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
