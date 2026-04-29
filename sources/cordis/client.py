"""HTTP client for CORDIS bulk CSV exports.

CORDIS (Community Research and Development Information Service) is the
European Commission's primary public source of EU-funded research and
innovation projects. The Publications Office maintains bulk CSV
exports for each Framework Programme, downloadable as ZIP bundles
from ``cordis.europa.eu/data/``.

Three programmes are exposed:

* ``HORIZON`` — Horizon Europe (2021–2027). Currently active; data
  refreshed monthly. ~30 MB ZIP, ~117 MB unzipped (April 2026).
* ``H2020`` — Horizon 2020 (2014–2020). Closed programme; data is
  stable but corrections still appear. ~55 MB ZIP.
* ``FP7`` — Seventh Framework Programme (2007–2013). Closed; ~33 MB ZIP.

Each ZIP contains the same file set:

* ``project.csv`` — one row per project (id, acronym, dates,
  totalCost, ecMaxContribution, status).
* ``organization.csv`` — one row per (project, organisation)
  participation (projectID, organisationID, **vatNumber**, **name**,
  **country**, role, ecContribution). The Norwegian-relevant subset
  is ``country == "NO"``; ``vatNumber`` typically encodes the
  organisasjonsnummer for NO entities.
* ``topics.csv``, ``legalBasis.csv``, ``euroSciVoc.csv``,
  ``webLink.csv``, ``policyPriorities.csv``, ``webItem.csv`` —
  reference and metadata tables.
* ``information.zip`` — nested zip of release notes / data dictionary
  PDFs.

The collector downloads the three ZIPs verbatim and writes them as
raw bytes to GCS. The parser unzips and ingests the CSVs.

License: Creative Commons Attribution 4.0 International (CC BY 4.0).
"""

import time

import requests


CORDIS_BASE = "https://cordis.europa.eu/data"
PROGRAMMES = {
    "horizon": f"{CORDIS_BASE}/cordis-HORIZONprojects-csv.zip",
    "h2020": f"{CORDIS_BASE}/cordis-h2020projects-csv.zip",
    "fp7": f"{CORDIS_BASE}/cordis-fp7projects-csv.zip",
}


class CordisClient:
    """HTTP client for CORDIS bulk CSV exports.

    Parameters
    ----------
    delay : float
        Seconds to sleep between successful requests. Default ``0.3``.

    Attributes
    ----------
    _request_count : int
        Running count of HTTP requests issued.

    Examples
    --------
    >>> c = CordisClient()
    >>> body = c.download_zip("horizon")
    >>> len(body) > 1_000_000
    True
    """

    def __init__(self, delay=0.3):
        self.delay = delay
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; startup-sources-collector; "
            "+https://github.com/sondreskarsten/startup-sources-collector)"
        )
        self._request_count = 0

    def _get(self, url, timeout=600, stream=False):
        """Execute a GET with progressive backoff on HTTP 429 and 5xx.

        Parameters
        ----------
        url : str
            Full URL.
        timeout : int
            Per-request timeout in seconds. Default ``600``
            (CORDIS ZIPs are 30–55 MB).
        stream : bool
            Whether to stream the response.

        Returns
        -------
        requests.Response

        Raises
        ------
        RuntimeError
            If all 5 retry attempts are exhausted.
        requests.HTTPError
            On any non-200 / non-429 / non-5xx HTTP status.
        """
        backoffs = [5, 10, 20, 30, 60]
        for attempt in range(len(backoffs)):
            self._request_count += 1
            r = self._session.get(url, timeout=timeout, stream=stream)
            if r.status_code == 429 or r.status_code >= 500:
                sleep_s = backoffs[attempt]
                print(
                    f"  {r.status_code} at request #{self._request_count}, "
                    f"sleeping {sleep_s}s",
                    flush=True,
                )
                time.sleep(sleep_s)
                continue
            r.raise_for_status()
            time.sleep(self.delay)
            return r
        raise RuntimeError(f"Failed after {len(backoffs)} retries: {url}")

    def download_zip(self, programme):
        """Download one programme's CSV bundle ZIP as raw bytes.

        Parameters
        ----------
        programme : str
            One of ``horizon``, ``h2020``, ``fp7``.

        Returns
        -------
        bytes
            ZIP body, unmodified.

        Raises
        ------
        KeyError
            If ``programme`` is not in :data:`PROGRAMMES`.
        """
        url = PROGRAMMES[programme]
        r = self._get(url)
        return r.content
