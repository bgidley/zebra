"""Contributing code upstream from an onboarded Zebra (#282).

Slice A provides ``contribute_diff_scan``, the check a patch must pass before it may leave the
instance as a GitHub pull request. See ``openspec/specs/contribute-diff-scan/spec.md``.
"""

from zebra_tasks.contribute.diff_scan import ContributeDiffScanAction

__all__ = ["ContributeDiffScanAction"]
