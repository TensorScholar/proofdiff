# Migration from AXIOM

The existing AXIOM repository is preserved as history, but its public product direction changes.

- Move Codex-autopilot orchestration documents under `legacy/codex-pack/`.
- Replace `app/` and FastAPI-first packaging with `src/proofdiff/` and a CLI-first core.
- Preserve useful trace-import and regression-promotion ideas as future adapters.
- Remove SQLAlchemy and FastAPI from the required dependency surface.
- Apply this source tree on a branch created from the existing default branch so Git history is
  retained.

The local release bundle created in the build environment has an independent Git history because
the environment could not clone GitHub. Do not force-push that history over the existing repo;
copy or merge the source tree into a branch based on the existing repository.
