"""The /onboarding/ wizard pages (#276) and the owner's switch for them.

Wizard views are anonymous (``login_not_required``), 404 while onboarding is off, rate
limited per IP and run with no request user, so the stores never scope to (or stamp) anyone.
They read only the session's own process: see ``zebra_agent_web.api.onboarding``.
No view here creates a user or touches a passkey view (a source-scan test enforces it).
"""

from __future__ import annotations

import functools
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from zebra_agent_web.api import agent_engine, engine
from zebra_agent_web.api import onboarding as ob
from zebra_agent_web.api import onboarding_access as access
from zebra_agent_web.api import onboarding_callback as cb
from zebra_agent_web.api import onboarding_preflight as pf
from zebra_agent_web.middleware import _current_user_id_var

logger = logging.getLogger(__name__)

_WIZARD = "onboarding/wizard.html"
_STEP_PARTIAL = "onboarding/partials/step.html"


def _wizard_view(view):
    """Anonymous, 404 while off, per-IP request limit, no request user for the stores."""

    @login_not_required
    @functools.wraps(view)
    async def wrapper(request, *args, **kwargs):
        if not await ob.is_enabled():
            raise Http404("Not found")
        if not ob.allow_request(ob.client_ip(request)):
            return _message(request, "Too many requests. Please wait a minute.", 429)
        reset = _current_user_id_var.set(None)
        try:
            return await view(request, *args, **kwargs)
        except ob.OnboardingRefused as e:
            return _message(request, e.message, e.status)
        finally:
            _current_user_id_var.reset(reset)

    return wrapper


def _message(request, message: str, status: int) -> HttpResponse:
    return render(request, _WIZARD, {"message": message}, status=status)


async def _engine():
    await agent_engine.ensure_initialized()
    await engine.ensure_initialized()
    return engine.get_engine()


def _set_cookie(request, response: HttpResponse, process_id: str, nonce: str) -> None:
    response.set_cookie(
        ob.COOKIE_NAME,
        ob.make_token(process_id, nonce),
        max_age=ob.max_age_seconds(),
        httponly=True,
        secure=request.is_secure() or settings.SESSION_COOKIE_SECURE,
        samesite="Lax",
        path="/onboarding/",
    )


async def _session(request):
    wf_engine = await _engine()
    process = await ob.load_session(wf_engine.store, request.COOKIES.get(ob.COOKIE_NAME))
    return wf_engine, process


async def _halted() -> bool:
    from zebra_agent_web.api.kill_switch import is_halted

    return await is_halted()


_ROUTE_LABELS = {
    "done": "Done, next step",
    ob.PROBLEM_ROUTE: "Something went wrong",
    "policy": "I can't use the stack: show the policy for my admin",
    "back": "Back",
}


def _session_name(process) -> str:
    """The short name the visitor chose on the access step (or the placeholder)."""
    output = (process.properties or {}).get("__task_output_access") or {}
    return access.clean_name(output.get("name") if isinstance(output, dict) else None)


async def _render_wizard(
    request,
    wf_engine,
    process,
    *,
    errors=None,
    values=None,
    status=200,
    new_token: str = "",
    message: str = "",
):
    from zebra.forms import schema_to_form

    state = await ob.wizard_state(wf_engine.store, process)
    parsed = ob.read_token(request.COOKIES.get(ob.COOKIE_NAME))
    name = _session_name(process)
    context = {
        "state": state,
        "form": schema_to_form(state.schema) if state.task_id else None,
        "field_errors": errors or {},
        "submitted_values": values or {},
        "halted": await _halted(),
        "route_labels": _ROUTE_LABELS,
        "resume_url": resume_url(request, process.id, parsed[1]) if parsed else "",
        "message": message,
        # Access step (#278 S3) and callback (S4) panels
        "stack": access.stack(),
        "policy": access.policy_text(name) if state.panel == "policy" else None,
        "zebra_name": name,
        "callback_token": cb.token_status(process.properties or {}),
        "new_token": new_token,
        "callback_url": request.build_absolute_uri(reverse("onboarding_callback")),
    }
    if state.current_key == "signup" and not state.retry:
        context.update(
            guide_version=pf.ONBOARDING_GUIDE_VERSION,
            guide_checked=pf.ONBOARDING_GUIDE_CHECKED,
            regions=pf.ALWAYS_FREE_26AI_REGIONS,
            default_region=pf.DEFAULT_REGION,
        )
    template = _STEP_PARTIAL if request.headers.get("HX-Request") else _WIZARD
    response = render(request, template, context, status=status)
    if parsed is not None:
        # Re-sign on each visit, so the 30 days count from the last visit
        _set_cookie(request, response, process.id, parsed[1])
    return response


