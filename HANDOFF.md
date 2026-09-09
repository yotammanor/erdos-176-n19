# Handoff: Erdős Problem 176, the \(N(19,2)\) case

Snapshot date: 2026-09-10.

## Executive status

This project has **not yet proved** \(N(19,2)=344\).

What is established:

- An explicit coloring of \([343]\) avoids discrepancy \(2\) on every
  19-term arithmetic progression.
- Two independent exact evaluators check all 3097 progressions in that
  witness.
- Therefore the unconditional result is
  \[
  N(19,2)\ge 344.
  \]
- The \(N=344\) pseudo-Boolean, threshold-CNF, and compact sliding-CNF
  formulations have independent encoding audits.
- Two proof-producing adaptive SAT routes made substantial progress, but
  neither is a complete certificate.

What is still missing:

- A complete independently checked UNSAT certificate for one audited
  \(N=344\) instance.
- A passing final campaign gate and release manifest.

Do not state \(N(19,2)=344\) as a theorem from the current artifacts. The
defensible wording is:

> As of 2026-09-10, the project proves \(N(19,2)\ge344\), and has partial
> machine-checked evidence toward the conjectured matching upper bound, but
> the complete upper-bound certificate is still missing.

There are no solver or cuber jobs intentionally left running.

Unless a command says otherwise, run all commands below from:

```text
/Users/yotam.manor/code/devex-construct/research/erdos-176-n19
```

## Recommended pickup order

There are two independent adaptive routes.

1. Inspect the **threshold-CNF route first**. It has only one unresolved
   final-tree leaf and 24 of 25 leaf proofs with matching successful
   `drat-trim` records. Its last leaf is exceptionally hard, and the legacy
   campaign records need a small provenance migration before the modern
   assembler will accept them.
2. If the threshold leaf remains intractable, continue the **sliding-CNF
   route**. Its provenance is modern and its assembler already finds proof
   candidates for 6637 of 6901 leaves, leaving 264 unresolved leaves.
3. Whichever route finishes first must be assembled, rechecked from scratch,
   gated, and archived. Evidence from the two different CNFs cannot be mixed
   into one cube tree.

## Mathematical problem

For integers \(k\ge2\) and \(1\le\ell\le k\), define

\[
N(k,\ell)=\min\left\{N:\ \forall f:[N]\to\{-1,+1\},\
\exists\text{ a }k\text{-term AP }P,\
\left|\sum_{n\in P} f(n)\right|\ge\ell\right\}.
\]

For \(k=19\), every progression sum is odd. Avoiding discrepancy \(2\)
therefore means that every 19-term arithmetic progression has sum exactly
\(-1\) or \(+1\). In Boolean variables \(x_i=1\iff f(i)=+1\), every
progression must contain 9 or 10 positive entries.

There are 3116 19-term arithmetic progressions in \([344]\).
Fixing \(x_1=1\) preserves satisfiability because global color
complementation maps avoiders to avoiders.

See `MATHEMATICS.md` for the proof of the lower bound and the exact encoding
equivalences. See `LITERATURE.md` for the open-status and prior-art audit.

## Certified lower bound

Authoritative witness:

```text
witnesses/k19_N343.txt
```

Its SHA-256 is:

```text
936ce2049c62331d7907af1cf41fb65029ca9d8c48a5614f96eba4060ec1f867
```

Independent audit:

```text
proofs/adaptive/k19_N343.witness.audit.json
```

The audit reports:

- `n = 343`
- `k = 19`
- 3097 checked progressions
- 1428 progression sums equal to \(-1\)
- 1669 progression sums equal to \(+1\)
- `avoids = true`

Recheck it with:

```sh
python3 nk2.py verify witnesses/k19_N343.txt --k 19
python3 independent_verify.py witnesses/k19_N343.txt --k 19
```

The witness is the published length-343 witness from T. Alexander Lystad's
2026 Zenodo dataset. The lower bound and witness are prior work, not the new
claim sought here.

## Route A: threshold CNF

### Audited instance

```text
proofs/k19_N344_x1.cnf
```

Properties:

- 480208 variables
- 1832209 clauses
- SHA-256
  `e548cab0efb34dd87aaa26c26f51f6a510d3eb0cf59a843b3fda0a0f4c4232b1`

