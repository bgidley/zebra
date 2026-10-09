"""Carry the goal submitter between processes (#151).

The Agent Main Loop process holds who submitted the goal. Processes it
creates (the executed goal workflow, goals it queues) must carry the same
keys so user-scoped steps (knowledge, trust gate, values profile, run
ownership) still find the user.
"""

from __future__ import annotations

USER_PROPERTY_KEYS = ("__user_id__", "__user_display_name__", "__user_identity_id__")


def copy_user_properties(source: dict, target: dict) -> None:
    """Copy the submitter keys present in *source* into *target*."""
    for key in USER_PROPERTY_KEYS:
        if key in source:
            target[key] = source[key]
