"""Independent checks for the N(k,2) evaluator and CNF encoding."""

from __future__ import annotations

import itertools
import json
import tempfile
import unittest
from pathlib import Path

import cube_campaign
import nk2


def cnf_sat(
    clauses: list[list[int]], assumptions: tuple[int, ...] = ()
) -> bool:
    """Small independent DPLL solver used only for encoding unit tests."""

    def search(assignment: dict[int, bool]) -> bool:
        while True:
            unit: int | None = None
            shortest: list[int] | None = None
            for clause in clauses:
                undecided: list[int] = []
                satisfied = False
                for literal in clause:
                    value = assignment.get(abs(literal))
                    if value is None:
                        undecided.append(literal)
                    elif value == (literal > 0):
                        satisfied = True
                        break
                if satisfied:
                    continue
                if not undecided:
                    return False
                if len(undecided) == 1:
                    unit = undecided[0]
                    break
                if shortest is None or len(undecided) < len(shortest):
                    shortest = undecided

            if unit is None:
                if shortest is None:
                    return True
                branch = shortest[0]
                for literal in (branch, -branch):
                    extended = assignment.copy()
                    extended[abs(literal)] = literal > 0
                    if search(extended):
                        return True
                return False

            variable, value = abs(unit), unit > 0
            previous = assignment.get(variable)
            if previous is not None and previous != value:
                return False
            assignment[variable] = value

    initial: dict[int, bool] = {}
    for literal in assumptions:
        variable, value = abs(literal), literal > 0
        if variable in initial and initial[variable] != value:
            return False
        initial[variable] = value
    return search(initial)


class ProgressionTests(unittest.TestCase):
    def test_count_matches_enumeration(self) -> None:
        for n in range(0, 30):
            for k in range(2, 12):
                self.assertEqual(nk2.num_aps(n, k), len(list(nk2.iter_aps(n, k))))

    def test_known_three_term_witness(self) -> None:
        coloring = tuple(1 if symbol == "+" else -1 for symbol in "--++--++")
        result = nk2.verify_coloring(coloring, k=3, ell=2)
        self.assertTrue(result["avoids"])
        self.assertEqual(result["max_abs_sum"], 1)

    def test_prime_lower_bound_construction(self) -> None:
        for prime in (3, 5, 7, 11, 13, 17, 19):
            coloring = nk2.prime_lower_bound_witness(prime)
            self.assertEqual(prime * (prime - 1) + 1, len(coloring))
            self.assertTrue(nk2.verify_coloring(coloring, prime, 2)["avoids"])

    def test_published_k19_witness_matches_construction(self) -> None:
        published = nk2.parse_coloring(
            Path(__file__).with_name("witnesses") / "k19_N343.txt"
        )
        self.assertEqual(nk2.prime_lower_bound_witness(19), published)


