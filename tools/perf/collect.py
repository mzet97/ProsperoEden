#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Import PS5 stdout logs into validated JSONL performance records.

Usage:
    python3 tools/perf/collect.py session.log > session.jsonl
    python3 tools/perf/collect.py a.log b.log --run dev-A > runs.jsonl
    cat session.log | python3 tools/perf/collect.py > session.jsonl

Every EDEN_* line becomes one JSON object per line: marker fields plus
"_marker", "_line", "_file" and "_run". Lines that fail to parse are
reported on stderr with their line number and skipped -- never
interpolated. Records missing required keys are kept with
"complete": false so the analyzer can exclude them explicitly.
Stdlib only.
"""
import json
import sys
from typing import Final

# One parsed k=v value: ints, floats, plain strings, or small homogeneous
# lists (cond CSV, ms CSV, idleN triples, trailing tokens).
RecordValue = int | float | str | bool | list[int] | list[float] | list[str]
Record = dict[str, RecordValue]

# Keys printed with %llx / %x (plain hex, no 0x prefix).
HEX_KEYS: Final = frozenset({
    "window", "pc", "location", "entry", "address", "mask",
})

# Minimal required keys per marker; a record missing any is incomplete.
REQUIRED: Final = {
    "EDEN_VULKAN_FRAME": ("frames", "seconds", "fps", "worst_ms", "total"),
    "EDEN_DEV_FRAME": ("frames", "seconds", "fps", "worst_ms", "total"),
    "EDEN_GAME_FRAME": ("frames", "seconds", "fps", "worst_ms", "total"),
    "EDEN_VULKAN_INTERVALS": ("v1", "v2", "v3", "v4plus", "half"),
    "EDEN_DEV_GPU": ("frame", "mono_ns", "idle_ns", "dispatch_calls",
                     "dispatch_ns", "draws"),
    "EDEN_DEV_GUEST": ("cpu_write_calls", "cpu_write_ns"),
    "EDEN_VULKAN_COST": ("api", "calls", "ns"),
    "EDEN_VULKAN_FRAMES": ("n", "overflow", "budget_ms", "ms"),
    "EDEN_FASTMEM": ("pages", "direct_reads", "direct_writes", "faults"),
    "EDEN_PERF_PROGRESS": ("core", "compilations", "compile_ns"),
    "EDEN_PERF_JIT": ("core", "compilations", "compile_ns"),
    "EDEN_PERF_DIRECT": ("total", "largest_free", "free"),
    "EDEN_PERF_HEAP": ("arenas",),
    "EDEN_GPU_TIME": ("wall_ms", "busy_ms", "submissions"),
    "EDEN_PERF_CLOCK_READ": ("calls", "elapsed_ns"),
}


def parse_value(key: str, text: str) -> RecordValue:
    """Convert one k=v token; hex keys first, then int, float, else str."""
    if key in HEX_KEYS:
        try:
            return int(text, 16)
        except ValueError:
            return text
    try:
        return int(text, 10)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_float_csv(text: str) -> list[float] | str:
    """ms=a,b,c -> [floats]; raw text when any entry is not a number."""
    try:
        return [float(v) for v in text.split(",")]
    except ValueError:
        return text


def parse_idle_triple(text: str) -> list[int] | str:
    """idleN=calls/ms/sleeps -> [calls, ms, sleeps] (ints, best effort)."""
    parts = text.split("/")
    if len(parts) != 3:
        return text
    try:
        return [int(p) for p in parts]
    except ValueError:
        return text


def parse_line(line: str) -> Record | None:
    """Parse one EDEN_* line -> dict, or None if it is not a record."""
    line = line.strip()
    if not line.startswith("EDEN_"):
        return None
    tokens = line.split()
    marker = tokens[0]
    record = {"_marker": marker}
    for token in tokens[1:]:
        if "=" not in token:
            record.setdefault("_trailing", []).append(token)
            continue
        key, _, value = token.partition("=")
        if key == "cond":
            try:
                record[key] = [int(v) for v in value.split(",")]
            except ValueError:
                record[key] = value
        elif key.startswith("idle") and key[4:].isdigit():
            record[key] = parse_idle_triple(value)
        elif key == "ms":
            record[key] = parse_float_csv(value)
        else:
            record[key] = parse_value(key, value)
    required = REQUIRED.get(marker, ())
    missing = [k for k in required if k not in record]
    # EDEN_GPU_TIME has a failure form ("failed=ring") with no numbers.
    if marker == "EDEN_GPU_TIME" and "failed" in record:
        missing = []
    if marker == "EDEN_VULKAN_FRAMES" and isinstance(record.get("ms"), str):
        missing.append("ms-parse")
    record["complete"] = not missing
    if missing:
        record["_missing"] = missing
    return record


def collect(paths: list[str], run: str | None) -> int:
    """Import EDEN_* lines as JSONL records; returns the record count."""
    n_records = 0
    for path in paths:
        if path == "-":
            stream, name = sys.stdin, "<stdin>"
        else:
            stream, name = open(path, encoding="utf-8", errors="replace"), path
        with stream:
            for lineno, line in enumerate(stream, 1):
                if "EDEN_" not in line:
                    continue
                record = parse_line(line)
                if record is None:
                    continue
                record["_line"] = lineno
                record["_file"] = name
                record["_run"] = run or name
                print(json.dumps(record))
                n_records += 1
    print(f"collect: {n_records} records", file=sys.stderr)
    return n_records


def main(argv: list[str]) -> int:
    paths: list[str] = []
    run: str | None = None
    args = iter(argv[1:])
    for arg in args:
        if arg == "--run":
            try:
                run = next(args)
            except StopIteration:
                print("collect.py: --run needs a value", file=sys.stderr)
                return 2
        elif arg in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        else:
            paths.append(arg)
    collect(paths or ["-"], run)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
