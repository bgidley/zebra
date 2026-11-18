"""Oracle Cloud signup guidance and pre-flight confirmation (#277).

``/onboarding/signup/`` is a static, versioned guide; ``/onboarding/signup/confirm/`` stores
the user's non-secret answers (tenancy OCID, region, "I've done this" ticks). Both return 404
while ``ONBOARDING_ENABLED`` is off.
"""

from __future__ import annotations

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from zebra_agent_web.api import onboarding_preflight as pf
from zebra_agent_web.api.models import OnboardingSignupModel

# Bump whenever the guidance text changes; shown on the page with the verification date.
ONBOARDING_GUIDE_VERSION = "2026-11-16.1"
ONBOARDING_GUIDE_CHECKED = "2026-11-16"

CHECKLIST = (
    ("account_created", "I created my Oracle Cloud account with uk-london-1 as home region"),
    ("admin_mfa", "I made a dedicated admin user and turned on MFA"),
    ("payg_requested", "I asked for the Pay-As-You-Go upgrade (or chose to stay Always Free)"),
    ("budget_ack", "I understand a $1 budget alert is created for me in the next step"),
)


PAYG_OPTIONS = (
    ("none", "Always Free only"),
    ("pending", "Upgrade requested (pending)"),
    ("active", "Pay-As-You-Go active"),
)


def onboarding_enabled() -> bool:
    """The ``ONBOARDING_ENABLED`` master switch (default off)."""
    return bool(settings.ZEBRA_AGENT_SETTINGS.get("ONBOARDING_ENABLED", False))


def _state(user) -> dict:
    row = OnboardingSignupModel.objects.filter(user_id=user.pk).first()
    data = dict(row.data) if row else {}
    payg = data.get("payg")
    return {
        "tenancy_ocid": data.get("tenancy_ocid", ""),
        "region": data.get("region", pf.DEFAULT_REGION),
        "done": list(data.get("done", [])),
        "payg": payg if payg in pf.PAYG_STATES else "none",
    }


def is_ready(state: dict) -> bool:
    """Ready for the next wizard step: account and budget guidance acknowledged."""
    return "budget_ack" in state["done"] and "account_created" in state["done"]


def _context(request, state: dict, errors: dict | None = None, warnings=None) -> dict:
    return {
        "guide_version": ONBOARDING_GUIDE_VERSION,
        "guide_checked": ONBOARDING_GUIDE_CHECKED,
        "state": state,
        "checklist": CHECKLIST,
        "payg_options": PAYG_OPTIONS,
        "regions": pf.ALWAYS_FREE_26AI_REGIONS,
        "default_region": pf.DEFAULT_REGION,
        "errors": errors or {},
        "warnings": warnings or [],
        "ready": is_ready(state),
    }


def _gate(request):
    if not onboarding_enabled():
        raise Http404("Onboarding is off")
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    return None


def signup_guide(request):
    """GET the guide with this user's saved answers."""
    if (blocked := _gate(request)) is not None:
        return blocked
    return render(request, "pages/onboarding_signup.html", _context(request, _state(request.user)))


@require_POST
def signup_confirm(request):
    """Validate and store the pre-flight answers for the signed-in user."""
    if (blocked := _gate(request)) is not None:
        return blocked
    ocid = pf.validate_tenancy_ocid(request.POST.get("tenancy_ocid", ""))
    region = pf.validate_region(request.POST.get("region", ""))
    payg = request.POST.get("payg", "none")
    state = {
        "tenancy_ocid": ocid.value,
        "region": region.value or pf.DEFAULT_REGION,
        "done": [key for key, _ in CHECKLIST if request.POST.get(key)],
        "payg": payg if payg in pf.PAYG_STATES else "none",
    }
    errors = {}
    if not ocid.ok:
        errors["tenancy_ocid"] = ocid.error
    if not region.ok:
        errors["region"] = region.error
    if errors:
        # A rejected value is never echoed back or stored: it may be a pasted secret.
        return render(
            request, "pages/onboarding_signup.html", _context(request, state, errors), status=422
        )
    OnboardingSignupModel.objects.update_or_create(
        user_id=request.user.pk, defaults={"data": state}
    )
    return render(
        request, "pages/onboarding_signup.html", _context(request, state, warnings=region.warnings)
    )