class EncodingTests(unittest.TestCase):
    @staticmethod
    def encoded_sat(n: int, k: int, ell: int, encoding: str) -> bool:
        clauses, _ = nk2.build_cnf(n, k, ell, encoding=encoding)
        return cnf_sat(clauses)

    def test_encoding_matches_brute_force_small_instances(self) -> None:
        for encoding in ("threshold", "totalizer"):
            for k in range(2, 7):
                for n in range(k, min(k + 5, 10)):
                    expected = nk2.brute_force_avoider(n, k, 2) is not None
                    self.assertEqual(
                        expected,
                        self.encoded_sat(n, k, 2, encoding),
                        (encoding, n, k),
                    )

    def test_single_ap_cardinality_semantics(self) -> None:
        # N=k has exactly one AP. Check every assignment, including auxiliary
        # existential choices made by both cardinality encodings.
        for encoding in ("threshold", "totalizer"):
            for k in range(2, 10):
                clauses, _ = nk2.build_cnf(k, k, 2, encoding=encoding)
                for bits in itertools.product((False, True), repeat=k):
                    assumptions = [
                        position if value else -position
                        for position, value in enumerate(bits, start=1)
                    ]
                    expected = abs(sum(1 if value else -1 for value in bits)) < 2
                    self.assertEqual(
                        expected,
                        cnf_sat(clauses, tuple(assumptions)),
                        (encoding, k, bits),
                    )

    def test_opb_matches_exact_evaluator_on_small_instances(self) -> None:
        def satisfies_opb(text: str, bits: tuple[bool, ...]) -> bool:
            for line in text.splitlines():
                if not line or line.startswith("*"):
                    continue
                left, right = line.removesuffix(";").split(">=")
                terms = left.split()
                total = sum(
                    int(terms[index])
                    * bits[int(terms[index + 1].removeprefix("x")) - 1]
                    for index in range(0, len(terms), 2)
                )
                if total < int(right):
                    return False
            return True

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "instance.opb"
            for k in range(2, 6):
                for n in range(k, k + 3):
                    metadata = nk2.write_opb(path, n, k, 2)
                    text = path.read_text(encoding="ascii")
                    self.assertTrue(
                        text.startswith(
                            f"* #variable= {n} "
                            f"#constraint= {metadata['nconstraints']} "
                            "#equal= 0 intsize= 32\n"
                        )
                    )
                    for bits in itertools.product((False, True), repeat=n):
                        coloring = tuple(1 if value else -1 for value in bits)
                        expected = nk2.verify_coloring(coloring, k, 2)["avoids"]
                        self.assertEqual(
                            expected,
                            satisfies_opb(text, bits),
                            (n, k, bits),
                        )

    def test_state_opb_is_existentially_equivalent_on_small_instances(
        self,
    ) -> None:
        def satisfies_opb(text: str, bits: tuple[bool, ...]) -> bool:
            for line in text.splitlines():
                if not line or line.startswith("*"):
                    continue
                left, right = line.removesuffix(";").split(">=")
                terms = left.split()
                total = sum(
                    int(terms[index])
                    * bits[int(terms[index + 1].removeprefix("x")) - 1]
                    for index in range(0, len(terms), 2)
                )
                if total < int(right):
                    return False
            return True

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.opb"
            for k in (3, 5):
                for n in range(k, k + 3):
                    metadata = nk2.write_state_opb(path, n, k, 2)
                    text = path.read_text(encoding="ascii")
                    nstates = int(metadata["num_aps"])
                    self.assertEqual(n + nstates, metadata["nvars"])
                    for colors in itertools.product((False, True), repeat=n):
                        coloring = tuple(
                            1 if value else -1 for value in colors
                        )
                        expected = nk2.verify_coloring(coloring, k, 2)[
                            "avoids"
                        ]
                        observed = any(
                            satisfies_opb(text, colors + states)
                            for states in itertools.product(
                                (False, True),
                                repeat=nstates,
                            )
                        )
                        self.assertEqual(expected, observed, (n, k, colors))

    def test_reversal_canonicalization_truth_table(self) -> None:
        for n in range(2, 9):
            clauses, _ = nk2.build_cnf(
                n,
                n + 1,
                2,
                fix_first=True,
                canonical_reversal=True,
            )
            for tail in itertools.product((False, True), repeat=n - 1):
                bits = (True, *tail)
                reverse = tuple(reversed(bits))
                complement_reverse = tuple(not value for value in reverse)
                expected = reverse <= bits and complement_reverse <= bits
                assumptions = tuple(
                    index if value else -index
                    for index, value in enumerate(bits, start=1)
                )
                self.assertEqual(
                    expected,
                    cnf_sat(clauses, assumptions),
                    (n, bits),
                )

    def test_every_symmetry_orbit_has_a_canonical_representative(self) -> None:
        for n in range(2, 9):
            for bits in itertools.product((False, True), repeat=n):
                reverse = tuple(reversed(bits))
                complement = tuple(not value for value in bits)
                complement_reverse = tuple(not value for value in reverse)
                representative = max(bits, reverse, complement, complement_reverse)
                self.assertTrue(representative[0])
                self.assertLessEqual(tuple(reversed(representative)), representative)
                self.assertLessEqual(
                    tuple(not value for value in reversed(representative)),
                    representative,
                )

    def test_threshold_generator_size_regression(self) -> None:
        clauses, nvars = nk2.build_cnf(225, 15, 2)
        self.assertEqual(168_129, nvars)
        self.assertEqual(634_304, len(clauses))


class CampaignResumeTests(unittest.TestCase):
    def test_failed_check_overrides_unverified_solver_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            solver_path = Path(temporary) / "solver.jsonl"
            checker_path = Path(temporary) / "checker.jsonl"
            solver_path.write_text(
                json.dumps({"cube": 3, "status": "UNVERIFIED"}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                {3},
                cube_campaign.previous_completed(
                    solver_path,
                    checker_path,
                    defer_check=True,
                ),
            )
            self.assertEqual(
                set(),
                cube_campaign.previous_completed(
                    solver_path,
                    checker_path,
                    defer_check=False,
                ),
            )

            checker_path.write_text(
                json.dumps({"cube": 3, "status": "CHECK_FAILED"}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                set(),
                cube_campaign.previous_completed(
                    solver_path,
                    checker_path,
                    defer_check=True,
                ),
            )

            with checker_path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps({"cube": 3, "status": "VERIFIED"}) + "\n"
                )
            self.assertEqual(
                {3},
                cube_campaign.previous_completed(
                    solver_path,
                    checker_path,
                    defer_check=False,
                ),
            )


if __name__ == "__main__":
    unittest.main()
