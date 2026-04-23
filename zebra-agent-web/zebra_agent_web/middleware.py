"""Custom middleware for Zebra Agent Web.

Provides setup redirect: if no users exist, all requests redirect to the
setup page so the first admin can register a passkey.
"""

import asyncio

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.utils.decorators import sync_and_async_middleware

User = get_user_model()

_SETUP_URL = "/auth/setup/"
_LOGIN_URL = "/auth/login/"
_AUTH_PREFIX = "/auth/"
_STATIC_PREFIX = "/static/"

# URLs that are always allowed even when no users exist
_ALWAYS_ALLOWED = {
    _SETUP_URL,
    "/auth/begin-register/",
    "/auth/complete-register/",
    "/auth/begin-authenticate/",
    "/auth/complete-authenticate/",
    "/api/health/",
    "/api/metrics/",
}


def _is_exempt(path: str) -> bool:
    """Return True if the path is exempt from the setup redirect."""
    if path.startswith(_STATIC_PREFIX):
        return True
    if path.startswith(_AUTH_PREFIX):
        return True
    if path in _ALWAYS_ALLOWED:
        return True
    return False


@sync_and_async_middleware
def SetupRedirectMiddleware(get_response):
    """Redirect to setup page when no users exist.

    If the user database is empty, every request is redirected to
    ``/auth/setup/`` so the first user can create an account and
    register a passkey. Once at least one user exists, this
    middleware is a no-op.
    """
    if asyncio.iscoroutinefunction(get_response):
        async def middleware(request):
            if _is_exempt(request.path_info):
                return await get_response(request)
            
            # Fast check: skip DB if we already know users exist in this process
            if getattr(settings, "_USERS_EXIST_CACHE", False):
                return await get_response(request)

            if not await User.objects.aexists():
                return HttpResponseRedirect(_SETUP_URL)
            
            # Cache the fact that users exist to avoid DB checks on every request
            settings._USERS_EXIST_CACHE = True
            return await get_response(request)
    else:
        def middleware(request):
            if _is_exempt(request.path_info):
                return get_response(request)
                
            if getattr(settings, "_USERS_EXIST_CACHE", False):
                return get_response(request)

            if not User.objects.exists():
                return HttpResponseRedirect(_SETUP_URL)
                
            settings._USERS_EXIST_CACHE = True
            return get_response(request)
    return middleware
