"""Unit tests of skill sync's pieces (#236): client, SKILL events, merge, lineage order."""

import json
import os
import time

import pytest

from zebra_agent.commons import keys
from zebra_agent.commons.client import (
    SKILL_KIND,
    Filter,
    InMemoryCommonsClient,
    InMemoryRelay,
    PublishRefused,
)
from zebra_agent.commons.events import Event, sign_event
from zebra_agent.commons.identity import make_device_cert, make_device_revoke, parse_cert
from zebra_agent.commons.skill import (
    SkillRefused,
    build_skill_events,
    skill_recipients,
    verify_skill,
)
from zebra_agent.commons.sync import (
    FAST_FORWARD,
    FORK,
    NEW,
    NOOP,
    STALE,
    can_receive,
    can_send,
    merge_decision,
)
from zebra_agent.library import WorkflowLibrary, lineage_order
from zebra_agent.provenance import read_commons, with_commons

FLOW = """name: Flow
version: 1
description: A flow.
first_task: a
tasks:
  a:
    name: A
    action: llm_call
    properties:
      prompt: "Do {{goal}}"
"""


@pytest.fixture
def zebra():
    zebra_secret = keys.generate_secret_key()
    devices = {s: keys.generate_secret_key() for s in ("home", "work", "studio")}
    certs = [
        make_device_cert(
            zebra_secret,
            keys.public_key(secret),
            label=s,
            sphere=s,
            observed=s == "work",
        )
        for s, secret in devices.items()
    ]
    return zebra_secret, devices, certs


def _shared_file(tmp_path, share_with):
    library = WorkflowLibrary(tmp_path / "lib", sphere="home", owner_user_id=1)
    path = library.save(FLOW, writer="human")
    block = read_commons(path.read_text())
    block["share_with"] = share_with
    path.write_text(with_commons(path.read_text(), block))
    return path.read_text()


def _events(zebra, text, spheres):
    zebra_secret, devices, certs = zebra
    zebra_pubkey = keys.public_key(zebra_secret)
    recipients = skill_recipients(
        spheres,
        [parse_cert(c) for c in certs],
        certs,
        zebra_pubkey=zebra_pubkey,
        sender_pubkey=keys.public_key(devices["home"]),
    )
    return build_skill_events(
        text,
        device_secret=devices["home"],
        zebra_pubkey=zebra_pubkey,
        own_cert=certs[0],
        recipients=recipients,
    )


async def test_skill_refused_on_a_public_relay(zebra):
    _, devices, _ = zebra
    event = sign_event(devices["home"], SKILL_KIND, [], "{}")
    public = InMemoryRelay(private=False)
    with pytest.raises(PublishRefused):
        await InMemoryCommonsClient(public).publish(event)
    assert public.events == []
    private = InMemoryRelay(private=True)
    client = InMemoryCommonsClient(private)
    await client.publish(event)
    assert await client.fetch([Filter(kinds=(SKILL_KIND,))]) == [event]


async def test_subscribe_yields_stored_then_new(zebra):
    _, devices, _ = zebra
    relay = InMemoryRelay()
    client = InMemoryCommonsClient(relay)
    first = sign_event(devices["home"], 1, [["p", "aa"]], "1")
    await client.publish(first)
    stream = client.subscribe([Filter(recipients=("aa",))])
    assert await anext(stream) == first
    second = sign_event(devices["home"], 1, [["p", "aa"]], "2")
    await client.publish(sign_event(devices["home"], 1, [["p", "bb"]], "x"))
    await client.publish(second)
    assert await anext(stream) == second
    await stream.aclose()


def test_events_only_for_devices_of_shared_spheres(tmp_path, zebra):
    _, devices, _ = zebra
    events = _events(zebra, _shared_file(tmp_path, ["studio"]), ["studio"])
    assert [e.tag_values("p") for e in events] == [[keys.public_key(devices["studio"])]]


def test_build_refuses_a_recipient_outside_share_with(tmp_path, zebra):
    zebra_secret, devices, certs = zebra
    with pytest.raises(SkillRefused):
        build_skill_events(
            _shared_file(tmp_path, ["studio"]),
            device_secret=devices["home"],
            zebra_pubkey=keys.public_key(zebra_secret),
            own_cert=certs[0],
            recipients=[parse_cert(certs[1])],
        )


def _verify(zebra, event, sphere="studio", held=None):
    zebra_secret, devices, certs = zebra
    return verify_skill(
        event,
        device_pubkey=keys.public_key(devices[sphere]),
        zebra_pubkey=keys.public_key(zebra_secret),
        sphere=sphere,
        held_events=certs if held is None else held,
    )


