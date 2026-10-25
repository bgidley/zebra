"""Leak guard for LLM-written workflows (#237).

An LLM that writes a workflow sees untrusted run content: the goal, earlier runs'
goals and outputs, continuation comments. It must not hard-code those specifics
(customer names, people, emails, numbers, pasted text) into a reusable workflow.

Rather than guess what is confidential, the guard uses what we know: exactly which
texts the writer was shown (its *exposure set*). It checks the string literals the
writer *added* compared with the parent workflow against that set. Words Zebra
itself supplied (the writer's system prompt and action list) are allowed.

Two kinds of exposure:

- ``run_texts``: other runs' content (sample goals, comments, previous-run context).
  Phrases of ``RUN_PHRASE_TOKENS`` normalised tokens count.
- ``goal_texts``: the goal the workflow is being written for. A workflow naturally
  describes its purpose, so only long verbatim copies (``GOAL_PHRASE_TOKENS``)
  count as phrases.

Names, emails, domains and numbers count from both. ``apply_guard()`` regenerates
once with ``generalise_prompt(hits)``. If hits remain, the dream-cycle optimizer
rejects the change (nobody asked for it), while the creator keeps the rewrite and
records the hits: a user's goal must not fail over its own words, and the data is
already in that user's runs.
"""

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)

RUN_PHRASE_TOKENS = 4
GOAL_PHRASE_TOKENS = 8
MIN_NUMBER_DIGITS = 3
MAX_REPORTED_HITS = 12

# Where a specific came from (LeakHit.source)
RUN = "run"
GOAL = "goal"

_TEMPLATE_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)
_TOKEN_RE = re.compile(r"[^\W_]+")
_WORD_RE = re.compile(r"[^\W\d_][\w'’&-]*")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+(?:[,.]\d+)*")
# Where a sentence or list item starts: capitalised words there are not names.
_SENTENCE_START_RE = re.compile(r"(?:^|[.!?:;]|\n)\s*(?:(?:[-*•>]|\d+[.)])\s+)?")

# Common words, often capitalised at the start of a sentence or in titles.
STOPWORDS = frozenset(
    """
    a about above after again against all also am an and any are as at be because been
    before being below between both but by can could did do does doing done down during each
    either even ever every few for from further get got had has have having he her here hers
    herself him himself his how however i if in into is it its itself just let like make many
    may me might more most much must my myself new next no nor not now of off on once one only
    or other our ours ourselves out over own per please same she should since so some such than
    that the their theirs them themselves then there these they this those though through to
    too under until up upon us use used using very via was we were what when where whether
    which while who whom whose why will with within without would yes yet you your yours
    yourself yourselves
    """.split()
)


@dataclass(frozen=True)
class LeakHit:
    """One specific from the exposure set found in text the writer added.

    Attributes:
        kind: ``phrase``, ``name``, ``email``, ``domain`` or ``number``
        text: The specific, as found
        where: Path of the YAML literal that contains it (e.g. ``tasks.check.properties.prompt``)
        source: ``run`` (other runs' content) or ``goal`` (the writer's own goal)
    """

    kind: str
    text: str
    where: str
    source: str = RUN

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "text": self.text, "where": self.where, "source": self.source}


@dataclass
class _Specifics:
    emails: set[str]
    domains: set[str]
    numbers: set[str]
    names: set[str]


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _numbers(text: str) -> set[str]:
    """Digit runs of at least ``MIN_NUMBER_DIGITS`` digits, separators removed."""
    found = set()
    for match in _NUMBER_RE.findall(text):
        value = re.sub(r"\D", "", match)
        if len(value) >= MIN_NUMBER_DIGITS:
            found.add(value)
    return found


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def _domains(text: str) -> set[str]:
    hosts = {_host(url) for url in _URL_RE.findall(text)}
    hosts |= {email.rsplit("@", 1)[1].lower() for email in _EMAIL_RE.findall(text)}
    return {h for h in hosts if "." in h}


def _names(text: str) -> set[str]:
    """Capitalised words that are not at the start of a sentence or list item.

    All-caps words (SLA, API, KPI, EU) are skipped: they are mostly jargon, and a
    workflow fixing an "SLA" failure must be able to say "SLA". The trade-off is that
    an all-caps company name is not caught.
    """
    starts = {m.end() for m in _SENTENCE_START_RE.finditer(text)}
    names = set()
    for match in _WORD_RE.finditer(text):
        word = match.group().strip("'’&-")
        if len(word) < 2 or not word[0].isupper() or match.start() in starts:
            continue
        word = re.split(r"['’]", word)[0]  # "Acme's" → "Acme"
        if len(word) >= 2 and not word.isupper() and word.lower() not in STOPWORDS:
            names.add(word)
    return names


