"""Zebra's side of the host builder's spool directory (#98, #172).

The host builder (``scripts/zebra_builder.py``) runs Claude Code builds in a sandbox outside
Zebra's containers. Zebra and the builder talk only through files in a shared directory, one
subdirectory per job; this module is the Zebra end. Every write is a temp file + rename, so the
builder never reads a half-written request.

See ``specs/claude-code-builder-design.md`` for the layout.
"""

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SPOOL_ENV = "ZEBRA_BUILDER_SPOOL"
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_MAX_FILE_BYTES = 1_000_000


class BuilderSpool:
    """Read and write build jobs in the builder's spool directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @classmethod
    def from_env(cls) -> "BuilderSpool | None":
        """The spool named by ``ZEBRA_BUILDER_SPOOL``, or None when it is unset or missing."""
        root = os.environ.get(SPOOL_ENV)
        if not root or not Path(root).is_dir():
            return None
        return cls(Path(root))

    # ---- requests (Zebra -> builder)

    def submit_build(
        self,
        *,
        repo: str,
        base_branch: str,
        title: str,
        prompt: str,
        test_command: str,
        max_turns: int,
        minutes: int,
        process_id: str,
        stage: str = "patch",
        branch: str | None = None,
        issue: int | None = None,
        approval: dict[str, str] | None = None,
    ) -> str:
        """Write a build job and return its id. The builder validates it.

        A delivery *stage* other than ``patch`` (#251) also names the feature *branch*, the
        *issue*, and for ``merge`` the human *approval* ``{ship_job_id, head_sha}``.
        """
        job_id = uuid.uuid4().hex
        job_dir = self.root / job_id
        job_dir.mkdir()
        job: dict[str, Any] = {
            "kind": "build",
            "repo": repo,
            "base_branch": base_branch,
            "title": title,
            "prompt": prompt,
            "test_command": test_command,
            "budget": {"max_turns": max_turns, "minutes": minutes},
            "process_id": process_id,
        }
        if stage != "patch":
            job.update(stage=stage, branch=branch, issue=issue)
            if approval is not None:
                job["approval"] = approval
        self._write(job_dir / "job.json", job)
        return job_id

    def request_publish(
        self, job_id: str, *, patch_sha256: str, mr_title: str, mr_description: str
    ) -> None:
        """Ask the builder to publish the approved patch (identified by its hash) as a draft MR."""
        self._write(
            self._job_dir(job_id) / "publish.json",
            {
                "patch_sha256": patch_sha256,
                "mr_title": mr_title,
                "mr_description": mr_description,
            },
        )

    def cancel(self, job_id: str) -> None:
        """Ask the builder to stop a job (its goal ended)."""
        (self._job_dir(job_id) / "cancel").touch()

    # ---- responses (builder -> Zebra)

    def result(self, job_id: str) -> dict[str, Any] | None:
        return self._read(self._job_dir(job_id) / "result.json")

    def published(self, job_id: str) -> dict[str, Any] | None:
        return self._read(self._job_dir(job_id) / "published.json")

    def live_jobs(self) -> list[tuple[str, str | None]]:
        """``(job_id, process_id)`` for every job the builder may still be working on.

        A job is live until it has a result (or a publish answer, once publish was asked for)
        or has been cancelled.
        """
        jobs = []
        if not self.root.is_dir():
            return jobs
        for job_dir in self.root.iterdir():
            if not _JOB_ID_RE.match(job_dir.name) or not job_dir.is_dir():
                continue
            if (job_dir / "cancel").exists():
                continue
            waiting_on = "published.json" if (job_dir / "publish.json").exists() else "result.json"
            if (job_dir / waiting_on).exists():
                continue
            job = self._read(job_dir / "job.json") or {}
            jobs.append((job_dir.name, job.get("process_id")))
        return jobs

    # ---- helpers

    def _job_dir(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not _JOB_ID_RE.match(job_id):
            raise ValueError(f"not a build job id: {job_id!r}")
        return self.root / job_id

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            if path.is_symlink() or path.stat().st_size > _MAX_FILE_BYTES:
                return None
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None


def get_spool(extras: dict) -> BuilderSpool | None:
    """The injected spool (``__builder_spool__``), else the one named by the environment."""
    spool = extras.get("__builder_spool__")
    return spool if spool is not None else BuilderSpool.from_env()
