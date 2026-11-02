"""Zebra Commons task actions (#41): checks a workflow must pass before it is shared.

S2b (#229) provides ``commons_pii_scan``. See ``specs/zebra-commons-design.md``.
"""

from zebra_tasks.commons.pii_scan import CommonsPiiScanAction

__all__ = ["CommonsPiiScanAction"]