Independent audit:

```text
proofs/adaptive/k19_N344_x1.cnf.audit.json
```

It reports `PASS` for both the local counter-gadget truth tables and the
exact serialized clause stream.

### Best threshold tree

```text
proofs/adaptive/k19_N344_final25.tree.json
```

Properties:

- 25 leaves
- SHA-256
  `2d31b244e3e81f9981e688ceb24536fa8e354f0fee14fbc2922c4bff836cfa16`

The associated partial campaign is:

```text
proofs/final-certificate/
```

A fresh local audit of that directory established:

- 24 of 25 tree leaves have a solver verdict with `solver_rc = 20`.
- Each of those 24 retained DRAT files matches the hash in its solver
  verdict.
- Each has a matching `proof_verdicts.jsonl` record with
  `status = VERIFIED` and the same proof hash.
- The only missing leaf is cube 17.

This is strong partial evidence, but it is not a complete campaign.

### The hard threshold leaf

Cube 17 has literals:

```text
[72000, 71692, 71846, -71855, -71547,
 72308, 71384, -72163, 74618, 74926]
```

Recorded direct attempts in `proofs/final-certificate/verdicts.jsonl`:

- CaDiCaL, 120 seconds: no UNSAT result; 28179343 proof bytes before stop.
- CaDiCaL, 900 seconds: no UNSAT result; 144812303 proof bytes before stop.
- Kissat, 900 seconds: no UNSAT result; 220898680 proof bytes before stop.

All three records have `solver_rc = 0`, `status = ERROR`, and no accepted
proof hash. Their partial proof streams are not certificate evidence.

The older `proofs/certificate/` directory is a superseded 22-leaf campaign.
It has 21 checked leaves and one failed leaf, cube 14. That failed region was
split to produce the better 25-leaf tree above. Do not present either
directory as a final certificate.

### Legacy provenance blocker

The 24 successful rows in `proofs/final-certificate/verdicts.jsonl` predate
mixed-solver provenance support. They contain the proof hash and successful
solver return code, but omit `solver` and `solver_sha256`.

The current `assemble_adaptive_campaign.py` deliberately requires those
fields per accepted verdict. A dry assembly therefore fails with:

```text
ValueError: source artifacts are missing or changed for cube 0:
.../proofs/final-certificate
```

The proof and checker hashes themselves were re-audited and match. The
immediate cause of this assembler error is the absent per-verdict solver
metadata: the assembler resolves the missing solver path to a non-file.

Before reusing these 24 proofs, implement one of these transparent,
tested migrations:

1. Teach the assembler to infer missing solver path/hash only from the
   campaign's checked manifest, while preserving explicit per-verdict values
   for modern mixed-solver records. Copy the inferred fields into the
   assembled verdict and mark their provenance as manifest-derived.
2. Preferably, create a normalized legacy-campaign directory without
   modifying the original. Copy the immutable proofs and logs, add the
   manifest-pinned CaDiCaL path/hash to the 24 old verdicts, verify all hashes,
   and rerun `drat-trim` for every proof.

Add tests covering legacy single-solver fallback, modern mixed-solver
records, a solver-hash mismatch, and a missing solver binary. Do not merely
weaken the artifact check.

### Suggested next threshold experiment

Because both solvers already timed out at 900 seconds, another unchanged
direct retry has low information value. First try a new, bounded partition of
cube 17, keeping splits on the 344 mathematical coloring variables:

```sh
python3 bulk_refine_adaptive_leaves.py \
  --base proofs/k19_N344_x1.cnf \
  --tree proofs/adaptive/k19_N344_final25.tree.json \
  --leaf 17 \
  --depth 4 \
  --cuber-max-variable 344 \
  --jobs 1 \
  --output proofs/adaptive/k19_N344_threshold-c17-d4.tree.json \
  --plan-output proofs/adaptive/k19_N344_threshold-c17-d4.plan.json
```

Use the generated plan's `indices_spec` for a fresh campaign:

```sh
INDICES=$(python3 -c "import json; print(json.load(open('proofs/adaptive/k19_N344_threshold-c17-d4.plan.json'))['indices_spec'])")

python3 cube_campaign.py \
  --base proofs/k19_N344_x1.cnf \
  --tree proofs/adaptive/k19_N344_threshold-c17-d4.tree.json \
  --solver tools/bin/cadical \
  --checker tools/bin/drat-trim \
  --campaign proofs/adaptive/k19_N344_threshold-c17-d4-cadical120 \
  --n-original 344 --k 19 \
  --indices "$INDICES" \
  --jobs 8 --timeout 130 \
  --solver-arg=--unsat \
  --solver-arg=-t \
  --solver-arg=120 \
  --defer-check \
  --discard-partial-proofs
```

If this partition also stalls, test solver diversity or a deeper partition
on only its unresolved children. Existing trees `final28` through `final52`,
`original55`, and `original-d4` record earlier unsuccessful refinement
directions; compare literal tuples before repeating them.

If a direct retry is desired, use a **new** campaign directory because the
existing manifest pins CaDiCaL and its old arguments:

```sh
python3 cube_campaign.py \
  --base proofs/k19_N344_x1.cnf \
  --tree proofs/adaptive/k19_N344_final25.tree.json \
  --solver tools/bin/kissat \
  --checker tools/bin/drat-trim \
  --campaign proofs/adaptive/k19_N344_threshold-c17-kissat3600 \
  --n-original 344 --k 19 \
  --indices 17 \
  --jobs 1 --timeout 3610 \
  --solver-arg=--unsat \
  --solver-arg=--time=3600 \
  --defer-check \
  --discard-partial-proofs
```

Do not point a different solver or argument list at
`proofs/final-certificate`; its manifest intentionally prevents that.

## Route B: compact sliding CNF

### Audited instance

```text
proofs/k19_N344_x1_sliding.cnf
```

Properties:

- 32005 variables
- 138594 clauses
- 173 residue-chain roots
- 2943 exact overlap transitions
- SHA-256
  `ab670b737250f5bb23e7849bbdb8b1ded24e8c5149c6e3da22d456f1ac27644e`

Independent audit:

```text
proofs/k19_N344_x1_sliding.cnf.audit.json
```

It reports `PASS` for the root counter truth tables, overlap relation truth
table, progression-chain partition, and exact clause stream.

### Authoritative sliding baseline

Tree:

```text
proofs/adaptive/k19_N344_sliding_probe3912d4-final3993-r1.tree.json
```

Tree properties:

- 6901 leaves
- 13801 nodes
- maximum depth 100
- no filled-gap leaves
- SHA-256
  `887d7e3a44c926bd9b2f8769ec8e1853330367c2dca229bb6b9fd6232e14749e`

Current dry assembly report:

```text
proofs/adaptive/k19_N344_sliding-final-assembly-plan.json
```

It reports:

- `complete = false`
- 6637 covered leaves
- 264 missing leaves
- 3102687976 bytes of selected proof candidates
- 35546943 bytes of selected solver logs

The modern assembler validated source manifests, exact leaf literal tuples,
proof hashes, solver paths, and solver hashes before counting those 6637
candidates. They still require a final independent `--recheck` after complete
assembly.

### Missing sliding leaves

The missing set is:

```text
4018:4273,4635,4699,4731,4747,4755,4759,4761,4762,5034
```

The range uses a half-open stop, so `4018:4273` means leaf IDs 4018 through
4272 inclusive.

Structure:

- 255 leaves are the contiguous block 4018 through 4272.
- All 255 have 84 literals and share a 76-literal tree prefix.
- The remaining 9 leaves have 76 literals and lie elsewhere in the tree.

Never infer compatibility from a leaf ID. The assembler correctly keys proof
reuse by the entire literal tuple.

### Direct attempts on the 264 leaves

Campaign:

```text
proofs/adaptive/k19_N344_sliding_final_missing264-cadical10/
```

Result:

- CaDiCaL tried all 264 leaves at 10 seconds each.
- 264 returned no UNSAT proof.
- 0 closed.

Campaign:

```text
proofs/adaptive/k19_N344_sliding_final_missing264-kissat60/
```

Result:

- Kissat tried all 264 missing leaves at 60 seconds each.
- All 264 reached the limit without an UNSAT proof.
- 0 closed.
- Partial proofs were discarded.

This is enough evidence not to continue the same flat short-timeout pass.

### Subdivision pilots for baseline leaf 4018

