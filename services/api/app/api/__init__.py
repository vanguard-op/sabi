"""API package: dependencies, health, and the versioned router.

Module routers
--------------
Each domain module under ``app/<name>/`` exposes ``router: APIRouter`` in
``app/<name>/router.py``. The app factory in ``app.main`` discovers these
modules and mounts each under ``/v1``, so the module declares its own paths
without the version prefix. A module whose directory has not landed is skipped.
"""

from __future__ import annotations
