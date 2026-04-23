"""Passkey (WebAuthn) authentication views for Zebra Agent.

Provides passkey-only registration and authentication. No passwords.
"""

import base64
import json
import logging
import secrets
from datetime import UTC, datetime

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    parse_authentication_credential_json,
    parse_registration_credential_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.registration.verify_registration_response import VerifiedRegistration

from zebra_agent_web.api.models import WebAuthnCredential

logger = logging.getLogger(__name__)
User = get_user_model()

# In-memory challenge store (sufficient for single-user local-first deployment)
# Maps session key -> bytes challenge
_challenge_store: dict[str, bytes] = {}


def _get_rp_id() -> str:
    return getattr(settings, "WEBAUTHN_RP_ID", "localhost")


def _get_rp_name() -> str:
    return getattr(settings, "WEBAUTHN_RP_NAME", "Zebra Agent")


def _get_origin() -> str:
    return getattr(settings, "WEBAUTHN_ORIGIN", "http://localhost:8000")


# ===========================================================================
# Registration (setup / add passkey)
# ===========================================================================


@login_not_required
@require_POST
def begin_register(request):
    """Generate WebAuthn registration options.

    Returns JSON with options to pass to navigator.credentials.create().
    Requires ``username`` in POST body.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    username = data.get("username", "").strip()
    if not username:
        return JsonResponse({"error": "Username is required"}, status=400)

    # If this is the first user, allow any username. Otherwise require auth.
    if User.objects.exists() and not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)

    # Generate challenge
    challenge = secrets.token_bytes(32)
    _challenge_store[request.session.session_key or "setup"] = challenge

    # Build registration options
    options = generate_registration_options(
        rp_id=_get_rp_id(),
        rp_name=_get_rp_name(),
        user_id=username.encode(),
        user_name=username,
        user_display_name=username,
        challenge=challenge,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred.credential_id))
            for cred in WebAuthnCredential.objects.filter(user__username=username)
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    return JsonResponse(json.loads(options_to_json(options)))


@login_not_required
@require_POST
def complete_register(request):
    """Verify WebAuthn registration response and create user + credential.

    Expects JSON body with credential response from navigator.credentials.create().
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    username = data.get("username", "").strip()
    credential_json = data.get("credential")
    if not username or not credential_json:
        return JsonResponse({"error": "username and credential required"}, status=400)

    # Retrieve challenge
    session_key = request.session.session_key or "setup"
    challenge = _challenge_store.pop(session_key, None)
    if challenge is None:
        return JsonResponse({"error": "Registration challenge expired"}, status=400)

    try:
        credential = parse_registration_credential_json(json.dumps(credential_json))
        result: VerifiedRegistration = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
            require_user_verification=False,
        )
    except Exception as e:
        logger.exception("Registration verification failed")
        return JsonResponse({"error": f"Verification failed: {e}"}, status=400)

    # Get or create user
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"first_name": username},
    )

    # Store credential
    WebAuthnCredential.objects.create(
        user=user,
        credential_id=base64.urlsafe_b64encode(result.credential_id).decode("ascii").rstrip("="),
        public_key=result.credential_public_key,
        sign_count=result.sign_count,
        transports=[],
    )

    # Log the user in
    login(request, user)

    return JsonResponse({"success": True, "username": username, "created": created})


# ===========================================================================
# Authentication (sign in with passkey)
# ===========================================================================


@login_not_required
@require_POST
def begin_authenticate(request):
    """Generate WebAuthn authentication options.

    Returns JSON with options to pass to navigator.credentials.get().
    """
    challenge = secrets.token_bytes(32)
    _challenge_store[request.session.session_key or "auth"] = challenge

    # Allow any credential (discoverable credential / passkey)
    options = generate_authentication_options(
        rp_id=_get_rp_id(),
        challenge=challenge,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    return JsonResponse(json.loads(options_to_json(options)))


@login_not_required
@require_POST
def complete_authenticate(request):
    """Verify WebAuthn authentication response and log the user in.

    Expects JSON body with credential response from navigator.credentials.get().
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    credential_json = data.get("credential")
    if not credential_json:
        return JsonResponse({"error": "credential required"}, status=400)

    # Retrieve challenge first (before looking up credential)
    session_key = request.session.session_key or "auth"
    challenge = _challenge_store.pop(session_key, None)
    if challenge is None:
        return JsonResponse({"error": "Authentication challenge expired"}, status=400)

    # Find credential by ID
    credential_id_b64 = credential_json.get("id", "")

    # ensure padding is removed to match stored version
    stored_cred_id = credential_id_b64.rstrip("=")

    try:
        cred = WebAuthnCredential.objects.get(credential_id=stored_cred_id)
    except WebAuthnCredential.DoesNotExist:
        return JsonResponse({"error": "Unknown credential"}, status=400)

    try:
        auth_credential = parse_authentication_credential_json(json.dumps(credential_json))
        auth_result = verify_authentication_response(
            credential=auth_credential,
            expected_challenge=challenge,
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
            require_user_verification=False,
        )
    except Exception as e:
        logger.exception("Authentication verification failed")
        return JsonResponse({"error": f"Verification failed: {e}"}, status=400)

    # Update sign count and last used
    cred.sign_count = auth_result.new_sign_count
    cred.last_used_at = datetime.now(UTC)
    cred.save(update_fields=["sign_count", "last_used_at"])

    # Log the user in
    login(request, cred.user)

    return JsonResponse({"success": True, "username": cred.user.username})


# ===========================================================================
# Logout
# ===========================================================================


def do_logout(request):
    """Log the user out and redirect to login page."""
    logout(request)
    return HttpResponseRedirect(settings.LOGOUT_REDIRECT_URL)


# ===========================================================================
# Page views (HTML)
# ===========================================================================


@login_not_required
def setup_page(request):
    """First-time setup page: create user and register passkey."""
    if User.objects.exists():
        return HttpResponseRedirect("/auth/login/")
    return render(request, "pages/auth_setup.html")


@login_not_required
def login_page(request):
    """Sign-in page with passkey."""
    if request.user.is_authenticated:
        return HttpResponseRedirect("/")
    return render(request, "pages/auth_login.html")
