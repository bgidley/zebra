"""The onboarding access step's content (#278, slice S3): deploy link, policy text, revoke.

Option A (default) is a "Deploy to Oracle Cloud" link to the published Resource Manager stack:
the visitor applies it in their own tenancy and this host receives nothing. Option B in v1
only *shows* the least-privilege policy text for the visitor's admin; no key is ever uploaded.
The revoke steps are the last screen of the step and reachable from every terminal state.

The policy text must match ``specs/onboarding-design.md`` section 3 exactly (a test compares
them). See that file for why each grant is there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from zebra_agent_web.api import onboarding as ob

#: Resource Manager's "Deploy to Oracle Cloud" entry point (the stack zip must be public).
DEPLOY_BASE = "https://cloud.oracle.com/resourcemanager/stacks/create"
#: A short name the visitor picks for their compartment, ``zebra-<name>``.
NAME_PATTERN = r"^[a-z][a-z0-9-]{0,19}$"
_NAME = re.compile(NAME_PATTERN)
NAME_PLACEHOLDER = "<name>"

COMPARTMENT_POLICY = """\
Allow group zebra-<name>-admins to manage instance-family in compartment zebra-<name>
Allow group zebra-<name>-admins to manage virtual-network-family in compartment zebra-<name>
Allow group zebra-<name>-admins to manage autonomous-database-family in compartment zebra-<name>
Allow group zebra-<name>-admins to manage vaults in compartment zebra-<name>
Allow group zebra-<name>-admins to manage keys in compartment zebra-<name>
Allow group zebra-<name>-admins to manage secret-family in compartment zebra-<name>
Allow group zebra-<name>-admins to manage object-family in compartment zebra-<name>
Allow group zebra-<name>-admins to read compartments in compartment zebra-<name>"""

TENANCY_POLICY = """\
Allow group zebra-<name>-admins to manage usage-budgets in tenancy
Allow group zebra-<name>-admins to manage quota in tenancy"""

RUNTIME_POLICY = """\
Dynamic group zebra-<name>-instances:
  Any {instance.compartment.id = '<compartment ocid>'}
Allow dynamic-group zebra-<name>-instances to read secret-family in compartment zebra-<name>
Allow dynamic-group zebra-<name>-instances to read object-family in compartment zebra-<name>"""


def clean_name(name: object) -> str:
    """*name* if it is a valid short name, else the ``<name>`` placeholder."""
    return name if isinstance(name, str) and _NAME.match(name) else NAME_PLACEHOLDER


@dataclass(frozen=True)
class PolicyText:
    """The three policy blocks with ``<name>`` filled in."""

    compartment: str
    tenancy: str
    runtime: str


def policy_text(name: object) -> PolicyText:
    """The design's policy text for compartment ``zebra-<name>``."""
    n = clean_name(name)
    return PolicyText(
        compartment=COMPARTMENT_POLICY.replace(NAME_PLACEHOLDER, n),
        tenancy=TENANCY_POLICY.replace(NAME_PLACEHOLDER, n),
        runtime=RUNTIME_POLICY.replace(NAME_PLACEHOLDER, n),
    )


@dataclass(frozen=True)
class Stack:
    """The published stack, or ``deploy_url`` empty while none is configured (#283)."""

    zip_url: str
    sha256: str
    deploy_url: str

    @property
    def available(self) -> bool:
        return bool(self.deploy_url)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def stack() -> Stack:
    """The configured stack zip (``ONBOARDING_STACK_ZIP_URL``); unavailable unless https."""
    zip_url = str(ob.config("STACK_ZIP_URL") or "").strip()
    sha = str(ob.config("STACK_ZIP_SHA256") or "").strip().lower()
    parts = urlsplit(zip_url)
    # "@" anywhere in the authority is userinfo, even empty (https://@host/)
    if parts.scheme != "https" or not parts.hostname or "@" in parts.netloc:
        return Stack("", "", "")
    deploy = f"{DEPLOY_BASE}?zipUrl={quote(zip_url, safe='')}"
    return Stack(zip_url, sha if _SHA256.match(sha) else "", deploy)


REVOKE_STEPS: tuple[tuple[str, str], ...] = (
    (
        "Destroy the stack",
        "In the OCI console open Developer Services > Resource Manager > Stacks, open the Zebra "
        "stack, run Destroy and wait for the job to succeed. Every resource it made is removed. "
        "Then delete the stack itself.",
    ),
    (
        "Delete the compartment",
        "Identity & Security > Compartments: delete the compartment the stack made "
        "(zebra-<name>). It can only be deleted once it is empty.",
    ),
    (
        "Delete the dynamic group and its policy",
        "If you or your admin created zebra-<name>-instances and its policy for the runtime "
        "grants, delete both under Identity & Security.",
    ),
    (
        "Delete the group and its policy (fallback only)",
        "If you used the policy text instead of the stack, delete the zebra-<name>-admins group, "
        "its policy, and any tenancy-level statements you added for budgets and quota.",
    ),
    (
        "Remove any API key",
        "This wizard never asks for an API key. If you made one for Zebra anyway, delete it "
        "under your user's API keys in the OCI console.",
    ),
    (
        "End this session",
        "Use Forget me on the wizard page (or just let it expire): this server then keeps "
        "nothing that links to you.",
    ),
)


def revoke_steps(name: object) -> list[tuple[str, str]]:
    """The revoke screen, with ``<name>`` filled in when known."""
    n = clean_name(name)
    return [(title, body.replace(NAME_PLACEHOLDER, n)) for title, body in REVOKE_STEPS]
