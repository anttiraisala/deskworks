"""Choosing the window placement backend (SPEC.md section 4).

The backends and their interface live in the `deskmap` library; `choose` is
tilepane's: it explains why when no backend is usable.
"""

from __future__ import annotations

from typing import Optional

from deskmap.backends import Backend, BackendError, Placement, WindowInfo  # noqa: F401 - re-exported


def choose() -> tuple[Optional[Backend], str]:
    """Return (backend, "") or (None, reason)."""
    from .. import doctor

    session = doctor.session_type()
    if session != "x11":
        return None, (f"no backend for a {session} session yet; only X11 is implemented "
                      "(run tilepane --doctor)")
    from deskmap.backends import x11

    ok, reason = x11.available()
    if not ok:
        return None, reason
    return x11.X11Backend(), ""
