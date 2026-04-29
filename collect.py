"""Top-level dispatcher for startup-sources-collector.

Selects which source to run based on the ``SOURCE`` environment variable
and invokes that source's ``collect.py``. Each source lives under
``sources/{source_name}/`` and exposes its own ``client.py`` and
``collect.py``.

Available sources
-----------------
``prosjektbanken``
    Forskningsrådets Prosjektbanken — three sub-sources (FORISS, EU,
    SKATTEFUNN). See ``sources/prosjektbanken/README.md``.

Environment variables
---------------------
SOURCE : str
    Source name to run. Default ``prosjektbanken``. Must match a
    subdirectory of ``sources/``.

All other environment variables are forwarded to the source's
``collect.py``.
"""

import os
import sys
import importlib.util


SOURCE = os.environ.get("SOURCE", "prosjektbanken")


def main():
    """Dispatch to the selected source's collect.py main function."""
    here = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(here, "sources", SOURCE)
    if not os.path.isdir(src_path):
        print(f"Unknown SOURCE: {SOURCE}", flush=True)
        print(f"Available sources: {sorted(os.listdir(os.path.join(here, 'sources')))}",
              flush=True)
        sys.exit(1)

    sys.path.insert(0, src_path)

    spec = importlib.util.spec_from_file_location(
        f"{SOURCE}_collect", os.path.join(src_path, "collect.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


if __name__ == "__main__":
    main()
