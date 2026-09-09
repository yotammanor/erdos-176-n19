#!/usr/bin/env python3
"""Build the vendored RoundingSat source without requiring CMake."""

from __future__ import annotations

import argparse
import concurrent.futures
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT / "tools" / "roundingsat-src"
BOOST_ROOT = ROOT / "tools" / "boost-src"
OBJECT_ROOT = ROOT / "tools" / "roundingsat-objects"
OUTPUT = ROOT / "tools" / "bin" / "roundingsat"
ROUNDINGSAT_COMMIT = "d4edbf7908a9bb951fd181940919e0f3ac7ab1ee"


def patch_veripb_v2_rup_sentinel() -> None:
    """Do not print unsigned ID_Undef as an optional VeriPB RUP hint."""
    path = SOURCE_ROOT / "src" / "ProofBuffer.cpp"
    text = path.read_text(encoding="utf-8")
    broken = '  buffer << ID_Undef << "\\n";'
    fixed = '  buffer << "\\n";'
    if broken in text:
        path.write_text(text.replace(broken, fixed, 1), encoding="utf-8")
    elif fixed not in text:
        raise RuntimeError("unexpected RoundingSat ProofBuffer.cpp")


def compile_source(
    compiler: str,
    source: Path,
    object_root: Path,
    extra_flags: tuple[str, ...],
) -> Path:
    relative = source.relative_to(SOURCE_ROOT)
    output = object_root / ("__".join(relative.parts) + ".o")
    if output.exists() and output.stat().st_mtime_ns >= source.stat().st_mtime_ns:
        return output
    command = (
        compiler,
        "-std=c++20",
        "-O3",
        "-DNDEBUG",
        "-w",
        f"-I{BOOST_ROOT}",
        f"-I{SOURCE_ROOT / 'src'}",
        *extra_flags,
        "-c",
        str(source),
        "-o",
        str(output),
    )
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{source} failed:\n{result.stdout}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default="clang++")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--soplex-root",
        type=Path,
        help="optional installed SoPlex prefix for an LP-enabled build",
    )
    args = parser.parse_args()
    soplex_root = args.soplex_root.resolve() if args.soplex_root else None
    if soplex_root:
        object_root = ROOT / "tools" / "roundingsat-soplex-objects"
        output = ROOT / "tools" / "bin" / "roundingsat-soplex"
        compile_flags = (
            "-DWITHSOPLEX=1",
            f"-I{soplex_root / 'include'}",
        )
        link_flags = (str(soplex_root / "lib" / "libsoplex.a"),)
    else:
        object_root = OBJECT_ROOT
        output = OUTPUT
        compile_flags = ()
        link_flags = ()

    patch_veripb_v2_rup_sentinel()
    generated = SOURCE_ROOT / "src" / "CMakeConfig.hpp"
    generated_content = (
        "#ifndef _RS_CMAKE_CONFIG_HPP_\n"
        "#define _RS_CMAKE_CONFIG_HPP_\n"
        "#endif\n"
    )
    if not generated.exists() or generated.read_text() != generated_content:
        generated.write_text(generated_content, encoding="ascii")
    version = SOURCE_ROOT / "src" / "version.hpp"
    version_content = (
        "#ifndef _RS_VERSION_HPP_\n"
        "#define _RS_VERSION_HPP_\n"
        f'#define GIT_COMMIT_HASH "{ROUNDINGSAT_COMMIT}"\n'
        '#define GIT_BRANCH "master"\n'
        "#endif\n"
    )
    if not version.exists() or version.read_text() != version_content:
        version.write_text(version_content, encoding="ascii")

    sources = sorted((SOURCE_ROOT / "src").glob("*.cpp"))
    sources += sorted((SOURCE_ROOT / "src" / "used_licenses").glob("*.cpp"))
    if not sources:
        raise FileNotFoundError("RoundingSat sources are missing")
    object_root.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        objects = list(
            executor.map(
                lambda source: compile_source(
                    args.compiler,
                    source,
                    object_root,
                    compile_flags,
                ),
                sources,
            )
        )
    subprocess.run(
        (
            args.compiler,
            *(str(path) for path in objects),
            *link_flags,
            "-o",
            str(output),
        ),
        check=True,
    )
    print(f"built {output} from {len(sources)} translation units")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
