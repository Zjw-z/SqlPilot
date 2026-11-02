from __future__ import annotations

import argparse
import json
from pathlib import Path


def matched_by_id(path: Path) -> dict[str, bool]:
    report = json.loads(path.read_text(encoding="utf-8"))
    return {str(case["case_id"]): bool(case.get("matched")) for case in report.get("cases", [])}


def build_sets(baseline: Path, candidate: Path) -> dict[str, list[str]]:
    old, new = matched_by_id(baseline), matched_by_id(candidate)
    ids = sorted(set(old) & set(new))
    return {
        "stable_correct": [case_id for case_id in ids if old[case_id] and new[case_id]],
        "fixed": [case_id for case_id in ids if not old[case_id] and new[case_id]],
        "regressed": [case_id for case_id in ids if old[case_id] and not new[case_id]],
        "persistent_failure": [case_id for case_id in ids if not old[case_id] and not new[case_id]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build stable Spider regression subsets from two reports")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    groups = build_sets(args.baseline, args.candidate)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, values in groups.items():
        (args.output_dir / f"{name}.txt").write_text("\n".join(values) + "\n", encoding="utf-8")
    (args.output_dir / "summary.json").write_text(
        json.dumps({name: len(values) for name, values in groups.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({name: len(values) for name, values in groups.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
