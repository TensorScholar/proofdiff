# Migrate AXIOM to ProofDiff without losing history

Target repository: `TensorScholar/axiom-ai-evaluation-platform`.

The final migration must start from the current public `main` history. The independent ProofDiff
bundle is review evidence, not a replacement ancestry and must never be force-pushed.

```bash
git clone git@github.com:TensorScholar/axiom-ai-evaluation-platform.git
cd axiom-ai-evaluation-platform
git rev-parse origin/main
git switch -c rebuild/proofdiff-core origin/main
```

The Codex handoff records the expected baseline commit. Stop if the remote baseline changed; inspect
new commits before proceeding.

Move materially useful AXIOM/autopilot content under `legacy/axiom-v0/`, then apply the candidate
source as focused commits. Do not preserve caches, generated reports, virtual environments, secrets,
or obsolete duplicate implementations.

Required local outcome:

- clean working tree;
- focused migration commits on `rebuild/proofdiff-core`;
- full quality/security/package gates captured as raw logs;
- no push, merge, tag, release, repository rename, or PyPI publication.

Only after independent review should the branch be pushed and opened as a pull request. Rename the
repository to `proofdiff` after green CI and human approval; GitHub normally preserves redirects,
but links and package metadata must still be checked explicitly.
