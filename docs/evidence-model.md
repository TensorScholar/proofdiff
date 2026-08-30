# Evidence model

A ProofDiff result is a scoped release assertion, not a universal safety claim.

```text
normalized manifests
  → semantic change set
  → selected contract definitions and selection reasons
  → baseline/candidate trace digests and replay results
  → paired classifications
  → effective policy
  → PASS / REVIEW / BLOCK
  → claims, provenance, report, and checksums
```

## Consistency requirements

Before generation, ProofDiff treats manifests, traces, contracts, policy, and the final report as
the authoritative inputs. It independently recomputes and compares every derived layer:

- semantic changeset from the protected manifests;
- impacted selection from the changeset and contract definitions;
- baseline and candidate results from selected contracts and traces;
- paired comparisons from those results;
- effective policy defaults and the final decision.

Generation fails if any supplied derived value disagrees with the recomputation. Manifests must also
be normalized and contain no unprotected secret-like configuration values. This prevents the Python
API from packaging a forged PASS decision or a selection/result set inconsistent with its inputs.

## Closed-set bundle

The set of evidence files is fixed for the schema version. `checksums.txt` covers every other file
and cannot cover itself. Verification rejects missing, unexpected, duplicate, nested, symlinked, or
modified entries.

`trace-digests.json` records canonical digests, not raw trace bodies. This limits evidence exposure
while preserving identity linkage. Selected contract definitions and the effective policy are
included so a reviewer can inspect what was actually evaluated.

## Authenticity boundary

SHA-256 checksums detect mutation relative to the supplied checksum file. They do not identify the
producer. GitHub artifact attestations, Sigstore, or another protected signing process should bind
release evidence to a publisher identity.