@_wizard_view
async def wizard(request):
    """The wizard: the visitor's current step, or a start screen without a session."""
    wf_engine, process = await _session(request)
    if process is None:
        return render(request, _WIZARD, {"halted": await _halted()})
    return await _render_wizard(request, wf_engine, process)


@require_POST
@_wizard_view
async def start(request):
    """Start a new session: one Onboarding process for this visitor."""
    if await _halted():
        return _message(request, "The wizard is paused right now. Please come back later.", 503)
    if not ob.allow_new_session(ob.client_ip(request)):
        return _message(request, "Too many new sessions from your network. Try again later.", 429)
    wf_engine = await _engine()
    process, nonce = await ob.start_session(wf_engine, agent_engine.get_library())
    response = redirect(reverse("onboarding_wizard"))
    _set_cookie(request, response, process.id, nonce)
    return response


@require_http_methods(["GET"])
@_wizard_view
async def resume(request, token: str):
    """A resume link: set the cookie from it, then show the wizard at the same step."""
    wf_engine = await _engine()
    process = await ob.load_session(wf_engine.store, token)
    if process is None:
        return _message(
            request, "This resume link no longer works. You can start again below.", 410
        )
    response = redirect(reverse("onboarding_wizard"))
    _set_cookie(request, response, process.id, ob.read_token(token)[1])
    return response


@require_POST
@_wizard_view
async def submit(request):
    """Complete the visitor's current step from the form."""
    wf_engine, process = await _session(request)
    if process is None:
        return _message(request, "Your session has ended. You can start again.", 403)
    if await _halted():
        return _message(request, "The wizard is paused right now. Please come back later.", 503)
    raw = {k: v for k, v in request.POST.items() if k not in ("csrfmiddlewaretoken", "task_id")}
    route = raw.pop("next_route", None)
    try:
        errors = await ob.submit_step(
            wf_engine, process, request.POST.get("task_id", ""), raw, route
        )
    except ob.OnboardingRefused as e:
        if e.status == 409:
            return await _render_wizard(request, wf_engine, process, status=409)
        raise
    if errors:
        # A rejected value may be a pasted secret: it is never shown back
        kept = {k: v for k, v in raw.items() if k not in errors}
        return await _render_wizard(
            request, wf_engine, process, errors=errors, values=kept, status=400
        )
    if request.headers.get("HX-Request"):
        process = await wf_engine.store.load_process(process.id)
        return await _render_wizard(request, wf_engine, process)
    return redirect(reverse("onboarding_wizard"))


@require_POST
@_wizard_view
async def new_link(request):
    """Rotate the nonce: earlier cookies and resume links stop working."""
    wf_engine, process = await _session(request)
    if process is None:
        return _message(request, "Your session has ended. You can start again.", 403)
    nonce = await ob.rotate_nonce(wf_engine.store, process.id)
    response = redirect(reverse("onboarding_wizard") + "#resume")
    _set_cookie(request, response, process.id, nonce)
    return response


@require_POST
@_wizard_view
async def forget(request):
    """End the session: invalidate its token, fail its process, drop the cookie."""
    wf_engine, process = await _session(request)
    response = redirect(reverse("onboarding_wizard"))
    if process is not None:
        await ob.forget_session(wf_engine, process.id)
    response.delete_cookie(ob.COOKIE_NAME, path="/onboarding/")
    return response


# ---------------------------------------------------------------------------
# Access step and callback (#278 S3, S4)
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
@_wizard_view
async def revoke(request):
    """How to undo everything: reachable from every terminal state, with or without a session."""
    name = access.NAME_PLACEHOLDER
    if request.COOKIES.get(ob.COOKIE_NAME):
        _wf_engine, process = await _session(request)
        if process is not None:
            name = _session_name(process)
    return render(
        request,
        "onboarding/revoke.html",
        {"steps": access.revoke_steps(name), "zebra_name": name},
    )


@require_POST
@_wizard_view
async def callback_token(request):
    """Make (or rotate) the session's one-time callback token and show it once."""
    wf_engine, process = await _session(request)
    if process is None:
        return _message(request, "Your session has ended. You can start again.", 403)
    if await _halted():
        return _message(request, "The wizard is paused right now. Please come back later.", 503)
    state = await ob.wizard_state(wf_engine.store, process)
    if state.panel not in ("provision", "await"):
        return await _render_wizard(request, wf_engine, process, status=409)
    token = await cb.issue_token(wf_engine.store, process.id)
    process = await wf_engine.store.load_process(process.id)
    response = await _render_wizard(request, wf_engine, process, new_token=token)
    response["Cache-Control"] = "no-store"
    return response


