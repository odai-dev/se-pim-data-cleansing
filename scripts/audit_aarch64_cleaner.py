#!/usr/bin/env python3
"""Fail if AArch64 feature repair contains data-dependent control flow."""

import argparse
import hashlib
import json
import re
from pathlib import Path


FUNCTION_START = "pim_clean_oblivious:"
FUNCTION_END = ".size\tpim_clean_oblivious"
SOURCE_LINE = re.compile(r"pim_cleaner\.c:(\d+):")
BRANCH = re.compile(r"^\s*(b(?:\.[a-z]+|[a-z]{2})?|cbnz|cbz|tbnz|tbz)\s")
SECRET_SOURCE_LINES = {417, 440, 443} | set(range(419, 425)) | set(range(429, 434))


def main():
    parser = argparse.ArgumentParser(description="Audit PIM cleaner AArch64 assembly")
    parser.add_argument("assembly", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    text = args.assembly.read_text()
    start = text.find(FUNCTION_START)
    end = text.find(FUNCTION_END, start)
    if start < 0 or end < 0:
        raise SystemExit("pim_clean_oblivious function not found in assembly")

    function = text[start:end]
    current_line = None
    forbidden = []
    branch_inventory = []
    for line in function.splitlines():
        source_match = SOURCE_LINE.search(line)
        if source_match:
            current_line = int(source_match.group(1))
        branch_match = BRANCH.match(line)
        if branch_match:
            item = {"source_line": current_line, "instruction": line.strip()}
            branch_inventory.append(item)
            if current_line in SECRET_SOURCE_LINES:
                forbidden.append(item)

    required_instructions = {
        "floating_compare_mask": "fcmgt" in function,
        "integer_mask_select": "\tand\t" in function and "\teor\t" in function,
        "conditional_select_for_empty_mean": "\tcsel\t" in function,
    }
    passed = not forbidden and all(required_instructions.values())
    report = {
        "schema_version": 1,
        "assembly": str(args.assembly),
        "assembly_sha256": hashlib.sha256(args.assembly.read_bytes()).hexdigest(),
        "function": "pim_clean_oblivious",
        "secret_source_lines": sorted(SECRET_SOURCE_LINES),
        "forbidden_secret_dependent_branches": forbidden,
        "required_mask_instructions": required_instructions,
        "branch_inventory": branch_inventory,
        "result": "pass" if passed else "fail",
        "scope": (
            "Checks generated control flow for the per-feature validity and repair expressions; "
            "public allocation, policy, record-count, and dimension branches are outside scope."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    if not passed:
        raise SystemExit(f"assembly audit failed: {forbidden or required_instructions}")
    print(f"[PASS] no secret-dependent feature branch; report={args.report}")


if __name__ == "__main__":
    main()
