"""Zebra's voice: a short first-person line recorded next to a reasoning output.

Reasoning tasks (ethics gates, workflow selection, concern flagging,
continuation assessment, the post-run ethics review) ask the model for two extra
JSON fields alongside their structured result:

- ``voice``: one or two short sentences, first person, telling the user what
  Zebra concluded and why.
- ``confidence``: how sure Zebra is, 0.0 to 1.0.

The web UI's voice layer (#161) quotes these verbatim, so they are only ever
what the model actually said. They ride along in the same LLM call; no extra
call is made. Both are optional: older outputs and models that omit them
simply have no voice line.
"""

from typing import Any

# The prompt asks for one or two sentences; 400 characters is comfortably more
# than that, and caps a model that rambles so a voice line never swamps the UI.
VOICE_MAX_CHARS = 400

# Fragment for a JSON response schema. Callers append it inside their braces.
VOICE_SCHEMA_FIELDS = (
    '"voice": "one or two short sentences in the first person, addressed to the user, '
    'saying what you concluded and why (plain, no preamble)",\n'
    '"confidence": a number from 0.0 to 1.0 for how sure you are of this conclusion'
)


def extract_voice(data: Any) -> dict[str, Any]:
    """Normalise the voice fields from a parsed model response.

    Args:
        data: The parsed JSON response (anything; non-dicts yield no voice).

    Returns:
        ``{"voice": str | None, "confidence": float | None}``. Text is stripped
        and clipped to ``VOICE_MAX_CHARS``; confidence is clamped to 0.0..1.0 and
        ``None`` when missing or not a number.
    """
    if not isinstance(data, dict):
        return {"voice": None, "confidence": None}

    voice = data.get("voice")
    if isinstance(voice, str):
        voice = " ".join(voice.split())
        if len(voice) > VOICE_MAX_CHARS:
            voice = voice[: VOICE_MAX_CHARS - 1].rstrip() + "…"
        voice = voice or None
    else:
        voice = None

    confidence = data.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        try:
            confidence = float(confidence) if isinstance(confidence, str) else None
        except ValueError:
            confidence = None
    if confidence is not None:
        confidence = round(min(1.0, max(0.0, float(confidence))), 2)

    return {"voice": voice, "confidence": confidence}


def voice_fields(data: Any) -> dict[str, Any]:
    """Like :func:`extract_voice` but only the fields the model actually supplied.

    Use this when merging into a stored output, so outputs without a voice keep
    exactly the shape they had before #161.
    """
    return {key: value for key, value in extract_voice(data).items() if value is not None}
