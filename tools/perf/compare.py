#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare baseline vs candidate statistics (from analyze.py).

Usage:
    python3 tools/perf/compare.py base.stats.json cand.stats.json
    python3 tools/perf/compare.py base.json cand.json --json report.json
    python3 tools/perf/compare.py --init-baseline run.stats.json baseline.json

Prints a Markdown report to stdout (or --markdown FILE) and optionally a
JSON report (--json FILE). Exit 0 on pass, 1 on regression,
3 when frame verdicts were blocked by overflow (inconclusive),
2 on usage/data errors. Verdicts live in compare_metrics.py; this
module owns the CLI and the report rendering. Stdlib only.
"""
import json
import sys
from collections.abc import Iterator

from compare_metrics import (
    TRIAGE_BAND_PCT,
    MetricResult,
    compare_reports,
    overall,
    windows_n,
)


def frames_line(tag: str, stats: dict) -> str:
    """One provenance line for a side's frame samples (H-01d)."""
    frames = stats.get("frame_samples")
    if not isinstance(frames, dict) or not frames.get("samples"):
        return f"- {tag} frames: none"
    return (f"- {tag} frames: {frames['samples']} samples, "
            f"{frames.get('windows', '?')} windows, "
            f"budgets {frames.get('budgets')}, "
            f"overflow {frames.get('overflow', 0)}, "
            f"partial {frames.get('partial', False)}")


def render_markdown(base_name: str, cand_name: str, base: dict, cand: dict,
                    results: list[MetricResult], band_pct: float) -> str:
    """Human-readable comparison report in Markdown."""
    lines = [
        "# perf comparison",
        "",
        f"- base: `{base_name}` ({windows_n(base)} windows, "
        f"{base.get('incomplete_excluded', '?')} incomplete excluded)",
        f"- candidate: `{cand_name}` ({windows_n(cand)} windows, "
        f"{cand.get('incomplete_excluded', '?')} incomplete excluded)",
        frames_line("base", base),
        frames_line("candidate", cand),
        f"- triage band: ±{band_pct:g}%",
        f"- overall: **{overall(results)}**",
        "",
        "| metric | base | candidate | change | verdict |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        base_text = fmt_value(result.base, result.unit)
        cand_text = fmt_value(result.cand, result.unit)
        change_text = "n/a" if result.change_pct is None else f"{result.change_pct:+.2f}%"
        note = f" ({result.detail})" if result.detail else ""
        lines.append(f"| {result.label} | {base_text} | {cand_text} | "
                     f"{change_text} | {result.outcome.value}{note} |")
    lines += [
        "",
        "Window fps/worst are window-level (5 s each) until PERF-FR-003 "
        "lands per-frame samples. Overlapping cumulative series are never "
        "summed; totals are compared per window.",
        "Frame intervals measure guest production cadence (GPU-thread "
        "Composite returns, skipped frames included via not_shown), not "
        "on-screen present intervals.",
    ]
    return "\n".join(lines) + "\n"


def fmt_value(value: float | None, unit: str) -> str:
    """Compact number with unit for the Markdown table."""
    if value is None:
        return "n/a"
    if unit == "bytes":
        scaled = value
        for suffix in ("B", "KiB", "MiB", "GiB"):
            if scaled < 1024 or suffix == "GiB":
                return f"{scaled:.2f} {suffix}"
            scaled /= 1024
    if unit == "fraction":
        return f"{value * 100:.1f}%"
    if abs(value) >= 1000:
        return f"{value:,.1f} {unit}"
    return f"{value:.3f} {unit}"


def render_json(base_name: str, cand_name: str,
                results: list[MetricResult]) -> str:
    """Machine-readable comparison report as JSON."""
    payload = {
        "base": base_name,
        "candidate": cand_name,
        "overall": overall(results),
        "metrics": [
            {"key": r.key, "label": r.label, "unit": r.unit,
             "base": r.base, "candidate": r.cand,
             "change_pct": r.change_pct, "verdict": r.outcome.value,
             "detail": r.detail, "blocked": r.blocked}
            for r in results
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def init_baseline(stats_path: str, out_path: str) -> int:
    """Validate a stats file and store it as a new baseline."""
    try:
        with open(stats_path, encoding="utf-8") as stream:
            stats = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"compare.py: cannot read {stats_path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(stats, dict) or windows_n(stats) <= 0:
        print(f"compare.py: {stats_path} has no counted windows",
              file=sys.stderr)
        return 2
    try:
        with open(out_path, "w", encoding="utf-8") as stream:
            json.dump(stats, stream, indent=2)
            stream.write("\n")
    except OSError as exc:
        print(f"compare.py: cannot write {out_path}: {exc}", file=sys.stderr)
        return 2
    print(f"compare.py: baseline has {windows_n(stats)} windows", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    """CLI: compare two stats files, or store a baseline."""
    markdown_path: str | None = None
    json_path: str | None = None
    band = TRIAGE_BAND_PCT
    positional: list[str] = []
    args = iter(argv[1:])
    for arg in args:
        if arg == "--markdown":
            markdown_path = next_arg(args, arg)
        elif arg == "--json":
            json_path = next_arg(args, arg)
        elif arg == "--triage-band":
            raw = next_arg(args, arg)
            try:
                band = float(raw)
            except ValueError:
                print(f"compare.py: bad --triage-band {raw!r}", file=sys.stderr)
                return 2
        elif arg == "--init-baseline":
            rest = list(args)
            if len(rest) != 2:
                print("compare.py: --init-baseline STATS OUT", file=sys.stderr)
                return 2
            return init_baseline(rest[0], rest[1])
        elif arg in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        elif arg.startswith("-"):
            print(f"compare.py: unknown flag {arg}", file=sys.stderr)
            return 2
        else:
            positional.append(arg)
    if len(positional) != 2:
        print("compare.py: need BASE CAND stats files", file=sys.stderr)
        return 2
    try:
        with open(positional[0], encoding="utf-8") as stream:
            base = json.load(stream)
        with open(positional[1], encoding="utf-8") as stream:
            cand = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"compare.py: {exc}", file=sys.stderr)
        return 2
    if not isinstance(base, dict) or not isinstance(cand, dict):
        print("compare.py: stats files must hold JSON objects", file=sys.stderr)
        return 2
    results = compare_reports(base, cand, band)
    markdown = render_markdown(positional[0], positional[1], base, cand,
                               results, band)
    if markdown_path is not None:
        try:
            with open(markdown_path, "w", encoding="utf-8") as stream:
                stream.write(markdown)
        except OSError as exc:
            print(f"compare.py: {exc}", file=sys.stderr)
            return 2
    else:
        print(markdown, end="")
    if json_path is not None:
        try:
            with open(json_path, "w", encoding="utf-8") as stream:
                stream.write(render_json(positional[0], positional[1], results))
        except OSError as exc:
            print(f"compare.py: {exc}", file=sys.stderr)
            return 2
    final = overall(results)
    if final == "regression":
        return 1
    return 3 if final == "inconclusive" else 0


def next_arg(args: Iterator[str], flag: str) -> str:
    """Next CLI value for flag, or exit 2 when missing."""
    try:
        return next(args)
    except StopIteration:
        print(f"compare.py: {flag} needs a value", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    sys.exit(main(sys.argv))
