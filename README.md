# Exact value of \(N(19,2)\) — Erdős Problem 176

Research workspace for determining the next open odd case of the discrepancy
threshold

\[
N(k,\ell)=\min\left\{N:\ \forall f:[N]\to\{-1,+1\},\
\exists\text{ a }k\text{-AP }P,\
\left|\sum_{n\in P}f(n)\right|\ge \ell\right\}.
\]

For odd \(k=19\), an avoiding coloring has sum exactly \(-1\) or \(+1\)
on every 19-term arithmetic progression.

## Current status

- Published lower-bound certificate: a coloring of \([343]\), so
  \(N(19,2)\ge344\).
- Previously conjectured exact value: \(N(19,2)=344\).
- Missing upper side: neither current \(N=344\) adaptive route has a complete
  independently checked UNSAT certificate.
- The threshold-CNF route has 24 of 25 leaf proofs and checker records, with
  one exceptionally hard leaf plus a legacy-provenance migration remaining.
- The compact sliding-CNF route has valid proof candidates for 6637 of 6901
  leaves; 264 leaves remain unresolved.

See [`HANDOFF.md`](HANDOFF.md) for the exact artifact hashes, unresolved
leaves, completed and failed campaigns, safe resume commands, and final
certificate checklist.  The equality must not be claimed until that checklist
passes.