def test_verify_accepts_and_reads_sender_sphere_from_cert(tmp_path, zebra):
    [event] = _events(zebra, _shared_file(tmp_path, ["studio"]), ["studio"])
    result = _verify(zebra, event)
    assert result.ok, result.reason
    assert result.sender_sphere == "home"


def _resigned(zebra, event, mutate):
    _, devices, _ = zebra
    content = json.loads(event.content)
    tags = mutate(content, [list(t) for t in event.tags])
    return sign_event(devices["home"], event.kind, tags, json.dumps(content))


def test_verify_rejections(tmp_path, zebra):
    zebra_secret, devices, certs = zebra
    [event] = _events(zebra, _shared_file(tmp_path, ["studio"]), ["studio"])

    assert _verify(zebra, event, sphere="work").reason == "not_addressed"

    tampered = Event.from_dict({**event.to_dict(), "content": event.content.replace("Do", "Rm")})
    assert _verify(zebra, tampered).reason == "bad_signature"

    def edit_yaml(content, tags):
        content["yaml"] = content["yaml"].replace("Do", "Rm")
        return tags

    assert _verify(zebra, _resigned(zebra, event, edit_yaml)).reason == "hash_mismatch"

    def foreign(content, tags):
        content["commons"]["foreign_users"] = True
        return tags

    assert _verify(zebra, _resigned(zebra, event, foreign)).reason == "foreign_users"

    def other_sphere(content, tags):
        content["commons"]["share_with"] = ["work"]
        return tags

    assert _verify(zebra, _resigned(zebra, event, other_sphere)).reason == (
        "not_shared_with_sphere"
    )

    revoke = make_device_revoke(zebra_secret, keys.public_key(devices["home"]))
    assert _verify(zebra, event, held=[*certs, revoke]).reason == "revoked"

    other_zebra = keys.generate_secret_key()
    stranger = verify_skill(
        event,
        device_pubkey=keys.public_key(devices["studio"]),
        zebra_pubkey=keys.public_key(other_zebra),
        sphere="studio",
        held_events=certs,
    )
    assert stranger.reason == "wrong_zebra"


def test_sync_directions():
    assert [can_send(d) for d in ("send", "receive", "both", "off", None)] == [
        True,
        False,
        True,
        False,
        False,
    ]
    assert [can_receive(d) for d in ("send", "receive", "both", "off", "x")] == [
        False,
        True,
        True,
        False,
        False,
    ]


def test_merge_decision():
    a = {"content_sha256": "a", "ancestors": []}
    b = {"content_sha256": "b", "ancestors": ["a"]}
    c = {"content_sha256": "c", "ancestors": ["a"]}
    assert merge_decision(None, a) == NEW
    assert merge_decision(a, dict(a)) == NOOP
    assert merge_decision(a, b) == FAST_FORWARD
    assert merge_decision(b, a) == STALE
    assert merge_decision(b, c) == FORK


def test_lineage_order_prefers_descendant_and_non_fork(tmp_path):
    library = WorkflowLibrary(tmp_path / "lib", sphere="home", owner_user_id=1)
    old = library.save(FLOW, writer="human")
    new = library.save(FLOW.replace("A flow.", "A better flow."), writer="human")
    os.utime(new, (time.time() - 500, time.time() - 500))  # the descendant is older on disk
    assert lineage_order([old, new]) == [new, old]
    assert "better" in library.get_workflow_yaml("Flow")

    block = read_commons(new.read_text())
    block["fork_of"] = "zzz"
    block["ancestors"] = []
    block["parent_sha256"] = None
    new.write_text(with_commons(new.read_text(), block))
    os.utime(new, None)
    assert lineage_order([new, old]) == [old, new]  # a fork never displaces the other


def test_approve_share_only_for_the_approved_version(tmp_path):
    library = WorkflowLibrary(tmp_path / "lib", sphere="home", owner_user_id=1)
    path = library.save(FLOW, writer="human")
    first = read_commons(path.read_text())["content_sha256"]
    mtime = path.stat().st_mtime_ns
    assert library.approve_share("Flow", "work", first)
    assert library.commons_block("Flow")["share_with"] == ["work"]
    assert path.stat().st_mtime_ns == mtime

    library.save(FLOW.replace("A flow.", "Changed."), writer="human")
    assert library.commons_block("Flow")["share_with"] == []  # a change resets it
    assert not library.approve_share("Flow", "work", first)
