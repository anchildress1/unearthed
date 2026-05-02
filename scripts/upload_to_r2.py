"""Upload local Parquet exports to Cloudflare R2.

Idempotent: each call replaces whatever is in the bucket with whatever is
on disk. Uploads preserve the ``layer/filename.parquet`` layout under
``s3://${R2_BUCKET}/`` so the data_client SQL never has to know whether a
file was newly built or held over from the previous run.

Required env::

    R2_ACCESS_KEY_ID       — token with Object Read+Write on the bucket
    R2_SECRET_ACCESS_KEY
    R2_ENDPOINT            — https://<account>.r2.cloudflarestorage.com
    R2_BUCKET              — defaults to "unearthed-data"

Usage::

    uv run python -m scripts.upload_to_r2                # everything under data/parquet
    uv run python -m scripts.upload_to_r2 --src ./other  # custom source root
    uv run python -m scripts.upload_to_r2 --dry-run      # log only, no PUT
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import boto3
from botocore.client import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _build_client():
    """Construct an S3 client wired to the R2 endpoint.

    R2 is S3-API-compatible but the SDK still expects a few quirks:
    ``signature_version=s3v4`` (R2 rejects v2), ``region_name='auto'``
    (R2 has no real regions but boto3 requires one), and we never use a
    bucket-style URL because R2's hostnames don't expose them.
    """
    required = ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            f"Missing R2 credentials in env: {missing}. "
            "See MIGRATION.md Phase 0 for the bucket setup."
        )
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _iter_parquet_files(src: Path):
    """Yield every ``.parquet`` file under ``src`` together with the key
    it should land under in R2 (``layer/filename.parquet``)."""
    for path in sorted(src.rglob("*.parquet")):
        rel = path.relative_to(src)
        # Posix-style key — R2 doesn't care about backslashes but cross-OS
        # consistency matters when debugging which file ended up where.
        key = rel.as_posix()
        yield path, key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("data/parquet"),
        help="Local source directory (default: ./data/parquet).",
    )
    parser.add_argument(
        "--bucket",
        default=os.environ.get("R2_BUCKET", "unearthed-data"),
        help="R2 bucket name (default: $R2_BUCKET or 'unearthed-data').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be uploaded without writing to R2.",
    )
    args = parser.parse_args(argv)

    src: Path = args.src.resolve()
    if not src.is_dir():
        raise SystemExit(
            f"Source directory not found: {src}. Run scripts.export_snowflake_to_parquet first."
        )

    files = list(_iter_parquet_files(src))
    if not files:
        logger.warning("No .parquet files under %s — nothing to upload.", src)
        return 0

    if args.dry_run:
        logger.info("[dry-run] would upload %d file(s) to s3://%s/", len(files), args.bucket)
        for path, key in files:
            logger.info("  %s → s3://%s/%s", path, args.bucket, key)
        return 0

    client = _build_client()
    for path, key in files:
        logger.info("PUT %s → s3://%s/%s", path, args.bucket, key)
        with path.open("rb") as fp:
            client.put_object(
                Bucket=args.bucket,
                Key=key,
                Body=fp,
                ContentType="application/vnd.apache.parquet",
            )
    logger.info("Uploaded %d file(s) to s3://%s/", len(files), args.bucket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
