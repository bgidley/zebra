## Context

`zebra_source` (#190) gives `llm_agent` read and search access to Zebra's deployed source. On prod
all 18 failed reads (of 171) were for allowlisted paths that the image never shipped. Agents had
no way to find out what exists, and the error gave no hint.

## Decisions

- **List is a third operation of the same action**, not a new action: it shares the allowlist,
  root and symlink rules. One level by default (subdirectories `name/ (N files)`, files
  `name (size)`); a `glob` switches to a recursive file list, using search's `_glob_match`.
  `max_results` (default 200) caps either form.
- **Failures stay failures.** A bad path still returns `TaskResult.fail`. `llm_agent` already
  passes a failed tool's error to the model ("Error: the workflow failed: …"), so the message
  itself carries the recovery: suggestions and a hint. Metrics still count the failure.
- **Suggestions** come from the allowed file list (`_source_files`, so hidden entries can never be
  suggested). Order: files with the same name, then `difflib.get_close_matches` on the full path
  (cutoff 0.6), at most 5. With an undeployed top-level entry, the message names the present
  top-level entries in place of guessing.
- **Directory read** fails with the listing, which is what the agent needed.
- **Deploy the docs (#212)**: the runtime stage copies `specs/ docs/ openspec/ scripts/ deploy/`
  and root `*.md` (about 2.5 MB). The allowlist is unchanged; the image now matches it.
- Tool descriptions name the deployed top-level entries; *Outcome Review* offers the list tool and
  its prompt mentions it.

## Risks

- Building the suggestion list walks the whole tree (a few thousand files): fine for a failure
  path, done only on failure.
- `CLAUDE.md` is a symlink to `AGENTS.md`. `COPY` keeps it as a symlink inside `/app`; it
  resolves inside the root, so reads work. Listing skips symlinks, as it does today.
