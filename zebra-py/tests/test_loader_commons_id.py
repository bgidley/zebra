"""#229 S2b: a workflow stamped with a ``commons`` block gets a content-addressed id."""

import hashlib

from zebra.definitions.loader import load_definition_from_dict

BASE = {"name": "Web Research", "version": 1, "tasks": {"a": {"name": "A"}}}


def test_legacy_id_unchanged():
    definition = load_definition_from_dict(dict(BASE))
    assert definition.id == hashlib.sha256(b"Web Research:1").hexdigest()[:16]


def test_commons_id_from_hash_and_name():
    data = {**BASE, "commons": {"content_sha256": "ab" * 32}}
    expected = hashlib.sha256(("ab" * 32 + ":Web Research").encode()).hexdigest()[:16]
    assert load_definition_from_dict(data).id == f"c:{expected}"


def test_same_name_and_version_with_different_content_differ():
    one = load_definition_from_dict({**BASE, "commons": {"content_sha256": "1" * 64}})
    two = load_definition_from_dict({**BASE, "commons": {"content_sha256": "2" * 64}})
    assert one.id != two.id
    assert one.id.startswith("c:") and two.id.startswith("c:")


def test_display_name_is_part_of_the_id():
    block = {"content_sha256": "1" * 64}
    one = load_definition_from_dict({**BASE, "commons": block})
    two = load_definition_from_dict({**BASE, "name": "Web Research (from Z)", "commons": block})
    assert one.id != two.id


def test_block_without_hash_keeps_legacy_id():
    legacy = load_definition_from_dict(dict(BASE))
    for block in ({"content_sha256": None}, {}, "junk", {"content_sha256": ""}):
        assert load_definition_from_dict({**BASE, "commons": block}).id == legacy.id
