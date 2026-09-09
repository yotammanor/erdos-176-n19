# Literature and open-status audit for \(N(19,2)\)

Audit date: 2026-09-09.

## Primary records checked

- [Erdős Problem 176](https://www.erdosproblems.com/176) records the family of
  two-color arithmetic-progression discrepancy questions and still labels the
  general problem `OPEN`.  That label concerns the asymptotic family and is not,
  by itself, evidence that any particular finite value is unknown.
- [OEIS A398541](https://oeis.org/A398541) is the sequence of exact values
  \(N(k,2)\).  Its machine-readable
  [b-file](https://oeis.org/A398541/b398541.txt) currently ends with
  \(N(17,2)=274\); no \(k=19\) value is listed.
- T. Alexander Lystad's
  [*Computational Data for Erdős Discrepancy Problem #176*,
  v1.3](https://doi.org/10.5281/zenodo.21840279), published 2026-08-07,
  contains checked lower-bound witnesses for larger odd \(k\), including the
  length-343 \(k=19\) witness used here.  It does not contain an upper-bound
  proof at 344.
- The [Problem 176 discussion
  thread](https://www.erdosproblems.com/forum/thread/176?order=newest)
  publicly conjectures the exact prime formula
  \(N(p,2)=p^2-p+2\) for primes \(p\ge11\).  It therefore already predicts
  \(N(19,2)=344\).  As of this audit, the thread reports no proof claim for
  that finite case.
- Leo Zhang's
  [DiscrepancyRecords](https://github.com/Leo-Y-Zhang/DiscrepancyRecords)
  repository reports \(N(17,2)=274\) from two complete cube waves.  Its
  [`claims/CLAIMS.json`](https://github.com/Leo-Y-Zhang/DiscrepancyRecords/blob/main/claims/CLAIMS.json)
  contains no \(k=19\) claim.  Those
  \(k=17\) waves are solver-diverse but did not retain proof certificates, so
  this project adopts a stricter acceptance gate at \(k=19\).
- M. J. Goss, Jr.'s
  [2026 preprint](https://doi.org/10.5281/zenodo.20763837) conjectures
  \(N(k,2)\le k^2\).  At \(k=19\) that would give only the upper bound 361;
  it neither predicts nor proves the exact value 344.

## Search boundary

Exact-phrase and notation searches were refreshed again on 2026-09-09 for
`N(19,2)`, `N(19;2)`, `N(19, 2)`,
`discrepancy 19-term arithmetic progressions 344`, and corresponding
certificate/SAT terms.  Public code and data records linked from the sources
above were also inspected.  The live OEIS b-file still ends at
\(N(17,2)=274\), and the Problem 176 page still lists zero proof claims.  No
paper, preprint, dataset, repository, or discussion post providing an UNSAT
certificate or other proof of \(N(19,2)\le344\) was found.

Searches for “discrepancy” and “344” also return Konev and Lisitsa's
[different result](https://arxiv.org/abs/1405.3097) that the longest
*multiplicative* discrepancy-2 sequence has length 344.  That problem
constrains homogeneous progression sums
\(\sum_{i=1}^m x_{id}\) and is unrelated to the present threshold for all
translated 19-term arithmetic progressions.

An absence search cannot prove priority.  Before making a formal priority
claim, repeat the search, inspect newly released OEIS/Zenodo versions, and ask
the maintainers of the active records.  The defensible current wording is:

> As of 2026-09-09, the author found a published lower bound
> \(N(19,2)\ge344\) and a public conjecture of the exact value 344, but no
> public proof of the matching upper bound \(N(19,2)\le344\).

## Contribution boundary

The following are prior art and are not claimed as new:

1. the problem definition;
2. the prime periodic construction;
3. the explicit length-343 witness;
4. the conjecture that the exact value is 344;
5. the general use of SAT, pseudo-Boolean solving, and cube-and-conquer.

The candidate new contribution is narrowly defined: an archived \(N=344\)
instance whose correspondence to the mathematical problem is independently
audited, together with a complete UNSAT proof accepted by an independent
checker.  Until that final check succeeds, this repository does not claim to
have solved the open case.
