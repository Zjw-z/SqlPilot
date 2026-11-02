from __future__ import annotations

import json
import itertools
import re
import sqlite3
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class SpiderCase:
    case_id: str
    db_id: str
    question: str
    gold_sql: str
    hardness: str = "unknown"


@dataclass
class SpiderCaseResult:
    case_id: str
    db_id: str
    hardness: str
    status: str
    execution_match: bool = False
    predicted_sql: str = ""
    error: str = ""
    elapsed_ms: int = 0


@dataclass
class SpiderReport:
    benchmark: str = "spider-1.0"
    total: int = 0
    evaluated: int = 0
    execution_matches: int = 0
    missing_predictions: int = 0
    missing_databases: int = 0
    execution_errors: int = 0
    by_hardness: dict[str, dict[str, int]] = field(default_factory=dict)
    cases: list[SpiderCaseResult] = field(default_factory=list)

    @property
    def execution_accuracy(self) -> float:
        return self.execution_matches / self.evaluated if self.evaluated else 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["execution_accuracy"] = round(self.execution_accuracy, 6)
        return data


class SpiderBenchmark:
    """Loads Spider 1.0 and evaluates result equivalence on its SQLite databases."""

    def __init__(self, dataset_dir: Path) -> None:
        self.dataset_dir = Path(dataset_dir)

    def load_cases(self, split: str = "dev") -> list[SpiderCase]:
        path = self._find_required(f"{split}.json")
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [SpiderCase(
            case_id=f"{split}-{index:04d}", db_id=row["db_id"],
            question=row["question"], gold_sql=row["query"],
            hardness=str(row.get("hardness") or self._infer_hardness(row["query"])),
        ) for index, row in enumerate(rows)]

    def load_schema(self) -> dict[str, dict[str, Any]]:
        rows = json.loads(self._find_required("tables.json").read_text(encoding="utf-8"))
        return {row["db_id"]: row for row in rows}

    def database_path(self, db_id: str) -> Path | None:
        candidates = list(self.dataset_dir.rglob(f"{db_id}.sqlite")) + list(self.dataset_dir.rglob(f"{db_id}.db"))
        return candidates[0] if candidates else None

    def readiness(self, split: str = "dev") -> dict[str, Any]:
        cases = self.load_cases(split)
        db_ids = sorted({case.db_id for case in cases})
        missing = [db_id for db_id in db_ids if self.database_path(db_id) is None]
        return {
            "benchmark": "spider-1.0", "split": split, "case_count": len(cases),
            "database_count": len(db_ids), "available_database_count": len(db_ids) - len(missing),
            "missing_databases": missing, "ready": not missing,
        }

    def evaluate(self, predictions: dict[str, str], split: str = "dev", limit: int | None = None,
                 only_predicted: bool = False) -> SpiderReport:
        cases = self.load_cases(split)
        if only_predicted:
            cases = [case for case in cases if case.case_id in predictions]
        cases = cases[:limit]
        report = SpiderReport(total=len(cases))
        buckets: dict[str, Counter] = {}
        for case in cases:
            predicted = predictions.get(case.case_id, "").strip()
            bucket = buckets.setdefault(case.hardness, Counter())
            if not predicted:
                report.missing_predictions += 1
                bucket["missing_prediction"] += 1
                report.cases.append(SpiderCaseResult(case.case_id, case.db_id, case.hardness, "missing_prediction"))
                continue
            database = self.database_path(case.db_id)
            if database is None:
                report.missing_databases += 1
                bucket["missing_database"] += 1
                report.cases.append(SpiderCaseResult(case.case_id, case.db_id, case.hardness, "missing_database", predicted_sql=predicted))
                continue
            started = time.perf_counter()
            try:
                gold_rows = self._execute(database, case.gold_sql)
                predicted_rows = self._execute(database, predicted)
                matched = self._equivalent(gold_rows, predicted_rows)
                report.evaluated += 1
                report.execution_matches += int(matched)
                bucket["evaluated"] += 1
                bucket["matched"] += int(matched)
                status = "matched" if matched else "result_mismatch"
                report.cases.append(SpiderCaseResult(case.case_id, case.db_id, case.hardness, status, matched, predicted, elapsed_ms=int((time.perf_counter()-started)*1000)))
            except (sqlite3.Error, ValueError) as exc:
                report.evaluated += 1
                report.execution_errors += 1
                bucket["evaluated"] += 1
                bucket["execution_error"] += 1
                report.cases.append(SpiderCaseResult(case.case_id, case.db_id, case.hardness, "execution_error", predicted_sql=predicted, error=str(exc)[:500], elapsed_ms=int((time.perf_counter()-started)*1000)))
        report.by_hardness = {key: dict(value) for key, value in sorted(buckets.items())}
        return report

    @staticmethod
    def load_predictions(path: Path) -> dict[str, str]:
        predictions: dict[str, str] = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            predictions[str(row["case_id"])] = str(row["sql"])
        return predictions

    @staticmethod
    def write_cases(path: Path, cases: Iterable[SpiderCase]) -> None:
        Path(path).write_text("\n".join(json.dumps(asdict(case), ensure_ascii=False) for case in cases) + "\n", encoding="utf-8")

    @staticmethod
    def _execute(database: Path, sql: str) -> list[tuple[Any, ...]]:
        if not sql.lstrip().lower().startswith(("select", "with")):
            raise ValueError("benchmark SQL must be read-only")
        uri = database.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            connection.text_factory = lambda raw: raw.decode("utf-8", errors="replace")
            connection.execute("PRAGMA query_only=ON")
            return connection.execute(sql).fetchall()

    @staticmethod
    def _infer_hardness(sql: str) -> str:
        normalized = " " + re.sub(r"\s+", " ", sql.lower()) + " "
        joins = normalized.count(" join ")
        nested = max(0, normalized.count(" select ") - 1)
        advanced = sum(token in normalized for token in (
            " group by ", " having ", " union ", " intersect ", " except ", " order by ",
        ))
        score = joins + nested * 2 + advanced
        if score == 0:
            return "easy"
        if score <= 2:
            return "medium"
        if score <= 4:
            return "hard"
        return "extra"

    @staticmethod
    def _equivalent(left: list[tuple[Any, ...]], right: list[tuple[Any, ...]]) -> bool:
        def normalize(rows: list[tuple[Any, ...]]) -> Counter:
            return Counter(tuple(SpiderBenchmark._normalize_value(v) for v in row) for row in rows)
        expected = normalize(left)
        if expected == normalize(right):
            return True
        if not left or not right or len(left[0]) != len(right[0]):
            return False
        width = len(left[0])
        if width > 6:
            return False
        for order in itertools.permutations(range(width)):
            reordered = [tuple(row[index] for index in order) for row in right]
            if expected == normalize(reordered):
                return True
        return False

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 6)
        return value

    def _find_required(self, filename: str) -> Path:
        matches = list(self.dataset_dir.rglob(filename))
        if not matches:
            raise FileNotFoundError(f"Spider file not found: {filename}")
        return matches[0]
