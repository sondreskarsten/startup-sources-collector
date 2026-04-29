"""Collector entrypoint: Prosjektbanken → raw JSONL.gz on GCS.

Scrapes the three Prosjektbanken sources (FORISS, EU, SKATTEFUNN) and
writes one gzipped JSONL file per (source, run-date) to GCS. No
parsing, no state — raw immutable archive only.

Output path::

    gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/source={kilde}/{date}.jsonl.gz

Each line is one project record as returned by the Prosjektbanken
listing JSON, preserving ``id, title, organisations, yearsActive,
geographies, disciplines, currentActivity, _kilde``.

Modes
-----
``snapshot``
    Re-fetch the full archive of every selected source. Volumes (April
    2026): FORISS ≈ 44.6K, EU ≈ 5.1K, SKATTEFUNN ≈ 53.4K. Total ≈ 103K
    records. The Prosjektbanken page has no incremental "added since"
    filter, so the simplest correct strategy is to dump everything on
    each run. The downstream parser deduplicates by ``id``.

``daily``
    Fetch the most recent ``DAILY_MAX_RECORDS`` records sorted by
    ``date desc``, per source. Captures recently added projects without
    re-paginating the full archive. Cheaper and faster than snapshot.

Environment variables
---------------------
GCS_BUCKET : str
    Target GCS bucket. Default ``sondre_brreg_data``. Set to empty
    string for local-only mode (writes to ``./data/raw/``).
GCS_PREFIX : str
    GCS path prefix. Default ``prosjektbanken``.
RUN_MODE : str
    ``snapshot`` or ``daily``. Default ``snapshot``.
KILDER : str
    Comma-separated list of sources to fetch. Default
    ``FORISS,EU,SKATTEFUNN``.
DAILY_MAX_RECORDS : int
    Cap on records per source in ``daily`` mode. Default ``2000``.
PAGE_SIZE : int
    ``resultCount`` per HTTP request. Default ``2000``.
DELAY : float
    Seconds between requests. Default ``0.3``.

Known limitations
-----------------
- SkatteFUNN funding amounts are suppressed by Forskningsrådet
  (``totalFunding == -1``). Only project metadata is recoverable.
- Listing JSON exposes the company name (third element of each
  ``organisations`` tuple) but no organisasjonsnummer. Name → orgnr
  resolution is the parser's job, against Enhetsregisteret.
"""

import os
import sys
import json
import gzip
import tempfile
from datetime import date

from client import ProsjektbankenClient, SOURCES


GCS_BUCKET = os.environ.get("GCS_BUCKET", "sondre_brreg_data")
GCS_PREFIX = os.environ.get("GCS_PREFIX", "prosjektbanken")
RUN_MODE = os.environ.get("RUN_MODE", "snapshot")
KILDER = [k.strip() for k in os.environ.get("KILDER", ",".join(SOURCES)).split(",") if k.strip()]
DAILY_MAX_RECORDS = int(os.environ.get("DAILY_MAX_RECORDS", "2000"))
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "2000"))
DELAY = float(os.environ.get("DELAY", "0.3"))


def upload_jsonl(records, gcs_path):
    """Compress records to JSONL.gz and upload to GCS.

    Parameters
    ----------
    records : list of dict
        Project records.
    gcs_path : str
        Full GCS object path (excluding bucket name).
    """
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    with tempfile.NamedTemporaryFile(suffix=".jsonl.gz", delete=False) as tmp:
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tmp_path = tmp.name

    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(tmp_path)
    size = os.path.getsize(tmp_path)
    os.unlink(tmp_path)
    print(
        f"  Uploaded {gcs_path} ({size:,} bytes, {len(records):,} records)",
        flush=True,
    )


def write_jsonl_local(records, path):
    """Compress records to JSONL.gz on local filesystem.

    Parameters
    ----------
    records : list of dict
        Project records.
    path : str
        Local file path.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  Wrote {path} ({len(records):,} records)", flush=True)


def write_records(records, kilde, today_str):
    """Write records to GCS or local fallback.

    Parameters
    ----------
    records : list of dict
        Project records for one source.
    kilde : str
        Source code (FORISS / EU / SKATTEFUNN), lowercased in the path.
    today_str : str
        ISO date string used as filename.
    """
    rel = f"{GCS_PREFIX}/raw/source={kilde.lower()}/{today_str}.jsonl.gz"
    if GCS_BUCKET:
        upload_jsonl(records, rel)
    else:
        write_jsonl_local(records, f"./data/raw/source={kilde.lower()}/{today_str}.jsonl.gz")


def run_snapshot(client, kilder):
    """Fetch the full archive of every source and write one file per source.

    Parameters
    ----------
    client : ProsjektbankenClient
        API client instance.
    kilder : list of str
        Source codes to fetch.
    """
    today_str = date.today().isoformat()
    grand_total = 0
    for kilde in kilder:
        print(f"  Source: {kilde}", flush=True)
        records, total = client.paginate(kilde)
        print(f"  {kilde}: fetched {len(records):,} of {total:,}", flush=True)
        write_records(records, kilde, today_str)
        grand_total += len(records)
    print(f"\n  Snapshot complete: {grand_total:,} records across {len(kilder)} sources", flush=True)


def run_daily(client, kilder, max_records):
    """Fetch the most recent N records per source.

    Parameters
    ----------
    client : ProsjektbankenClient
        API client instance.
    kilder : list of str
        Source codes to fetch.
    max_records : int
        Cap per source.
    """
    today_str = date.today().isoformat()
    for kilde in kilder:
        print(f"  Source: {kilde} (max {max_records:,})", flush=True)
        records, total = client.paginate(kilde, max_records=max_records)
        print(f"  {kilde}: fetched {len(records):,} of {total:,}", flush=True)
        write_records(records, kilde, today_str)


def main():
    """Parse environment variables and dispatch to snapshot or daily mode."""
    print(f"{'=' * 60}", flush=True)
    print(f"  prosjektbanken-collector — mode: {RUN_MODE}", flush=True)
    print(f"  kilder: {KILDER}", flush=True)
    print(f"  page_size: {PAGE_SIZE}  delay: {DELAY}", flush=True)
    print(f"  {date.today().isoformat()}", flush=True)
    print(f"{'=' * 60}", flush=True)

    client = ProsjektbankenClient(delay=DELAY, page_size=PAGE_SIZE)

    if RUN_MODE == "snapshot":
        run_snapshot(client, KILDER)
    elif RUN_MODE == "daily":
        run_daily(client, KILDER, DAILY_MAX_RECORDS)
    else:
        print(f"Unknown RUN_MODE: {RUN_MODE}")
        sys.exit(1)


if __name__ == "__main__":
    main()
