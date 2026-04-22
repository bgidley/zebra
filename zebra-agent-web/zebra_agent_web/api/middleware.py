"""Custom Django middleware for Zebra Agent Web."""

from __future__ import annotations

# URL prefixes that are always accessible even before first-run setup
_SETUP_EXEMPT_PREFIXES = (
    "/api/",
    "/setup",
    "/static/",
    "/admin/",
    "/ws/",
)


class SetupRequiredMiddleware:
    """Redirect all web UI requests to /setup/ until first-run setup is complete.

    API routes, static files, and the setup page itself are exempt so the
    daemon and external tools continue to work without a display name.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not any(request.path.startswith(p) for p in _SETUP_EXEMPT_PREFIXES):
            try:
                from zebra_agent_web.api.identity import is_setup_complete_sync

                if not is_setup_complete_sync():
                    from django.shortcuts import redirect

                    return redirect("/setup/")
            except Exception:
                pass  # DB unavailable (e.g. during test collection) — allow through
        return self.get_response(request)