def _literals(yaml_text: str) -> list[tuple[str, str]]:
    """Every string key and string value of a YAML document, with its path."""
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return [("", yaml_text)]
    found: list[tuple[str, str]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{path}.{key}" if path else str(key)
                if isinstance(key, str):
                    found.append((child, key))
                walk(value, child)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
        elif isinstance(node, str):
            found.append((path, node))

    walk(data, "")
    return found


class LeakGuard:
    """Checks a generated workflow for specifics copied from the writer's exposure set.

    Args:
        run_texts: Untrusted run content the writer saw (full check, 4-token phrases)
        goal_texts: The goal the workflow is written for (specifics, 8-token phrases)
        parent_yaml: The workflow being modified, if any; its text is never a leak
        allow_text: Text Zebra supplied (system prompt, action list); never a leak
    """

    def __init__(
        self,
        run_texts: list[str] | tuple[str, ...] = (),
        goal_texts: list[str] | tuple[str, ...] = (),
        parent_yaml: str | None = None,
        allow_text: str = "",
    ) -> None:
        run_texts = [t for t in run_texts if isinstance(t, str) and t.strip()]
        goal_texts = [t for t in goal_texts if isinstance(t, str) and t.strip()]

        self._parent_literals = (
            {text for _, text in _literals(parent_yaml)} if parent_yaml else set()
        )
        self._known = f"{parent_yaml or ''}\n{allow_text}"
        known_tokens = _tokens(self._known)
        self._known_words = set(known_tokens)
        self._known_ngrams = _ngrams(known_tokens, RUN_PHRASE_TOKENS) | _ngrams(
            known_tokens, GOAL_PHRASE_TOKENS
        )

        # Run phrases come first so a span matching both is a run phrase.
        self._phrases: list[tuple[int, str, set[tuple[str, ...]]]] = [
            (n, source, {g for t in texts for g in _ngrams(_tokens(t), n)})
            for n, source, texts in (
                (RUN_PHRASE_TOKENS, RUN, run_texts),
                (GOAL_PHRASE_TOKENS, GOAL, goal_texts),
            )
        ]
        run = self._specifics("\n".join(run_texts))
        goal = self._specifics("\n".join(goal_texts))
        # A specific in both is a run specific (the stricter source).
        self._by_source = {
            RUN: run,
            GOAL: _Specifics(
                goal.emails - run.emails,
                goal.domains - run.domains,
                goal.numbers - run.numbers,
                goal.names - run.names,
            ),
        }

    def _specifics(self, text: str) -> _Specifics:
        known_lower = self._known.lower()
        return _Specifics(
            emails={e.lower() for e in _EMAIL_RE.findall(text)}
            - {e.lower() for e in _EMAIL_RE.findall(self._known)},
            domains={d for d in _domains(text) if d not in known_lower},
            numbers=_numbers(text) - _numbers(self._known),
            names={
                n
                for n in _names(text)
                if n.lower() not in self._known_words and not any(c.isdigit() for c in n)
            },
        )

    def check(self, yaml_text: str) -> list[LeakHit]:
        """Return the specifics in literals added versus the parent (deduplicated, capped)."""
        hits: list[LeakHit] = []
        seen: set[tuple[str, str]] = set()

        def add(kind: str, text: str, where: str, source: str) -> None:
            if (kind, text.lower()) not in seen:
                seen.add((kind, text.lower()))
                hits.append(LeakHit(kind, text, where, source))

        for where, literal in _literals(yaml_text):
            if literal in self._parent_literals:
                continue
            text = _TEMPLATE_RE.sub(" ", literal)
            lower = text.lower()
            tokens = _tokens(text)
            words = set(tokens)
            numbers = _numbers(text)

            for source, spec in self._by_source.items():
                for email in sorted(spec.emails):
                    if email in lower:
                        add("email", email, where, source)
                for domain in sorted(spec.domains):
                    if domain in lower:
                        add("domain", domain, where, source)
                for number in sorted(numbers & spec.numbers):
                    add("number", number, where, source)
                for name in sorted(spec.names):
                    if name.lower() in words:
                        add("name", name, where, source)
            for phrase, source in self._phrase_hits(tokens):
                add("phrase", phrase, where, source)

        # Run hits first: they matter most in the report.
        hits.sort(key=lambda h: h.source != RUN)
        return hits[:MAX_REPORTED_HITS]

    def _phrase_hits(self, tokens: list[str]) -> list[tuple[str, str]]:
        """Merge overlapping exposure n-grams in ``tokens`` into (phrase, source) spans."""
        covered: list[str | None] = [None] * len(tokens)
        for n, source, phrases in self._phrases:
            if not phrases:
                continue
            for i in range(len(tokens) - n + 1):
                gram = tuple(tokens[i : i + n])
                if gram not in phrases or gram in self._known_ngrams:
                    continue
                if not any(t not in STOPWORDS and t not in self._known_words for t in gram):
                    continue
                for j in range(i, i + n):
                    covered[j] = covered[j] or source
        spans: list[tuple[str, str]] = []
        start = None
        for i, source in enumerate([*covered, None]):
            if source and start is None:
                start = i
            elif not source and start is not None:
                span_source = RUN if RUN in covered[start:i] else GOAL
                spans.append((" ".join(tokens[start:i]), span_source))
                start = None
        return spans


async def apply_guard(
    guard: "LeakGuard | None",
    yaml_content: str,
    regenerate: Callable[[str], Awaitable[tuple[str | None, str | None]]],
    *,
    reject: bool,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Check a generated workflow, regenerate once on hits, then keep or reject.

    Args:
        guard: The writer's guard; None skips the check
        yaml_content: The valid workflow the writer generated
        regenerate: Called once with ``generalise_prompt(hits)``; returns
            ``(yaml, None)`` for a valid rewrite or ``(None, problem)``. If it
            raises, the rewrite counts as unusable (#244)
        reject: Reject the change when hits remain (dream cycle) instead of
            keeping the rewrite and recording them (a user's goal)

    Returns:
        ``(yaml, problem, record)``: ``problem`` set means do not save. ``record``
        is the ``leak_record()`` (None when there was no hit).
    """
    if guard is None:
        return yaml_content, None, None
    try:
        hits = guard.check(yaml_content)
    except Exception as e:  # the guard must never let an unchecked change through silently
        return _guard_error(yaml_content, e, reject)
    if not hits:
        return yaml_content, None, None
    logger.warning("Leak guard: %d hit(s), regenerating: %s", len(hits), describe_hits(hits))
    try:
        rewrite, problem = await regenerate(generalise_prompt(hits))
    except Exception as e:  # e.g. an LLM error: the guard-only call must not lose a valid workflow
        rewrite, problem = None, f"rewrite failed: {e}"
    if problem or not rewrite:
        # An unusable rewrite: the first version stands or falls on its own hits.
        logger.warning("Leak guard: rewrite unusable: %s", problem)
        rewrite, remaining = yaml_content, hits
    else:
        try:
            remaining = guard.check(rewrite)
        except Exception as e:
            return _guard_error(rewrite, e, reject)
    if not remaining:
        return rewrite, None, leak_record("generalised", hits)
    if reject:
        logger.warning("Leak guard rejected the change: %s", describe_hits(remaining))
        return None, rejection_reason(remaining), leak_record("rejected", remaining)
    logger.warning("Leak guard kept the rewrite with hits: %s", describe_hits(remaining))
    return rewrite, None, leak_record("kept", remaining)


def _guard_error(
    yaml_content: str, error: Exception, reject: bool
) -> tuple[str | None, str | None, dict[str, Any]]:
    """A guard that crashed: reject (fail closed) or keep the workflow and record why."""
    logger.exception("Leak guard check failed")
    record = {"status": "error", "hits": [], "error": str(error)[:500]}
    if reject:
        record["status"] = "rejected"
        return None, f"Leak guard: check failed, change not saved: {error}", record
    return yaml_content, None, record


def describe_hits(hits: list[LeakHit]) -> str:
    """One line naming the hits, e.g. ``"Acme" (name), "jane@acme.com" (email)``."""
    return ", ".join(f'"{h.text}" ({h.kind})' for h in hits)


def generalise_prompt(hits: list[LeakHit]) -> str:
    """The instruction for the one regeneration after a leak-guard hit."""
    lines = "\n".join(f'- "{h.text}" ({h.kind}, in {h.where or "the YAML"})' for h in hits)
    return (
        "That workflow copies specifics from past runs or the goal into the YAML:\n"
        f"{lines}\n"
        "Generalise it: replace these with {{goal}}, an earlier task's output or a task "
        "input, so the workflow works for any similar goal. Never write names, companies, "
        "emails, numbers or text from runs into the YAML. Return the corrected workflow as "
        "YAML only."
    )


def rejection_reason(hits: list[LeakHit]) -> str:
    """Reason recorded when a writer still copies run specifics after regenerating."""
    return (
        f"Leak guard: workflow still copies run specifics after regenerating: {describe_hits(hits)}"
    )


def leak_record(status: str, hits: list[LeakHit]) -> dict[str, Any]:
    """The ``leak_guard`` record on a writer's output.

    ``status`` is ``generalised`` (the rewrite passed), ``kept`` (hits remained and the
    writer kept the rewrite) or ``rejected`` (nothing saved).
    """
    return {"status": status, "hits": [h.to_dict() for h in hits]}


def run_texts_from_metrics(metrics_analysis: dict[str, Any] | None) -> list[str]:
    """The run texts the evaluator puts in its prompt (sample goals, errors, comments)."""
    if not isinstance(metrics_analysis, dict):
        return []
    texts: list[str] = []
    for pattern in metrics_analysis.get("failure_patterns") or []:
        texts.extend(str(e) for e in (pattern.get("error_types") or {}))
        texts.extend(str(g) for g in pattern.get("sample_goals") or [])
    ca = metrics_analysis.get("continuation_analysis") or {}
    for fc in ca.get("frequently_continued") or []:
        texts.extend(str(c) for c in fc.get("comments") or [])
    for gap in ca.get("capability_gaps") or []:
        texts.extend(str(gap[k]) for k in ("comment", "rationale") if gap.get(k))
    return [t for t in texts if t.strip()]
