# Toward the exact value \(N(19,2)\)

## Status

As of 2026-09-09, the unconditional result established here is

\[
N(19,2)\ge 344.
\]

The candidate equality \(N(19,2)=344\) still requires a complete UNSAT
certificate at \(N=344\) that passes an independent checker.  This document
will not label the equality a theorem until that check succeeds.
The detailed 2026-09-10 computation snapshot and continuation instructions are
in [`HANDOFF.md`](HANDOFF.md).

## Definition

For integers \(k\ge2\) and \(1\le\ell\le k\), let \(N(k,\ell)\) be the least
\(N\) such that every \(f:[N]\to\{-1,+1\}\) has a \(k\)-term arithmetic
progression \(P\) satisfying

\[
\left|\sum_{n\in P}f(n)\right|\ge\ell.
\]

For odd \(k=19\), every progression sum is odd.  Thus a coloring avoids
discrepancy \(2\) exactly when every 19-term progression has sum \(-1\) or
\(+1\).

## Prior status and novelty boundary

The current [OEIS A398541 b-file](https://oeis.org/A398541/b398541.txt)
ends at \(N(17,2)=274\); it has no \(k=19\) entry.  T. Alexander Lystad's
[Zenodo v1.3 dataset](https://doi.org/10.5281/zenodo.21840279), published
2026-08-07, gives two-sided certified values through \(k=15\) and one-sided
witnesses for larger odd \(k\), including a length-343 witness for \(k=19\).
M. J. Goss, Jr. conjectured the general upper bound \(N(k,2)\le k^2\), which
would give only \(N(19,2)\le361\), not the exact value 344.
Separately, the public [Problem 176 discussion
thread](https://www.erdosproblems.com/forum/thread/176?order=newest)
conjectures \(N(p,2)=p^2-p+2\) for primes \(p\ge11\), which does predict
\(N(19,2)=344\).

Accordingly, the published lower bound is prior work.  The only possible new
contribution here is a checked upper-bound certificate confirming that
conjectured value by proving that no avoiding coloring of \([344]\) exists.

## The lower bound

**Proposition.** For every odd prime \(p\),

\[
N(p,2)\ge p(p-1)+2.
\]

**Proof.** Color the interval \([p(p-1)+1]\).  Begin with the \(p\)-periodic
coloring that assigns \(+1\) to residues
\(1,\ldots,(p+1)/2\) and \(-1\) to the remaining residues.  In the residue-1
column, change the final \((p-1)/2\) entries from \(+1\) to \(-1\).

A \(p\)-term progression can have difference at most \(p\).  If its
difference is below \(p\), primality makes the progression visit every
residue modulo \(p\) once.  Its original sum is \(+1\), and its unique
residue-1 entry is either unchanged or flipped, so its final sum is \(+1\)
or \(-1\).  For difference \(p\), there is exactly one progression: the
residue-1 column.  It contains \((p+1)/2\) positive and \((p-1)/2\) negative
entries, hence also has sum \(+1\).  Every \(p\)-term progression therefore
has absolute sum 1. ∎

At \(p=19\), this is an avoiding coloring of length
\(19\cdot18+1=343\), proving \(N(19,2)\ge344\).  The generated coloring is
symbol-for-symbol identical to Lystad's published witness.  Both
`nk2.py verify` and the separately implemented `independent_verify.py`
exhaustively check all 3097 progressions.

### The published witness is maximal, but not uniquely so

Neither choice of a color at position 344 extends this particular witness.
If \(f(344)=+1\), then

\[
\{2,21,40,\ldots,344\}
\]

is a 19-term progression of difference 19 whose entries are all \(+1\).
If \(f(344)=-1\), the consecutive progression
\(\{326,327,\ldots,344\}\) contains eight \(+1\)'s and eleven \(-1\)'s,
so its sum is \(-3\).  These two direct obstructions prove that the
published witness is inclusion-maximal.

This observation does **not** prove the upper bound: another avoiding
coloring of \([343]\) might have extended to 344.  Excluding every such
coloring remains exactly the certificate task below.

## Exact upper-bound formulation

Introduce a Boolean \(x_i\), with \(x_i=1\) meaning \(f(i)=+1\).  If a
19-term progression \(P\) contains \(q_P=\sum_{i\in P}x_i\) positive
entries, then

\[
\sum_{i\in P}f(i)=2q_P-19.
\]

The avoidance condition is therefore equivalent to

\[
9\le q_P\le10
\]

for every \(P\).  There are

\[
\sum_{d=1}^{19}(344-18d)=3116
\]

such progressions in \([344]\).  The direct OPB instance contains the two
inequalities \(q_P\ge9\) and \(-q_P\ge-10\) for each progression, plus
\(x_1\ge1\).  Fixing \(x_1=1\) is satisfiability-preserving because global
color complementation maps avoiders to avoiders.

The resulting instance has 344 variables and 6233 constraints.  Its SHA-256
is

```text
0f19b72149de1001d6c39738f539efd52c37e7171c1dabf5a631ada98f11876c
```

`independent_audit_opb.py` parses the archived OPB without importing the
production generator, independently enumerates the progressions, derives the
allowed color counts from \(|2q-19|<2\), and compares the complete constraint
multiset.

A deterministic threshold-counter CNF used by the adaptive route has 480208
variables and 1832209 clauses.  Its SHA-256 is

```text
e548cab0efb34dd87aaa26c26f51f6a510d3eb0cf59a843b3fda0a0f4c4232b1
```

`independent_audit_cnf.py` does not import the production generator.  It
exhaustively establishes the truth table of each counter gadget, independently
enumerates all 3116 progressions, and compares every serialized clause in
order.  The archived full-instance audit reports `PASS` for both the local
truth tables and the exact 1832209-clause stream.

A compact, equivalent CNF uses the overlap chains directly.  Let
\(q_{a,d}\) be the number of positive entries in the progression beginning at
\(a\) with difference \(d\), and introduce a Boolean \(y_{a,d}\).  At the
first progression in each residue chain, enforce

\[
q_{a,d}-y_{a,d}=9.
\]

For every pair of consecutive overlapping progressions, enforce

\[
y_{a,d}-y_{a+d,d}-x_a+x_{a+19d}=0.
\]

The identity \(q_{a,d}-q_{a+d,d}=x_a-x_{a+19d}\) shows inductively that
\(q_{a,d}=9+y_{a,d}\) at every later node of the chain.  Because each
\(y_{a,d}\) is Boolean, every 19-term progression therefore has 9 or 10
positive entries.  Conversely, any avoiding coloring extends to these state
variables, so the compact formula is equisatisfiable with the direct one.

There are 173 residue-chain roots and 2943 overlap edges.  Encoding only the
root cardinalities gives a CNF with 32005 variables and 138594 clauses, whose
SHA-256 is

```text
ab670b737250f5bb23e7849bbdb8b1ded24e8c5149c6e3da22d456f1ac27644e
```

`independent_audit_sliding_cnf.py` separately checks the counter and overlap
truth tables, verifies that the roots and edges partition all 3116
progressions into complete chains, and regenerates the exact clause stream.

A second route uses a totalizer CNF with 461512 variables and 1358577
clauses.  Its SHA-256 is

```text
ded8037616a5972c354a3a1bd0ddd516746a77c2816f18dc3ea752e13de37db5
```

Small cases are exhaustively compared with brute force for both the totalizer
and an independently structured threshold encoding.  Known exact cases
through \(k=7\) are also solved and their DRAT proofs checked end to end.

## Certificate gate

Either of the following closes the upper bound:

1. RoundingSat reports UNSAT for the audited OPB and VeriPB reports
   `s VERIFIED UNSATISFIABLE` for its proof; or
2. Kissat reports UNSAT for the archived CNF and `drat-trim` reports
   `s VERIFIED` for its DRAT proof; or
3. an audited binary tree partitions all assignments into cubes and
   `drat-trim` reports `s VERIFIED` for the base CNF plus every leaf cube.

The adaptive cuber is not trusted.  The tree auditor checks that every split
has both Boolean children and that every leaf literal list equals its
root-to-leaf path.  Induction on the tree then shows that the leaf cubes
partition all assignments exactly once.  Consequently, if every base-plus-leaf
formula is UNSAT, the base CNF itself is UNSAT.

`run_proof_job.py` records the input digest and exact commands, distinguishes
SAT, UNKNOWN, checker failure, and verified UNSAT, and hashes a proof only
after successful checking.  A raw solver verdict is deliberately
insufficient.

When either gate succeeds, the checked upper bound \(N(19,2)\le344\), combined
with the explicit 343-witness above, yields \(N(19,2)=344\).
