"""
Enterprise Data Quality & Governance Framework
Step 2: Data Quality Rules Engine

A configurable, extensible rule engine that runs the 9 core DQ dimensions
against enterprise datasets:

  1. NULL checks              - mandatory fields must be populated
  2. Duplicate checks         - full-row and key-based duplication
  3. Data type checks         - column values conform to expected dtype
  4. Range checks             - numeric values fall within valid bounds
  5. Referential integrity    - FK values exist in the referenced dimension
  6. Schema validation        - columns/values match the approved schema
  7. Business rules           - domain-specific logic (e.g. order_date <= today)
  8. Freshness checks         - data loaded within SLA window
  9. Row-count checks         - volume anomaly detection vs. expected baseline

Design mirrors patterns used in Great Expectations / SAP DQM / Informatica
IDQ, but implemented from scratch in pandas so it's transparent and
portable (no external DQ platform license required).

Each rule returns a RuleResult with:
  - rule_id, dimension, severity
  - records_checked, records_failed
  - failed_row_indices (for drill-down/export)
  - pass_rate
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Callable
import json

DATA_DIR = "/Users/macbook/Downloads/files/dq_framework/data"
REPORTS_DIR = "/Users/macbook/Downloads/files/dq_framework/reports"



# CORE DATA STRUCTURES

@dataclass
class RuleResult:
    rule_id: str
    dimension: str
    description: str
    table: str
    column: Optional[str]
    severity: str                 # CRITICAL / HIGH / MEDIUM / LOW
    records_checked: int
    records_failed: int
    failed_indices: list = field(default_factory=list)

    @property
    def pass_rate(self):
        if self.records_checked == 0:
            return 100.0
        return round(100 * (1 - self.records_failed / self.records_checked), 4)

    @property
    def status(self):
        return "PASS" if self.records_failed == 0 else "FAIL"

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "dimension": self.dimension,
            "description": self.description,
            "table": self.table,
            "column": self.column,
            "severity": self.severity,
            "records_checked": self.records_checked,
            "records_failed": self.records_failed,
            "pass_rate": self.pass_rate,
            "status": self.status,
        }


class DQRuleEngine:
    def __init__(self):
        self.results: List[RuleResult] = []
        self.tables = {}

    def load_table(self, name, path, parse_dates=None):
        df = pd.read_csv(path)
        self.tables[name] = df
        return df

    def _add(self, result: RuleResult):
        self.results.append(result)

   
    # 1. NULL CHECKS
    
    def check_not_null(self, table, column, severity="CRITICAL", rule_id=None):
        df = self.tables[table]
        failed = df[df[column].isna()]
        r = RuleResult(
            rule_id=rule_id or f"NULL_{table}_{column}",
            dimension="Null Check",
            description=f"{table}.{column} must not be NULL",
            table=table, column=column, severity=severity,
            records_checked=len(df), records_failed=len(failed),
            failed_indices=failed.index.tolist(),
        )
        self._add(r)
        return r

   
    # 2. DUPLICATE CHECKS
    
    def check_duplicates(self, table, subset=None, severity="HIGH", rule_id=None):
        df = self.tables[table]
        dup_mask = df.duplicated(subset=subset, keep="first")
        failed = df[dup_mask]
        cols_label = ", ".join(subset) if subset else "all columns"
        r = RuleResult(
            rule_id=rule_id or f"DUP_{table}_{'_'.join(subset) if subset else 'ALL'}",
            dimension="Duplicate Check",
            description=f"{table}: no duplicate records on [{cols_label}]",
            table=table, column=",".join(subset) if subset else None,
            severity=severity,
            records_checked=len(df), records_failed=len(failed),
            failed_indices=failed.index.tolist(),
        )
        self._add(r)
        return r

    # -----------------------------------------------------------------
    # 3. DATA TYPE CHECKS
    # -----------------------------------------------------------------
    def check_data_type(self, table, column, expected_type, severity="HIGH", rule_id=None):
        """expected_type: 'numeric', 'int', 'date', 'string'"""
        df = self.tables[table]
        col = df[column]

        if expected_type in ("numeric", "int", "float"):
            coerced = pd.to_numeric(col, errors="coerce")
            failed_mask = coerced.isna() & col.notna()
        elif expected_type == "date":
            coerced = pd.to_datetime(col, errors="coerce")
            failed_mask = coerced.isna() & col.notna()
        else:  # string - basically always passes unless null, skip
            failed_mask = pd.Series([False] * len(df))

        failed = df[failed_mask]
        r = RuleResult(
            rule_id=rule_id or f"TYPE_{table}_{column}",
            dimension="Data Type Check",
            description=f"{table}.{column} must be valid {expected_type}",
            table=table, column=column, severity=severity,
            records_checked=len(df), records_failed=len(failed),
            failed_indices=failed.index.tolist(),
        )
        self._add(r)
        return r

    # -----------------------------------------------------------------
    # 4. RANGE CHECKS
    # -----------------------------------------------------------------
    def check_range(self, table, column, min_val=None, max_val=None,
                     severity="HIGH", rule_id=None):
        df = self.tables[table]
        numeric_col = pd.to_numeric(df[column], errors="coerce")
        mask = pd.Series([False] * len(df), index=df.index)
        if min_val is not None:
            mask |= (numeric_col < min_val)
        if max_val is not None:
            mask |= (numeric_col > max_val)
        failed = df[mask & numeric_col.notna()]

        bounds = []
        if min_val is not None:
            bounds.append(f">= {min_val}")
        if max_val is not None:
            bounds.append(f"<= {max_val}")
        r = RuleResult(
            rule_id=rule_id or f"RANGE_{table}_{column}",
            dimension="Range Check",
            description=f"{table}.{column} must be {' and '.join(bounds)}",
            table=table, column=column, severity=severity,
            records_checked=len(df), records_failed=len(failed),
            failed_indices=failed.index.tolist(),
        )
        self._add(r)
        return r

    # -----------------------------------------------------------------
    # 5. REFERENTIAL INTEGRITY
    # -----------------------------------------------------------------
    def check_referential_integrity(self, table, column, ref_table, ref_column,
                                     severity="CRITICAL", rule_id=None):
        df = self.tables[table]
        ref_values = set(self.tables[ref_table][ref_column].dropna().unique())
        mask = df[column].notna() & ~df[column].isin(ref_values)
        failed = df[mask]
        r = RuleResult(
            rule_id=rule_id or f"REFINT_{table}_{column}",
            dimension="Referential Integrity",
            description=f"{table}.{column} must exist in {ref_table}.{ref_column}",
            table=table, column=column, severity=severity,
            records_checked=len(df), records_failed=len(failed),
            failed_indices=failed.index.tolist(),
        )
        self._add(r)
        return r

    # -----------------------------------------------------------------
    # 6. SCHEMA VALIDATION
    # -----------------------------------------------------------------
    def check_schema(self, table, expected_columns, severity="CRITICAL", rule_id=None):
        df = self.tables[table]
        actual = list(df.columns)
        missing = [c for c in expected_columns if c not in actual]
        extra = [c for c in actual if c not in expected_columns]
        failed_count = len(missing) + len(extra)
        r = RuleResult(
            rule_id=rule_id or f"SCHEMA_{table}",
            dimension="Schema Validation",
            description=f"{table} schema matches approved contract "
                        f"(missing={missing}, unexpected={extra})",
            table=table, column=None, severity=severity,
            records_checked=len(expected_columns),
            records_failed=failed_count,
            failed_indices=[],
        )
        self._add(r)
        return r

    def check_allowed_values(self, table, column, allowed_values, severity="MEDIUM", rule_id=None):
        """Schema/domain validation: column values must be within an approved value set."""
        df = self.tables[table]
        mask = df[column].notna() & ~df[column].isin(allowed_values)
        failed = df[mask]
        r = RuleResult(
            rule_id=rule_id or f"DOMAIN_{table}_{column}",
            dimension="Schema Validation",
            description=f"{table}.{column} must be one of {allowed_values}",
            table=table, column=column, severity=severity,
            records_checked=len(df), records_failed=len(failed),
            failed_indices=failed.index.tolist(),
        )
        self._add(r)
        return r

    # -----------------------------------------------------------------
    # 7. BUSINESS RULES (custom logic via lambda/callable)
    # -----------------------------------------------------------------
    def check_business_rule(self, table, rule_id, description, condition_fn,
                             severity="HIGH"):
        """condition_fn(df) -> boolean Series where True = VALID row"""
        df = self.tables[table]
        valid_mask = condition_fn(df)
        failed = df[~valid_mask]
        r = RuleResult(
            rule_id=rule_id,
            dimension="Business Rule",
            description=description,
            table=table, column=None, severity=severity,
            records_checked=len(df), records_failed=len(failed),
            failed_indices=failed.index.tolist(),
        )
        self._add(r)
        return r

    # ---------------------------------------------------------------
    # 8. FRESHNESS CHECKS
    # -------------------------------------------------------------
    def check_freshness(self, table, timestamp_column, sla_hours=24,
                         severity="MEDIUM", rule_id=None):
        df = self.tables[table]
        ts = pd.to_datetime(df[timestamp_column], errors="coerce")
        now = datetime.now()
        age_hours = (now - ts).dt.total_seconds() / 3600
        mask = age_hours > sla_hours
        failed = df[mask.fillna(False)]
        r = RuleResult(
            rule_id=rule_id or f"FRESH_{table}_{timestamp_column}",
            dimension="Freshness Check",
            description=f"{table}.{timestamp_column} must be loaded within {sla_hours}h SLA",
            table=table, column=timestamp_column, severity=severity,
            records_checked=len(df), records_failed=len(failed),
            failed_indices=failed.index.tolist(),
        )
        self._add(r)
        return r

    # ------------------------------------------------------------
    # 9. ROW-COUNT / VOLUME CHECKS
    # -----------------------------------------------------------------
    def check_row_count(self, table, expected_min, expected_max=None,
                         severity="MEDIUM", rule_id=None):
        df = self.tables[table]
        n = len(df)
        failed = 0
        if n < expected_min:
            failed = expected_min - n
        elif expected_max is not None and n > expected_max:
            failed = n - expected_max
        r = RuleResult(
            rule_id=rule_id or f"VOLUME_{table}",
            dimension="Row Count Check",
            description=f"{table} row count must be within "
                        f"[{expected_min:,}, {expected_max:,}]" if expected_max
                        else f"{table} row count must be >= {expected_min:,}",
            table=table, column=None, severity=severity,
            records_checked=1, records_failed=(1 if failed else 0),
            failed_indices=[],
        )
        r.actual_count = n  # extra attribute for reporting
        self._add(r)
        return r

    # -----------------------------------------------------------
    # SUMMARY / EXPORT
    # ---------------------------------------------------------------
    def summary_df(self):
        return pd.DataFrame([r.to_dict() for r in self.results])

    def overall_score(self, table=None, primary_table="fact_sales"):
        """
        DQ Score = % of records in the primary fact table that pass EVERY
        applicable row-level rule (the "clean record" definition used by
        most enterprise DQ scorecards -- a record with even one CRITICAL
        or HIGH defect is not counted as a good record).

        This is computed directly from row-level failed_indices (a proper
        union across rules), not by averaging rule-level pass rates, so
        overlapping failures on the same row are correctly de-duplicated
        without over- or under-counting.
        """
        target_table = table or primary_table
        bad_rows = set()
        total = None
        for r in self.results:
            if r.table != target_table or r.records_checked <= 1:
                continue
            if r.severity in ("CRITICAL", "HIGH"):
                bad_rows.update(r.failed_indices)
            total = r.records_checked
        if not total:
            return 100.0
        clean = total - len(bad_rows)
        return round(100 * clean / total, 2)

    def hard_failed_records(self, table=None, primary_table="fact_sales"):
        """
        'Failed Records' KPI = distinct records with at least one CRITICAL
        severity defect only (the subset that would block a load / trigger
        a pipeline failure in production, as opposed to every record with
        any defect of any severity). This is the standard, stricter
        definition most DQ scorecards surface on the headline KPI tile.
        """
        target_table = table or primary_table
        bad_rows = set()
        for r in self.results:
            if r.table != target_table or r.records_checked <= 1:
                continue
            if r.severity == "CRITICAL":
                bad_rows.update(r.failed_indices)
        return len(bad_rows)

    def export_json(self, path):
        payload = {
            "generated_at": datetime.now().isoformat(),
            "overall_score": self.overall_score(),
            "hard_failed_records": self.hard_failed_records(),
            "rules": [r.to_dict() for r in self.results],
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        return payload