These are three **alternative** replacement trees for the same baseline leaf.
Choose at most one lineage. Their proofs cannot be combined as siblings
because the trees represent different partitions below leaf 4018.

Depth-4 pilot:

```text
proofs/adaptive/k19_N344_sliding_missing264-pilot4018-r1.tree.json
proofs/adaptive/k19_N344_sliding_missing264-pilot4018-r1/
proofs/adaptive/k19_N344_sliding_missing264-pilot4018-r1-kissat60/
```

Results:

- The leaf became 16 children of length 88.
- CaDiCaL at 10 seconds produced 4 unchecked UNSAT proofs and left 12 open.
- Kissat at 60 seconds produced 1 more unchecked UNSAT proof and left 11
  open.

Depth-6 pilot:

```text
proofs/adaptive/k19_N344_sliding_missing264-pilot4018d6-r1.tree.json
proofs/adaptive/k19_N344_sliding_missing264-pilot4018d6-r1/
```

Results:

- The leaf became 64 children of length 90.
- CaDiCaL at 10 seconds produced 23 unchecked UNSAT proofs.
- 41 children remained open.

Depth-8 pilot:

```text
proofs/adaptive/k19_N344_sliding_missing264-pilot4018d8-r1.tree.json
proofs/adaptive/k19_N344_sliding_missing264-pilot4018d8-r1.plan.json
```

Results:

- The leaf became 256 children of length 92.
- The resulting tree has 7156 leaves.
- The inserted children are IDs `4018:4274`.
- Tree SHA-256:
  `bbbf134f750d5f3fc606fa51bf1e1edf82fcd437bda92afbd1030ee76b361293`
- No solver campaign has been run on these 256 children.

The depth-4 and depth-6 proof records have status `UNVERIFIED`. They are not
certificate evidence until checked, and they apply only if their respective
pilot tree is selected.

### Suggested next sliding experiment

The depth-8 tree is already generated. Run a cheap, proof-producing probe
before multiplying it across the 255-leaf block:

```sh
python3 cube_campaign.py \
  --base proofs/k19_N344_x1_sliding.cnf \
  --tree proofs/adaptive/k19_N344_sliding_missing264-pilot4018d8-r1.tree.json \
  --solver tools/bin/cadical \
  --checker tools/bin/drat-trim \
  --campaign proofs/adaptive/k19_N344_sliding_missing264-pilot4018d8-cadical10 \
  --n-original 344 --k 19 \
  --indices 4018:4274 \
  --jobs 8 --timeout 12 \
  --solver-arg=--unsat \
  --solver-arg=-t \
  --solver-arg=10 \
  --defer-check \
  --discard-partial-proofs
```

Measure the closure rate and retained proof volume. Do not extrapolate a
full 255-leaf expansion until this pilot is known:

- Depth 4 closed only 5 of 16 children after the CaDiCaL and Kissat waves.
- Depth 6 closed 23 of 64.
- A bulk depth-6 or depth-8 expansion could create tens of thousands of
  final proof obligations.

If a selected depth closes well, use
`bulk_refine_adaptive_leaves.py` in bounded batches, such as 8 or 16 baseline
leaves, rather than transforming all 255 at once. Solve and inspect each batch
before growing the tree again. Keep the nine 76-literal leaves in a separate
pilot because they likely require a different depth.

The bulk refiner emits:

- an audited replacement tree;
- a plan binding the base, input tree, output tree, cuber, and SHA-256 hashes;
- the exact new leaf IDs and a ready-to-use `indices_spec`.

When refining unresolved children again, always start from the latest selected
tree and select leaves by their current IDs. Preserve old campaigns
unchanged; the assembler can recover unchanged proof tuples later.

## Final certificate procedure

The final procedure is the same for either CNF route.

### 1. Dry assembly

Use the final selected tree and all compatible campaign roots. Omit
`--output` first:

```sh
python3 assemble_adaptive_campaign.py \
  --tree FINAL_TREE.json \
  --reference-campaign REFERENCE_CAMPAIGN \
  --source-root proofs/adaptive
```

For the threshold route, include the normalized legacy campaign after fixing
the provenance issue. Do not include a source root containing malformed
legacy campaigns until the assembler can normalize or skip them safely.

