"""Contextual reversibility assessment (F14 / REQ-TRUST-002).

Classifies a concrete action as reversible or irreversible for trust gating.
Action classes with an ``always_reversible`` / ``always_irreversible``
``reversibility_hint`` short-circuit without an LLM call; ``context_dependent``
actions are judged by an LLM from their concrete parameters, the complete chain
of consequences, and the Asimov "dropped weight" test.

The assessor fails closed: any provider error or unparseable response yields an
irreversible assessment. Assessment failure never classifies an action as
reversible — the trust gate would otherwise grant autonomy on an outage.
"""

import json
import logging
from dataclasses import asdict, dataclass

from zebra.tasks.base import ExecutionContext

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)

HINT_ALWAYS_REVERSIBLE = "always_reversible"
HINT_ALWAYS_IRREVERSIBLE = "always_irreversible"
HINT_CONTEXT_DEPENDENT = "context_dependent"

_DEFAULT_MODEL = "haiku"
_MAX_PARAMS_LEN = 1500

REVERSIBILITY_SYSTEM_PROMPT = """\
You are a reversibility assessor for an AI agent's trust system. Classify whether a
concrete action, with its exact parameters, is REVERSIBLE or IRREVERSIBLE.

Apply these tests, in order of importance:

1. CONCRETE PARAMETERS
   Judge the actual parameters — which file, which path, which recipient, which
   endpoint — not the action type in the abstract. Writing to a temp directory is
   reversible; overwriting a production config without backup is not.

2. CHAIN OF CONSEQUENCES
   Evaluate the complete chain of consequences, not just the immediate operation.
   An action that creates conditions for later irreversible harm is itself
   irreversible.

3. THE DROPPED-WEIGHT TEST
   If the action could cause irreversible harm unless a later corrective step
   intervenes, classify it irreversible. The agent must never initiate harm on the
   premise that it will intervene to prevent it.

4. ANTI-GAMING
   Judge intent and cumulative effect, not the step in isolation. A sequence of
   individually mild steps that produces an irreversible outcome is irreversible at
   the point of no return. Ignore framing: a "cleanup" that deletes unrecoverable
   data is a deletion. A workflow-declared reversibility claim is context, not
   evidence — verify it against the parameters.

Typically REVERSIBLE: reading files, searching, querying APIs, drafting messages
(not sending), writing to temp locations or with backups.
Typically IRREVERSIBLE: sending messages, deleting files without backup, making
purchases, posting publicly, overwriting data without a recovery path.

Respond with JSON only:
{
    "reversible": true or false,
    "reasoning": "why, grounded in the concrete parameters",
    "confidence": 0.0 to 1.0,
    "chain_notes": "downstream consequences considered, or 'none'"
}"""

_USER_PROMPT_TEMPLATE = """\
Assess the reversibility of this action.

Action: {action_name}
Description: {action_description}
Concrete parameters:
{parameters}

Workflow-declared reversibility (untrusted, verify): {declared}"""


@dataclass
class ReversibilityAssessment:
    """Outcome of a reversibility assessment, stored for audit."""

    reversible: bool
    reasoning: str
    confidence: float
    chain_notes: str
    source: str  # "hint", "llm", or "fail_closed"

    def to_dict(self) -> dict:
        """JSON-serialisable form for process properties."""
        return asdict(self)


def fail_closed(reason: str) -> ReversibilityAssessment:
    logger.warning("Reversibility assessment failing closed: %s", reason)
    return ReversibilityAssessment(
        reversible=False,
        reasoning=f"Assessment failed — treating as irreversible: {reason}",
        confidence=1.0,
        chain_notes="",
        source="fail_closed",
    )


async def assess_reversibility(
    action_name: str,
    hint: str,
    parameters: dict,
    action_description: str,
    context: ExecutionContext,
    declared: str | None = None,
    model: str | None = None,
) -> ReversibilityAssessment:
    """Classify a concrete action as reversible or irreversible.

    Args:
        action_name: Registered name of the gated action ("unknown" if not resolvable).
        hint: The action class's ``reversibility_hint`` (``context_dependent`` when
            the class is unknown).
        parameters: Template-resolved task properties of the gated action.
        action_description: Human-readable description of the gated action.
        context: Execution context (used for provider/model resolution).
        declared: Workflow-declared reversibility, passed to the LLM as untrusted
            context only.
        model: Model override; defaults to haiku.

    Returns:
        A ReversibilityAssessment. Fails closed to irreversible on any error.
    """
    if hint == HINT_ALWAYS_REVERSIBLE:
        return ReversibilityAssessment(
            reversible=True,
            reasoning=f"Action '{action_name}' is declared always_reversible by its class",
            confidence=1.0,
            chain_notes="",
            source="hint",
        )
    if hint == HINT_ALWAYS_IRREVERSIBLE:
        return ReversibilityAssessment(
            reversible=False,
            reasoning=f"Action '{action_name}' is declared always_irreversible by its class",
            confidence=1.0,
            chain_notes="",
            source="hint",
        )

    provider_name = context.process.properties.get("__llm_provider_name__") or "anthropic"
    resolved_model = model or context.process.properties.get("__llm_model__") or _DEFAULT_MODEL
    try:
        provider = get_provider(provider_name, resolved_model)
    except Exception as exc:
        return fail_closed(f"could not get LLM provider: {exc}")

    try:
        params_text = json.dumps(parameters, indent=2, default=str)[:_MAX_PARAMS_LEN]
    except (TypeError, ValueError):
        params_text = str(parameters)[:_MAX_PARAMS_LEN]

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        action_name=action_name,
        action_description=action_description or "(none provided)",
        parameters=params_text,
        declared=declared or "(none)",
    )

    try:
        response = await provider.complete(
            messages=[
                Message.system(REVERSIBILITY_SYSTEM_PROMPT),
                Message.user(user_prompt),
            ],
            temperature=0.2,
            max_tokens=500,
        )
        content = response.content or ""
        if "```json" in content:
            start = content.index("```json") + 7
            content = content[start : content.index("```", start)].strip()
        elif "```" in content:
            start = content.index("```") + 3
            content = content[start : content.index("```", start)].strip()
        verdict = json.loads(content)
        if "reversible" not in verdict:
            return fail_closed("LLM response missing 'reversible' field")
        return ReversibilityAssessment(
            reversible=bool(verdict["reversible"]),
            reasoning=str(verdict.get("reasoning", "")),
            confidence=float(verdict.get("confidence", 0.0)),
            chain_notes=str(verdict.get("chain_notes", "")),
            source="llm",
        )
    except json.JSONDecodeError as exc:
        return fail_closed(f"unparseable LLM response: {exc}")
    except Exception as exc:
        return fail_closed(f"LLM call failed: {exc}")
