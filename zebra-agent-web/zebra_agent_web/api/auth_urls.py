"""URL patterns for passkey authentication.

Provides WebAuthn registration and authentication endpoints.
"""

from django.urls import path

from zebra_agent_web.api.auth_views import (
    begin_authenticate,
    begin_register,
    complete_authenticate,
    complete_register,
    do_logout,
    login_page,
    setup_page,
)

urlpatterns = [
    path("setup/", setup_page, name="auth_setup"),
    path("login/", login_page, name="auth_login"),
    path("logout/", do_logout, name="auth_logout"),
    path("begin-register/", begin_register, name="auth_begin_register"),
    path("complete-register/", complete_register, name="auth_complete_register"),
    path("begin-authenticate/", begin_authenticate, name="auth_begin_authenticate"),
    path("complete-authenticate/", complete_authenticate, name="auth_complete_authenticate"),
]