The command must exit 0 and print:

```json
{"complete": true}
```

among the report fields. Any nonzero exit or nonempty `missing_leaves` means
the certificate is incomplete.

### 2. Materialize the assembled campaign

```sh
python3 assemble_adaptive_campaign.py \
  --tree FINAL_TREE.json \
  --reference-campaign REFERENCE_CAMPAIGN \
  --source-root proofs/adaptive \
  --output proofs/certificate-complete
```

The destination must not already exist. The assembler copies artifacts,
checks their hashes before and after copying, records exact source campaigns,
and refuses incomplete coverage.

### 3. Recheck every proof

```sh
python3 verify_campaign.py \
  --campaign proofs/certificate-complete \
  --checker tools/bin/drat-trim \
  --jobs 8 \
  --recheck
```

Do not rely only on source campaigns' old checker records.

### 4. Run the fail-closed gate

```sh
python3 gate_campaign.py \
  --campaign proofs/certificate-complete
```

The gate must verify the tree and base hashes, complete leaf coverage,
per-cube proof and log hashes, solver provenance, and latest checker status.

### 5. Create the release manifest

For the threshold CNF:

```sh
python3 make_campaign_release_manifest.py \
  --campaign proofs/certificate-complete \
  --cnf-audit proofs/adaptive/k19_N344_x1.cnf.audit.json \
  --output certificate_manifest.json
```

For the sliding CNF:

```sh
python3 make_campaign_release_manifest.py \
  --campaign proofs/certificate-complete \
  --cnf-audit proofs/k19_N344_x1_sliding.cnf.audit.json \
  --output certificate_manifest.json
```

Only after these five steps succeed should `MATHEMATICS.md` be changed from
“candidate equality” to a theorem statement.

## Trusted base and proof logic

The SAT and cuber binaries are not trusted for correctness.

The argument is:

1. An independent auditor verifies that the archived CNF exactly encodes the
   mathematical avoidance problem.
2. The adaptive-tree auditor verifies a full binary decision tree whose
   leaves partition all assignments.
3. `drat-trim` independently checks an UNSAT proof for the base CNF plus each
   leaf's unit literals.
4. Therefore every assignment is excluded and the base CNF is UNSAT.

The cuber's branch choices may be heuristic or patched. Soundness comes from
the serialized tree audit and independent proof checks, not trust in the
cuber.

Pinned tool versions and source commits are in `TOOLCHAIN.md`. Important
local binary hashes seen in the current artifacts are:

- CaDiCaL:
  `c4be053d54dada4c6da01d6819571ea053943423cd3249ff8a097e3fab8ae995`
- Kissat:
  `3e3da1083465c712da393e16cd01f87cbdc38bdda240541c6449b384436edfd4`
- `drat-trim`:
  `45039a924080537bd839f21b41127ba2fa5002f7bc61945bfa36e7d49b9880ca`
- CaDiCaL cuber:
  `65163322c67541f5614da5520d78eda21269b613ce36e432511c20b1d22a1d90`

Rebuilds are acceptable only if the new binary hashes and source revisions
are recorded in fresh manifests.

## Important invariants and failure modes

- A solver timeout, `UNKNOWN`, `ERROR`, partial DRAT, or unchecked
  `UNVERIFIED` record does not prove anything.
- Never reuse a proof by cube ID after changing a tree. Leaf IDs are
  reassigned. Match the full literal tuple.
- Never combine proofs from alternative refinements of the same leaf into
  one tree.
- Never combine threshold-CNF and sliding-CNF cube proofs.
- Use a fresh campaign directory whenever the tree, solver, checker, solver
  arguments, or proof format changes.
- Use `--discard-partial-proofs` for broad probes. It preserves complete
  UNSAT proofs and removes incomplete streams after timeout.
- Keep proof checking deferred during broad solver waves if needed, but run
  `verify_campaign.py --recheck` before the final gate.
- The assembler's `complete` count is not the final gate. It counts valid
  retained solver proofs; the assembled result still needs independent
  rechecking.
- Many manifests contain absolute paths under
  `/Users/yotam.manor/code/devex-construct`. Moving the workspace may require
  a deliberate relocation/migration step; do not silently edit hashed
  manifests.
