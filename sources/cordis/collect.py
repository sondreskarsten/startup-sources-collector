"""Collector entrypoint: CORDIS bulk CSV exports → raw ZIP on GCS.

Downloads the CORDIS CSV bundle ZIP for each Framework Programme and
writes verbatim to GCS. No parsing, no unzipping — raw immutable
archive only.

Output path::

    gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/programme={programme}/{date}.zip

Modes
-----
``snapshot``
    Re-download all three programme ZIPs on every run. Total ~119 MB
    compressed across HORIZON Europe, H2020, FP7. The Publications
    Office refreshes monthly; the parser deduplicates by ``projectID``.

Environment variables
---------------------
GCS_BUCKET : str
    Target GCS bucket. Default ``sondre_brreg_data``. Empty = local-only.
GCS_PREFIX : str
    GCS path prefix. Default ``cordis``.
RUN_MODE : str
    Only ``snapshot`` is supported. Default ``snapshot``.
PROGRAMMES : str
    Comma-separated list of programme codes. Default ``horizon,h2020,fp7``.
DELAY : float
    Seconds between requests. Default ``0.3``.
"""

import os
import sys
import tempfile
from datetime import date

from client import CordisClient, PROGRAMMES


GCS_BUCKET = os.environ.get("GCS_BUCKET", "sondre_brreg_data")
GCS_PREFIX = os.environ.get("GCS_PREFIX", "cordis")
RUN_MODE = os.environ.get("RUN_MODE", "snapshot")
PROGS = [
    p.strip().lower()
    for p in os.environ.get("PROGRAMMES", ",".join(PROGRAMMES.keys())).split(",")
    if p.strip()
]
DELAY = float(os.environ.get("DELAY", "0.3"))


def upload_bytes(body, gcs_path):
    """Upload a bytes body to GCS.

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

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(body)
        tmp_path = tmp.name

    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(tmp_path)
    size = os.path.getsize(tmp_path)
    os.unlink(tmp_path)
    print(f"  Uploaded {gcs_path} ({size:,} bytes)", flush=True)


def write_bytes_local(body, path):
    """Write a bytes body to local disk.

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


def write_zip(body, programme, today_str):
    """Write one programme's ZIP to GCS or local fallback.

    Parameters
    ----------
    body : bytes
        ZIP file contents.
    programme : str
        Programme code (``horizon`` / ``h2020`` / ``fp7``).
    today_str : str
        ISO date string used as filename.
    """
    rel = f"{GCS_PREFIX}/raw/programme={programme}/{today_str}.zip"
    if GCS_BUCKET:
        upload_bytes(body, rel)
    else:
        write_bytes_local(body, f"./data/raw/programme={programme}/{today_str}.zip")


def run_snapshot(client, programmes):
    """Download each programme's ZIP and write to GCS.

    Parameters
    ----------
    client : CordisClient
        API client instance.
    programmes : list of str
        Programme codes to fetch.
    """
    today_str = date.today().isoformat()
    for programme in programmes:
        if programme not in PROGRAMMES:
            print(f"  Skipping unknown programme: {programme}", flush=True)
            continue
        print(f"  Downloading programme={programme} ...", flush=True)
        body = client.download_zip(programme)
        print(f"  {programme}: {len(body):,} bytes", flush=True)
        write_zip(body, programme, today_str)
    print(f"\n  Snapshot complete: {len(programmes)} programmes", flush=True)


def main():
    """Parse environment variables and dispatch to the snapshot run."""
    print(f"{'=' * 60}", flush=True)
    print(f"  cordis-collector — mode: {RUN_MODE}", flush=True)
    print(f"  programmes: {PROGS}", flush=True)
    print(f"  delay: {DELAY}", flush=True)
    print(f"  {date.today().isoformat()}", flush=True)
    print(f"{'=' * 60}", flush=True)

    client = CordisClient(delay=DELAY)

    if RUN_MODE == "snapshot":
        run_snapshot(client, PROGS)
    else:
        print(f"Unknown RUN_MODE: {RUN_MODE}")
        sys.exit(1)


if __name__ == "__main__":
    main()
