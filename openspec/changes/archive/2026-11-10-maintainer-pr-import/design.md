## Decisions

- Two steps, not one: `push` is the only step that triggers CI and needs the reviewed sha, so the
  maintainer cannot skip reading the diff by accident, and a PR that moves after review is refused.
- Origin signature message: sha256("zebra-contribute-v1\n<repo>\n<head sha>"), signed with the Zebra
  key (`zebra_agent.commons.keys`). It names the proposing Zebra; it does not make code trusted.
- Scanner is an interface so slice A can replace the built-in scan; any scanner error rejects.
- The branch holds the contributor's commits as-is (no rewrite), so `merge --no-ff` keeps authorship
  and GitHub marks the PR merged once master is pushed to the mirror.
