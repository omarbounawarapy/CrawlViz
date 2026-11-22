# PR checklist (lead, before asking Omar to push a branch and open a PR)

- [ ] Every commit title passes `python3 .claude/hooks/commit_msg_check.py --range <base>..HEAD`
- [ ] Every commit is one logical change; moves and formatting are separate; each is about
      200 hand-written lines or fewer, or the brief says why not
- [ ] `make check` passes on the integrated branch; `pytest -m pins` unchanged or signed off
- [ ] Required reviewers signed off; blocking findings resolved
- [ ] Docs updated in the same PR when behaviour changed
- [ ] Public-readiness: every added file is meant for readers outside the project (internal working
      files stay under `.claude/` or untracked), and the scan below finds nothing in the added lines
      or the PR text. A hit is rewritten in plain words (a code is explained, not just dropped) and
      fixed in a new commit once the branch is pushed:
      `git diff origin/main...HEAD -U0 | grep -E '^\+' | grep -vE '^\+\+\+' | grep -nEi "omar|ux-researcher|research-scientist|architect|lead agent|backend-engineer|frontend-engineer|Phase [A-H]\b|\b[A-Z][A-Z0-9]{1,5}-[0-9]+\b|AGENTS\.md|CLAUDE\.md|proposed, not approved|questions for"`
      and every path the added text links to exists in the diff or on `main`
- [ ] `.left-undone.json` updated
- [ ] PR text: one or two sentences, plus `Closes #N` when there is an issue; checked with no-ai-slop
- [ ] The branch is up to date with `origin/main` (the protection rule requires it)
- [ ] Omar approved pushing this branch and opening the PR
- [ ] CI `backend` and `frontend` are green on the PR before it is merged; a red run is read and
      fixed on the branch, never bypassed
- [ ] If the PR changes `uv.lock`, `pyproject.toml` or `crawler-ui/package*.json`, the
      Dependency audit workflow is green on it, or each advisory is triaged in the PR text
      (the audit is not a required check)
