"""HTTP client for Forskningsrådets Prosjektbanken.

Scrapes ``prosjektbanken.forskningsradet.no`` by extracting the
``__NEXT_DATA__`` JSON blob embedded in each server-rendered page.

Three sources are exposed via the ``Kilde`` query parameter:

* ``FORISS`` — Forskningsrådet competitive grants from 2004 (~44.6K projects).
* ``EU`` — EU projects with Norwegian participation (FP7, Horizon 2020,
  Horizon Europe). Sourced from eCorda. Funding amounts are the
  Norwegian-only share, distributed across project years (~5.1K).
* ``SKATTEFUNN`` — Approved SkatteFUNN tax-deduction projects from 2002
  (~53.4K). Per-project funding is suppressed (``totalFunding == -1``)
  per Forskningsrådet policy. Aggregated statistics suppress samples
  with fewer than 5 projects.

Each page-level record carries ``id, title, organisations, yearsActive,
geographies, disciplines, currentActivity``. ``organisations`` is a list
of ``[sector_label, type, name, ...]`` tuples — the third element is the
company or institution name. SkatteFUNN records mark
``Bedriftens prosjektansvarlig: Ikke tilgjengelig`` on the project
detail page; the company name is still present in the ``organisations``
tuple of the listing JSON.

Pagination uses offset stride; the API returns fewer records than
``resultCount`` when the end of the list is reached. Empirical sweet
spot is ``resultCount=2000`` (~3.3 MB per response).
"""

import json
import re
import time

import requests


BASE = "https://prosjektbanken.forskningsradet.no"
SOURCES = ["FORISS", "EU", "SKATTEFUNN"]
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


class ProsjektbankenClient:
    """HTTP client for the Prosjektbanken listing pages.

    Parameters
    ----------
    delay : float
        Seconds to sleep between successful requests. Default ``0.3``.
    page_size : int
        ``resultCount`` query parameter. Default ``2000``.

    Attributes
    ----------
    _request_count : int
        Running count of HTTP GETs issued.

    Examples
    --------
    >>> c = ProsjektbankenClient()
    >>> records, total = c.fetch_page("SKATTEFUNN", 0)
    >>> records[0]["source"]
    'SKATTEFUNN'
    """

    def __init__(self, delay=0.3, page_size=2000):
        self.delay = delay
        self.page_size = page_size
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; prosjektbanken-collector; "
            "+https://github.com/sondreskarsten/prosjektbanken-collector)"
        )
        self._session.headers["Accept"] = "text/html,application/xhtml+xml"
        self._request_count = 0

    def _get(self, path, params=None):
        """Execute a GET with progressive backoff on HTTP 429 and 5xx.

        Parameters
        ----------
        path : str
            URL path relative to BASE.
        params : dict or None
            URL query parameters.

        Returns
        -------
        str
            Response body as text.

        Raises
        ------
        RuntimeError
            If all 5 retry attempts are exhausted.
        requests.HTTPError
            On non-200 / non-429 / non-5xx HTTP status.
        """
        url = f"{BASE}{path}"
        backoffs = [5, 10, 20, 30, 60]
        for attempt in range(len(backoffs)):
            self._request_count += 1
            r = self._session.get(url, params=params, timeout=120)
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
            return r.text
        raise RuntimeError(f"Failed after {len(backoffs)} retries: {url}")

    def fetch_page(self, kilde, offset, sort_by="date", sort_order="desc"):
        """Fetch one listing page and parse the embedded JSON.

        Parameters
        ----------
        kilde : str
            One of ``FORISS``, ``EU``, ``SKATTEFUNN``.
        offset : int
            Pagination offset (0-indexed).
        sort_by : str
            Sort key. Default ``date``.
        sort_order : str
            ``asc`` or ``desc``. Default ``desc``.

        Returns
        -------
        records : list of dict
            Project records from the listing page.
        total : int
            Total hits for the current filter (from ``pagination.totalHits``).
        """
        params = {
            "Kilde": kilde,
            "Sprak": "no",
            "sortBy": sort_by,
            "sortOrder": sort_order,
            "resultCount": self.page_size,
            "offset": offset,
            "view": "projects",
        }
        html = self._get("/explore/projects", params=params)
        m = NEXT_DATA_RE.search(html)
        data = json.loads(m.group(1))
        pl = data["props"]["pageProps"]["initialState"]["PROJECTLIST"]
        records = pl.get("projects", [])
        total = pl.get("pagination", {}).get("totalHits", 0)
        return records, total

    def paginate(self, kilde, max_records=None):
        """Paginate through all records for one source.

        Iterates pages by stride ``self.page_size`` until a page returns
        fewer than ``page_size`` records. Each record is annotated with
        ``_kilde`` for downstream provenance.

        Parameters
        ----------
        kilde : str
            One of ``FORISS``, ``EU``, ``SKATTEFUNN``.
        max_records : int or None
            Optional cap on records to fetch (for daily mode). ``None``
            means unbounded.

        Returns
        -------
        records : list of dict
            All project records for the source.
        total : int
            Reported total hits at the time of first fetch.
        """
        offset = 0
        all_records = []
        total = None
        while True:
            records, t = self.fetch_page(kilde, offset)
            if total is None:
                total = t
            for rec in records:
                rec["_kilde"] = kilde
            all_records.extend(records)
            if len(records) < self.page_size:
                break
            if max_records is not None and len(all_records) >= max_records:
                break
            offset += self.page_size
            if offset % (10 * self.page_size) == 0:
                print(
                    f"    {kilde} offset {offset:,}, "
                    f"{len(all_records):,} of {total:,} records so far",
                    flush=True,
                )
        return all_records, total
