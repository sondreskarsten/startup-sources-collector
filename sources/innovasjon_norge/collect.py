"""Collector entrypoint: Innovasjon Norge tildelingsrapport CSV → raw on GCS.

Downloads the full tildelingsrapport CSV from Innovasjon Norge's
public Azure blob and writes verbatim to GCS. No parsing, no
encoding conversion — raw immutable archive only.

Output path::

    gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/{date}.csv

Modes
-----
``snapshot``
    Re-download the full CSV on every run. The blob is updated
    nightly by Innovasjon Norge; the parser deduplicates by
    (Org-nr, Innvilget dato, Underkategori, Innvilget beløp) since
    there is no stable per-tildeling key.

Environment variables
---------------------
GCS_BUCKET : str
    Target GCS bucket. Default ``sondre_brreg_data``. Empty = local-only.
GCS_PREFIX : str
    GCS path prefix. Default ``innovasjon_norge``.
RUN_MODE : str
    Only ``snapshot`` is supported. Default ``snapshot``.
DELAY : float
    Seconds between requests. Default ``0.3``.
"""

import os
import sys
import tempfile
from datetime import date

from client import InnovasjonNorgeClient


GCS_BUCKET = os.environ.get("GCS_BUCKET", "sondre_brreg_data")
GCS_PREFIX = os.environ.get("GCS_PREFIX", "innovasjon_norge")
RUN_MODE = os.environ.get("RUN_MODE", "snapshot")
DELAY = float(os.environ.get("DELAY", "0.3"))


def upload_bytes(body, gcs_path):
    """Upload bytes to GCS.

    Parameters
    ----------
    body : bytes
        File contents.
    gcs_path : str
        Full GCS object path (excluding bucket name).
    """
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(body)
        tmp_path = tmp.name

    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(tmp_path)
    size = os.path.getsize(tmp_path)
    os.unlink(tmp_path)
    print(f"  Uploaded {gcs_path} ({size:,} bytes)", flush=True)


def write_bytes_local(body, path):
    """Write bytes to local disk.

    Parameters
    ----------
    body : bytes
        File contents.
    path : str
        Local file path.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    print(f"  Wrote {path} ({len(body):,} bytes)", flush=True)


def write_csv(body, today_str):
    """Write the CSV to GCS or local fallback.

    Parameters
    ----------
    body : bytes
        CSV file contents.
    today_str : str
        ISO date string used as filename.
    """
    rel = f"{GCS_PREFIX}/raw/{today_str}.csv"
    if GCS_BUCKET:
        upload_bytes(body, rel)
    else:
        write_bytes_local(body, f"./data/raw/{today_str}.csv")


def run_snapshot(client):
    """Download the CSV and write to GCS.

    Parameters
    ----------
    client : InnovasjonNorgeClient
        API client instance.
    """
    today_str = date.today().isoformat()
    print(f"  Downloading tildelingsrapport ...", flush=True)
    body = client.download_csv()
    print(f"  CSV: {len(body):,} bytes", flush=True)
    write_csv(body, today_str)
    print(f"\n  Snapshot complete", flush=True)


def main():
    """Parse environment variables and dispatch to the snapshot run."""
    print(f"{'=' * 60}", flush=True)
    print(f"  innovasjon-norge-collector — mode: {RUN_MODE}", flush=True)
    print(f"  delay: {DELAY}", flush=True)
    print(f"  {date.today().isoformat()}", flush=True)
    print(f"{'=' * 60}", flush=True)

    client = InnovasjonNorgeClient(delay=DELAY)

    if RUN_MODE == "snapshot":
        run_snapshot(client)
    else:
        print(f"Unknown RUN_MODE: {RUN_MODE}")
        sys.exit(1)


if __name__ == "__main__":
    main()
