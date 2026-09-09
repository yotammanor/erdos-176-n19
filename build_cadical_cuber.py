#!/usr/bin/env python3
"""Build the CaDiCaL look-ahead cube exporter used for adaptive splitting."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT / "tools" / "cadical-src"
EXTERNAL = SOURCE_ROOT / "src" / "external.cpp"
LOOKAHEAD = SOURCE_ROOT / "src" / "lookahead.cpp"
DRIVER = ROOT / "cadical_generate_cubes.cpp"
OUTPUT = ROOT / "tools" / "bin" / "cadical-generate-cubes"

BROKEN_EXTERNALIZATION = """\
  auto externalize_map = [this, externalize] (std::vector<int> cube) {
    (void) this;
    MSG ("Cube : ");
    std::for_each (begin (cube), end (cube), externalize);
  };
"""

FIXED_EXTERNALIZATION = """\
  auto externalize_map = [this, externalize] (std::vector<int> &cube) {
    (void) this;
    MSG ("Cube : ");
    for (auto &literal : cube)
      literal = externalize (literal);
  };
"""

PLAIN_LOOKAHEAD_HEADER = """\
#include "internal.hpp"

namespace CaDiCaL {
"""

MAX_ONLY_LOOKAHEAD_HEADER = """\
#include "internal.hpp"

#include <climits>
#include <cstdlib>

namespace CaDiCaL {

static int lookahead_variable_limit () {
  static const int limit = [] () {
    const char *text = std::getenv ("CADICAL_CUBE_MAX_INTERNAL_VAR");
    if (!text || !*text)
      return 0;
    const long value = std::strtol (text, nullptr, 10);
    return value > 0 && value <= INT_MAX ? static_cast<int> (value) : 0;
  } ();
  return limit;
}

static bool lookahead_variable_allowed (int idx) {
  const int limit = lookahead_variable_limit ();
  return !limit || idx <= limit;
}
"""

LIMITED_LOOKAHEAD_HEADER = """\
#include "internal.hpp"

#include <climits>
#include <cstdlib>

namespace CaDiCaL {

static int lookahead_environment_positive (const char *name) {
  const char *text = std::getenv (name);
  if (!text || !*text)
    return 0;
  const long value = std::strtol (text, nullptr, 10);
  return value > 0 && value <= INT_MAX ? static_cast<int> (value) : 0;
}

static bool lookahead_variable_allowed (int idx) {
  static const int limit =
      lookahead_environment_positive ("CADICAL_CUBE_MAX_INTERNAL_VAR");
  static const int base =
      lookahead_environment_positive ("CADICAL_CUBE_INTERNAL_BASE");
  static const int stride =
      lookahead_environment_positive ("CADICAL_CUBE_INTERNAL_STRIDE");
  if (base && stride)
    return idx >= base && (!limit || idx <= limit) &&
           (idx - base) % stride == 0;
  return !limit || idx <= limit;
}
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_returned_cube_literals() -> None:
    """Make the public API return external rather than internal literals."""
    text = EXTERNAL.read_text(encoding="utf-8")
    if BROKEN_EXTERNALIZATION in text:
        EXTERNAL.write_text(
            text.replace(
                BROKEN_EXTERNALIZATION,
                FIXED_EXTERNALIZATION,
                1,
            ),
            encoding="utf-8",
        )
    elif FIXED_EXTERNALIZATION not in text:
        raise RuntimeError("unexpected CaDiCaL external.cpp cube exporter")


def patch_optional_variable_limit() -> None:
    """Let the cuber restrict look-ahead choices to frozen variable sets."""
    text = LOOKAHEAD.read_text(encoding="utf-8")
    if PLAIN_LOOKAHEAD_HEADER in text:
        text = text.replace(
            PLAIN_LOOKAHEAD_HEADER,
            LIMITED_LOOKAHEAD_HEADER,
            1,
        )
    elif MAX_ONLY_LOOKAHEAD_HEADER in text:
        text = text.replace(
            MAX_ONLY_LOOKAHEAD_HEADER,
            LIMITED_LOOKAHEAD_HEADER,
            1,
        )
    elif LIMITED_LOOKAHEAD_HEADER not in text:
        raise RuntimeError("unexpected CaDiCaL lookahead.cpp header")

    replacements = (
        (
            """\
        if (active (lit))
          ++loccs[std::abs (lit)];
""",
            """\
        if (active (lit) && lookahead_variable_allowed (std::abs (lit)))
          ++loccs[std::abs (lit)];
""",
        ),
        (
            """\
    if (active (abs (lit)) && !assumed (lit) && !assumed (-lit) &&
        !val (lit))
""",
            """\
    if (lookahead_variable_allowed (abs (lit)) && active (abs (lit)) &&
        !assumed (lit) && !assumed (-lit) && !val (lit))
""",
        ),
        (
            """\
  for (int idx = 1; idx <= max_var; idx++) {
    if (!active (idx) || assumed (idx) || assumed (-idx) || val (idx))
""",
            """\
  for (int idx = 1; idx <= max_var; idx++) {
    if (!lookahead_variable_allowed (idx) || !active (idx) ||
        assumed (idx) || assumed (-idx) || val (idx))
""",
        ),
        (
            """\
  for (int idx = 1; idx <= max_var; idx++) {

    // Then focus on roots of the binary implication graph, which are
""",
            """\
  for (int idx = 1; idx <= max_var; idx++) {
    if (!lookahead_variable_allowed (idx))
      continue;

    // Then focus on roots of the binary implication graph, which are
""",
        ),
    )
    for plain, limited in replacements:
        if plain in text:
            text = text.replace(plain, limited, 1)
        elif limited not in text:
            raise RuntimeError("unexpected CaDiCaL lookahead.cpp body")
    LOOKAHEAD.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--compiler", default=os.environ.get("CXX", "c++"))
    args = parser.parse_args()
    if args.jobs < 1:
        raise ValueError("--jobs must be positive")
    if not EXTERNAL.is_file():
        raise FileNotFoundError(EXTERNAL)
    if not DRIVER.is_file():
        raise FileNotFoundError(DRIVER)

    patch_returned_cube_literals()
    patch_optional_variable_limit()
    build = SOURCE_ROOT / "build"
    subprocess.run(
        (
            "make",
            "-C",
            str(build),
            f"-j{args.jobs}",
            "libcadical.a",
        ),
        check=True,
    )
    library = build / "libcadical.a"
    if not library.is_file():
        raise FileNotFoundError(library)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        (
            args.compiler,
            "-std=c++11",
            "-O3",
            "-DNDEBUG",
            "-I",
            str(SOURCE_ROOT / "src"),
            str(DRIVER),
            str(library),
            "-o",
            str(OUTPUT),
        ),
        check=True,
    )
    print(f"built {OUTPUT}")
    print(f"sha256 {sha256(OUTPUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
