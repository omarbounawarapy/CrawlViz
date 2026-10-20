# PR checklist (lead, before asking Omar to push a branch and open a PR)

- [ ] Every commit title passes `python3 .claude/hooks/commit_msg_check.py --range <base>..HEAD`
- [ ] Every commit is one logical change; moves and formatting are separate; each is about
      200 hand-written lines or fewer, or the brief says why not
- [ ] `make check` passes on the integrated branch; `pytest -m pins` unchanged or signed off
- [ ] Required reviewers signed off; blocking findings resolved
- [ ] Docs updated in the same PR when behaviour changed
- [ ] `.left-undone.json` updated
- [ ] PR text: one or two sentences, plus `Closes #N` when there is an issue; checked with no-ai-slop
- [ ] The branch is up to date with `origin/main` (the protection rule requires it)
- [ ] Omar approved pushing this branch and opening the PR
- [ ] CI `backend` and `frontend` are green on the PR before it is merged; a red run is read and
      fixed on the branch, never bypassed