@require_POST
@_wizard_view
async def manual_instance(request):
    """The visitor pastes their instance URL: the same control proof as the callback."""
    wf_engine, process = await _session(request)
    if process is None:
        return _message(request, "Your session has ended. You can start again.", 403)
    if await _halted():
        return _message(request, "The wizard is paused right now. Please come back later.", 503)
    if not ob.allow("instance", ob.client_ip(request), cb.CALLBACKS_PER_IP_MINUTE, 60):
        return _message(request, "Too many checks. Please wait a minute.", 429)
    try:
        await cb.manual_instance(wf_engine, process, request.POST.get("instance_url", ""))
    except cb.CallbackError as e:
        return await _render_wizard(request, wf_engine, process, status=e.status, message=e.message)
    return redirect(reverse("onboarding_wizard"))


def _json(payload: dict, status: int) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store"
    return response


@csrf_exempt
@login_not_required
@require_POST
async def callback(request):
    """``POST /onboarding/callback/``: the new instance calls home (contract: design §4).

    JSON in ``{token, instance_url, version?, commons_fingerprint?}``; JSON out ``{status}``
    or ``{error}``. 200 done; 400 bad body; 404 onboarding off; 409 session not waiting yet;
    410 unknown, used, rotated or expired token; 413 body over 4 KB; 422 control proof
    failed (token stays unused); 429 rate limited; 503 paused.
    """
    if not await ob.is_enabled():
        raise Http404("Not found")
    if not ob.allow("callback", ob.client_ip(request), cb.CALLBACKS_PER_IP_MINUTE, 60):
        return _json({"error": "Too many requests; retry later."}, 429)
    if await _halted():
        return _json({"error": "Paused; retry later."}, 503)
    reset = _current_user_id_var.set(None)
    try:
        await cb.handle_callback(await _engine(), request.body)
    except cb.CallbackError as e:
        return _json({"error": e.message}, e.status)
    finally:
        _current_user_id_var.reset(reset)
    return _json({"status": "ok"}, 200)


def resume_url(request, process_id: str, nonce: str) -> str:
    """The absolute resume link for a session."""
    return request.build_absolute_uri(
        reverse("onboarding_resume", kwargs={"token": ob.make_token(process_id, nonce)})
    )


# ---------------------------------------------------------------------------
# The owner's switch (signed in; not gated by the switch itself)
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
async def manage(request):
    """Owner-only: switch the wizard on or off and see how it is used (counts only)."""
    from zebra_agent_web.api.commons_identity import is_owner

    user = await request.auser()
    if not user.is_authenticated:
        # A constant "next", never the request path (CodeQL py/url-redirection, #276)
        return redirect(f"{settings.LOGIN_URL}?next={reverse('onboarding_manage')}")
    owner = await is_owner(user)
    if request.method == "POST":
        if not owner:
            return HttpResponseForbidden("Only the owner can switch onboarding on or off.")
        await ob.set_owner_switch(request.POST.get("enabled") == "1")
        return redirect(reverse("onboarding_manage"))
    context = {
        "is_owner": owner,
        "env_enabled": bool(ob.config("ENABLED")),
        "owner_enabled": await ob.owner_switch(),
        "enabled": await ob.is_enabled(),
        "live_sessions": await ob.live_session_count(),
        "max_live_sessions": ob.config("MAX_LIVE_SESSIONS"),
        "spent_today": await ob.spent_today(),
        "daily_cap": ob.config("DAILY_COST_CAP_USD"),
        "session_cap": ob.config("SESSION_COST_CAP_USD"),
    }
    return render(request, "onboarding/manage.html", context)


# ---------------------------------------------------------------------------
# The #277 signup URLs, kept as redirects (#312): the guide is now wizard step 1
# ---------------------------------------------------------------------------


@login_not_required
@csrf_exempt
@require_http_methods(["GET", "POST"])
async def legacy_signup(request):
    """``/onboarding/signup/`` and ``signup/confirm/``: 404 while off, else on to the wizard.

    Nothing is read or stored here (a POST body is ignored), so skipping CSRF is safe and a
    POST gets the same 404 as a GET while onboarding is off.
    """
    if not await ob.is_enabled():
        raise Http404("Not found")
    return redirect(reverse("onboarding_wizard"), permanent=False)
