# Pinned certificate toolchain

The generated instances and proofs are data artifacts; solver and checker
binaries under `tools/` are intentionally not committed.  These are the
source revisions used by this workspace.

- Kissat 4.0.4, tag `rel-4.0.4`, commit
  `8af8e56f174b778aef3aa45af9f739b2a5f492c2`
- drat-trim, commit
  `2e3b2dc0ecf938addbd779d42877b6ed69d9a985`
- RoundingSat `master`, commit
  `d4edbf7908a9bb951fd181940919e0f3ac7ab1ee`
- SoPlex 7.1.1, tag `release-711`, commit
  `9a11f87c333a9e1490563a363dbb6b428d363262` (optional LP route)
- Boost headers 1.86.0
- VeriPB 3.0.2 from crates.io
- CaDiCaL 3.0.0 (secondary route)
- lrat-trim, commit
  `b30f400f4ee5c32b77ee566a7c006081b521534f`
- gratgen, commit
  `d2ff883b0c480176af53216dfce958424721d373`

`build_roundingsat.py` compiles the pinned source directly with C++20,
including the generated license translation units, and embeds the source
revision in the executable.  The local build uses:

```sh
python3 build_roundingsat.py --jobs 4

python3 build_roundingsat.py --jobs 4 \
  --soplex-root tools/soplex-install-711
```

The second command emits `tools/bin/roundingsat-soplex`.  The build helper
also applies a one-line compatibility correction in RoundingSat's VeriPB 2.0
logger: `ProofBuffer::addSubProofStepRup` must omit `ID_Undef`, whose unsigned
serialization is `18446744073709551615`, from an optional RUP-hint list.
Without that correction VeriPB rejects LP-generated subproofs.  With it, the
LP-enabled solver's proof for the independently known \(N(5,2)=22\) boundary
passes VeriPB 3.0.2.  This local solver patch is not part of the trusted base;
the independent proof checker remains the acceptance gate.

`build_cadical_cuber.py` builds a separate
`tools/bin/cadical-generate-cubes` helper from the same CaDiCaL source:

```sh
python3 build_cadical_cuber.py --jobs 4
```

CaDiCaL 3.0.0's public `generate_cubes` wrapper applies external-variable
mapping to a copy of each returned cube and discards the mapped values.  The
build helper corrects that wrapper to map each literal in place.  This local
patch affects only heuristic partition generation; it is not trusted by the
certificate.  The serialized tree is audited as a complete Boolean partition,
and `drat-trim` checks every resulting base-plus-cube formula independently.

Install the independent PB checker into the workspace:

```sh
CARGO_HOME="$PWD/tools/cargo-home" \
CARGO_TARGET_DIR="$PWD/tools/cargo-target" \
cargo install --root "$PWD/tools/veripb" --version 3.0.2 veripb
```

On Cursor's macOS sandbox this Cargo operation must run through the documented
host-terminal bridge because the `fragile` crate contains a protected
`.vscode` path.  This is a packaging/sandbox collision, not a VeriPB failure.

For a final release, archive the exact executable hashes and the complete
solver and checker logs alongside the instance, proof, and proof-job status
JSON.  The proof remains independently checkable from source: neither solver
binary is trusted by the mathematical argument.
