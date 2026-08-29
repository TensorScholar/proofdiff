# Publishing

Do not publish or tag from a reconstruction or Codex handoff bundle.

1. Apply the candidate to a branch rooted in the existing public repository history.
2. Require CI, CodeQL, schemas, examples, coverage, standard build/twine, dependency audit, and
   isolated wheel smoke installation.
3. Review package name availability and configure a protected PyPI Trusted Publisher only after
   merge approval.
4. Publish a release candidate only from a reviewed tag and protected workflow.
5. Complete a real pilot before stable `v0.1.0`.

Release artifacts should include wheel, sdist, source archive, `SHA256SUMS`, SBOM, benchmark result,
validation report, and build provenance. Checksums provide integrity; protected attestations bind
artifacts to the release workflow.
