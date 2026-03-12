#!/usr/bin/env python3
"""
Clear and re-upload satellite images to Supabase Storage.

Steps:
  1. Delete all existing objects in the 'images' bucket
  2. Upload all .png files from the local image directory

Environment variables:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY

Usage:
  python scripts/upload_images_to_supabase.py                    # upload all
  python scripts/upload_images_to_supabase.py --limit 10         # test with 10
  python scripts/upload_images_to_supabase.py --skip-delete      # upload without clearing first
  python scripts/upload_images_to_supabase.py --dry-run           # preview only
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

BUCKET = "images"
IMAGE_DIR = PROJECT_ROOT / "data" / "images" / "Boulder_CO"


def get_client():
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def list_existing(client) -> set[str]:
    """List all objects currently in the bucket."""
    existing = set()
    offset = 0
    while True:
        result = client.storage.from_(BUCKET).list(options={"limit": 1000, "offset": offset})
        if not result:
            break
        for f in result:
            existing.add(f["name"])
        if len(result) < 1000:
            break
        offset += len(result)
    return existing


def clear_bucket(client) -> int:
    """Delete all objects in the bucket. Returns count deleted."""
    deleted = 0
    while True:
        result = client.storage.from_(BUCKET).list(options={"limit": 1000})
        if not result:
            break
        paths = [f["name"] for f in result]
        if not paths:
            break
        client.storage.from_(BUCKET).remove(paths)
        deleted += len(paths)
        print(f"  Deleted {deleted} objects...")
    return deleted


def upload_file(filepath: Path, max_retries: int = 3) -> tuple[str, bool, str]:
    """Upload a single file using its own client. Retries on failure."""
    name = filepath.name
    with open(filepath, "rb") as f:
        data = f.read()
    for attempt in range(max_retries):
        try:
            client = get_client()
            client.storage.from_(BUCKET).upload(
                name,
                data,
                file_options={"content-type": "image/png", "upsert": "true"},
            )
            return (name, True, "")
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
            else:
                return (name, False, str(e))


def main():
    parser = argparse.ArgumentParser(description="Upload images to Supabase Storage")
    parser.add_argument("--limit", type=int, default=None, help="Max images to upload")
    parser.add_argument("--skip-delete", action="store_true", help="Skip clearing the bucket first")
    parser.add_argument("--sync", action="store_true", help="Only upload files missing from bucket")
    parser.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    parser.add_argument("--workers", type=int, default=4, help="Parallel upload threads (default: 4)")
    args = parser.parse_args()

    if not IMAGE_DIR.exists():
        print(f"ERROR: Image directory not found: {IMAGE_DIR}")
        sys.exit(1)

    files = sorted(IMAGE_DIR.glob("*.png"))
    if args.limit:
        files = files[:args.limit]

    print(f"Images to upload: {len(files)}")
    print(f"Source: {IMAGE_DIR}")
    print(f"Bucket: {BUCKET}")

    if args.dry_run:
        print("\n--dry-run: no changes made")
        for f in files[:5]:
            print(f"  Would upload: {f.name}")
        if len(files) > 5:
            print(f"  ... and {len(files) - 5} more")
        return

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        print("\nERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
        sys.exit(1)

    client = get_client()

    # Step 1: Clear bucket or filter to missing files
    if args.sync:
        print("\nChecking which files are already in bucket...")
        existing = list_existing(client)
        before = len(files)
        files = [f for f in files if f.name not in existing]
        print(f"  {len(existing)} already in bucket, {len(files)} to upload ({before - len(files)} skipped)")
        if not files:
            print("Nothing to upload — bucket is in sync.")
            return
    elif not args.skip_delete:
        print("\nClearing existing images from bucket...")
        deleted = clear_bucket(client)
        print(f"  Cleared {deleted} objects")
    else:
        print("\nSkipping bucket clear (--skip-delete)")

    # Step 2: Upload with thread pool (each thread gets its own client)
    print(f"\nUploading {len(files)} images ({args.workers} threads)...")
    start = time.time()
    uploaded = 0
    failed = 0
    errors = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(upload_file, f): f for f in files}
        for future in as_completed(futures):
            name, success, err = future.result()
            if success:
                uploaded += 1
            else:
                failed += 1
                errors.append((name, err))
            total = uploaded + failed
            if total <= 5 or total % 500 == 0 or total == len(files):
                elapsed = time.time() - start
                rate = total / elapsed if elapsed > 0 else 0
                print(f"  [{total}/{len(files)}] {uploaded} ok, {failed} failed ({rate:.0f}/s)")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s. Uploaded {uploaded}, failed {failed}.")
    if errors:
        print(f"\nFailed uploads:")
        for name, err in errors[:20]:
            print(f"  {name}: {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")


if __name__ == "__main__":
    main()