The lower-bound witness and prior tooling came from T. Alexander Lystad,
*Erdős Problem 176 — exact small values of the discrepancy threshold
\(N(k,2)\) with machine-checkable DRAT certificates*, v1.3 (2026),
[Zenodo record 21840279](https://zenodo.org/records/21840279), CC-BY-4.0.
That publication proves exact values only through \(k=15\); its \(k=19\)
artifact is explicitly one-sided.

The live [OEIS A398541](https://oeis.org/A398541) record was last checked on
2026-09-09.  It contains exact values through \(k=17\), ending in
\(N(17,2)=274\), and has no \(k=19\) value.

## Lower bound

The 343-symbol witness is an instance of an elementary prime construction.
For an odd prime \(p\), start with the \(p\)-periodic coloring that is positive
on residues \(1,\ldots,(p+1)/2\).  In the residue-1 column, flip its final
\((p-1)/2\) entries.  This colors \([p(p-1)+1]\).

Every \(p\)-AP of difference below \(p\) visits each residue modulo \(p\)
once.  It therefore has sum \(+1\) if its residue-1 entry was not flipped and
\(-1\) if it was.  The sole AP of difference \(p\) consists of the residue-1
column, which has \((p+1)/2\) positive and \((p-1)/2\) negative entries.
Thus

\[
N(p,2)\ge p(p-1)+2,
\]

giving \(N(19,2)\ge344\).  `nk2.py prime-witness` regenerates this
construction, and the tests confirm that it is symbol-for-symbol identical to
the published witness.

## Reproduce

Verify the published witness using two independent exact evaluators:

```sh
python3 nk2.py verify witnesses/k19_N343.txt --k 19
python3 independent_verify.py witnesses/k19_N343.txt --k 19
```

Generate the compact \(N=344\) avoidance instance:

```sh
python3 nk2.py generate --n 344 --k 19 --fix-first \
  --canonical-reversal --encoding totalizer \
  --output proofs/k19_N344_orbit_totalizer.cnf
```

`--fix-first` adds \(f(1)=+1\). This is satisfiability-preserving because
global color complementation maps every avoiding coloring to another one.
The optional reversal canonicalization selects a lexicographically greatest
representative from each orbit under complementation and interval reversal.

An independent direct pseudo-Boolean formulation is also available:

```sh
python3 nk2.py generate-opb --n 344 --k 19 --fix-first \
  --output proofs/k19_N344_x1.opb
python3 independent_audit_opb.py proofs/k19_N344_x1.opb \
  --n 344 --k 19 --ell 2 --fix-first
```

Run the encoding audit:

```sh
python3 -m unittest -v test_nk2 test_independent_audit_cnf
python3 independent_audit_cnf.py proofs/k19_N344_x1.cnf \
  --n 344 --k 19 --ell 2 --fix-first \
  --output proofs/adaptive/k19_N344_x1.cnf.audit.json
python3 audit_encoding.py \
  --solver tools/bin/kissat --checker tools/bin/drat-trim
```

Generate and independently audit the compact overlap-chain encoding:

```sh
python3 sliding_state_cnf.py proofs/k19_N344_x1_sliding.cnf \
  --n 344 --k 19 --fix-first
python3 independent_audit_sliding_cnf.py \
  proofs/k19_N344_x1_sliding.cnf \
  --n 344 --k 19 --ell 2 --fix-first \
  --output proofs/k19_N344_x1_sliding.cnf.audit.json
```

This equivalent formulation has 32005 variables and 138594 clauses.  It uses
one balanced-window counter per residue chain and exact four-variable
transitions for the remaining progressions.

Run a proof-producing backend.  `run_proof_job.py` records the exact
commands and input hash, refuses to overwrite an earlier attempt, and invokes
an independent checker after an UNSAT result:

```sh
python3 run_proof_job.py \
  --backend roundingsat \
  --label k19-n344-pb \
  --instance proofs/k19_N344_x1.opb

# Optional LP-strengthened PB route (see TOOLCHAIN.md)
python3 run_proof_job.py \
  --backend roundingsat-soplex \
  --label k19-n344-pb-lp \
  --instance proofs/k19_N344_x1.opb

python3 run_proof_job.py \
  --backend kissat \
  --label k19-n344-cnf \
  --instance proofs/k19_N344_x1_totalizer.cnf

python3 run_proof_job.py \
  --backend cadical \
  --label k19-n344-cadical \
  --instance proofs/k19_N344_x1_totalizer.cnf
```

The first route emits a VeriPB proof; the CNF routes emit DRAT.  Job state and
checker results are written under `proofs/portfolio/`.

### Certified adaptive route

The monolithic encodings can instead be split with CaDiCaL's look-ahead
brancher.  The brancher is only a heuristic: it is not in the trusted base.
`adaptive_cube_tree.py` reconstructs a complete binary partition, fills any
omitted sibling branches explicitly, and audits variable bounds and every
root-to-leaf path.

```sh
python3 build_cadical_cuber.py --jobs 4
tools/bin/cadical-generate-cubes \
  proofs/k19_N344_x1_sliding.cnf 4 cubes.json
python3 adaptive_cube_tree.py cubes.json \
  --nvars 32005 --output tree.json
```

A hard leaf can be cubed again after adding its path literals to the base CNF,
then grafted without changing the other leaves:

```sh
python3 refine_adaptive_tree.py \
  --tree tree.json --leaf LEAF_ID --cubes child-cubes.json \
  --output refined-tree.json
```

Refinement reassigns leaf IDs.  Always start a fresh campaign directory for a
refined tree; never attach leaf-indexed proofs from an older tree by ID.
`cube_campaign.py` stages transient cube CNFs and in-progress proofs outside
the watched workspace, then publishes finished proofs atomically into the
campaign.
For broad exploratory passes, `--discard-partial-proofs` removes incomplete
proof streams after a solver timeout or UNKNOWN result; complete UNSAT proofs
are still retained.
`assemble_adaptive_campaign.py` can consolidate retained proofs only after
matching each source verdict's full literal tuple against both its source tree
and the final tree.

Run, independently verify, and gate every leaf:

```sh
python3 assemble_adaptive_campaign.py \
  --tree refined-tree.json \
  --reference-campaign proofs/adaptive/sliding-lookahead-serial-v5 \
  --source-root proofs/adaptive \
  --output proofs/certificate
python3 verify_campaign.py \
  --campaign proofs/certificate --checker tools/bin/drat-trim \
  --jobs 8 --recheck
python3 gate_campaign.py --campaign proofs/certificate
python3 make_campaign_release_manifest.py \
  --campaign proofs/certificate \
  --cnf-audit proofs/k19_N344_x1_sliding.cnf.audit.json \
  --output certificate_manifest.json
```

The assembler refuses incomplete coverage, copies rather than hard-links proof
artifacts, and binds its report into the campaign manifest.  The campaign
manifest pins the base CNF, adaptive tree, checker, every contributing solver,
and assembly report by SHA-256; solver provenance is also retained per cube.
Compatible campaigns may use different DRAT-producing solvers because every
assembled proof is checked independently.  Assembly is not a certificate: the
gate accepts the upper bound only after `verify_campaign.py --recheck` has
independently checked every final-tree proof, every latest checker record
contains `s VERIFIED`, and every retained proof and checker log has the
recorded hash.

## Proof standard

Equality requires both:

1. the 343-symbol witness passes two independent exhaustive AP evaluators;
2. a proof-producing SAT solver reports UNSAT at 344 and an independent
   DRAT/LRAT checker validates the proof against the archived DIMACS file, or
   a PB solver's proof passes VeriPB against the independently audited OPB
   file.

A solver verdict without a checked proof is not treated as a solution.