- The macOS Cursor agent runs under Seatbelt. Long campaigns and tools that
  write temporary files were run through the documented host/tmux boundary.
  Do not treat sandbox permission failures as solver failures.

## Code added or materially changed

The research directory contains the complete generator, auditors, campaign
runner, assembler, gate, and release tooling. Recent material changes include:

- `cube_campaign.py`
  - supports `--discard-partial-proofs`;
  - keeps complete UNSAT proofs while deleting incomplete timeout streams.
- `assemble_adaptive_campaign.py`
  - supports per-cube mixed-solver provenance;
  - reports selected proof and solver-log byte totals;
  - still intentionally rejects legacy verdict rows lacking solver metadata.
- `adaptive_cube_tree.py`
  - audits complete binary partitions;
  - can refine one leaf;
  - now also supports simultaneous multi-leaf refinement and exact-subtree
    replacement.
- `refine_adaptive_tree.py`
  - supports either `--leaf` or an exact `--prefix-literals` subtree path.
- `bulk_refine_adaptive_leaves.py`
  - runs cubers for multiple leaves in parallel;
  - reconstructs and audits one combined tree;
  - writes a hash-bound refinement plan and exact campaign indices.
- `recover_refinement_queue.py`
  - reconstructs interrupted adaptive queues from immutable artifacts.
- `verify_campaign.py`, `gate_campaign.py`, and
  `make_campaign_release_manifest.py`
  - provide the final independent verification and fail-closed release path.

The bulk orchestration script is new. Its underlying multi-leaf tree
replacement is unit-tested and the script passes compilation, but it has not
yet driven a production multi-leaf campaign. Start with a small bounded batch
and independently audit its output tree before scaling it.

## Validation snapshot

At handoff, the complete Python unit-test suite passed:

```text
Ran 59 tests
OK
```

Reproduce with:

```sh
PYTHONDONTWRITEBYTECODE=1 \
python3 -m unittest discover -s . -p 'test_*.py'
```

## Repository and storage state

This directory is a standalone Git repository published privately at:

```text
https://github.com/yotammanor/erdos-176-n19
```

Its default branch is `main`. It is nested inside an unrelated, dirty
`devex-construct` working tree; run Git commands from this directory so they
target the standalone repository. Do not run cleanup or reset commands from
the parent repository.

The local `.gitignore` intentionally excludes:

- solver/checker binaries under `tools/`;
- DRAT, LRAT, PB proof streams;
- logs;
- Python caches.
- transient `cube-campaign-*` CNFs and refinement scratch directories.

Consequences:

- The private Git repository contains the source, documentation, witnesses,
  audited CNF/OPB instances, trees, manifests, and small campaign metadata.
- A normal clone will not contain the large proof payloads or pinned local
  binaries.
- The current 3.10 GB selected sliding proof set and the threshold proof
  files must be archived separately.
- Before mathematical publication, package the large immutable artifacts with
  checksums in durable storage.

## Literature and claim boundary

The literature audit was refreshed on 2026-09-09.

- OEIS A398541 ended at \(N(17,2)=274\).
- Lystad's dataset supplied the \(k=19\), length-343 witness but no upper
  certificate.
- A public Erdős Problem 176 discussion conjectured
  \(N(p,2)=p^2-p+2\) for primes \(p\ge11\), so the value 344 was already
  conjectured.
- No public proof or UNSAT certificate for \(N(19,2)\le344\) was found.

An absence search is not a priority proof. Refresh OEIS, Zenodo, the Erdős
Problems page/thread, and relevant repositories immediately before any
public claim. The possible new contribution is only the complete checked
upper-bound certificate, not the lower witness or conjectured value.

## Definition of done

The task is complete only when all of the following are true:

- The 343 witness and independent witness audit are archived.
- One exact \(N=344\) instance and its independent encoding audit are
  archived.
- One audited adaptive tree is selected.
- Every leaf has a retained UNSAT proof.
- Every retained proof passes an independent checker from a clean recheck.
- The fail-closed campaign gate passes.
- The release manifest pins every instance, tree, proof, log, solver,
  checker, audit, and source artifact by hash.
- The literature audit is refreshed.
- The theorem write-up clearly distinguishes prior work from the new checked
  upper bound.

Until then, the project remains a substantial partial computation rather
than a solution.
