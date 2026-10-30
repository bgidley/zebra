"""Zebra Commons: identity, signed events and (later) workflow sharing over Nostr.

S1 (#228) provides the Zebra key, certified device keys, local ``DEVICE_CERT`` /
``DEVICE_REVOKE`` events and the cert-chain verify helper. Nothing here touches the
network or Django. See ``specs/zebra-commons-design.md``.
"""
