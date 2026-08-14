"""
Enterprise Data Quality & Governance Framework
Step 4: Dashboard KPI Rollup + Power BI / Tableau Export Layer

Converts raw rule results into the exact KPI set requested:

  - Data Quality Score
  - Total Records
  - Failed Records
  - Duplicate Rate
  - Freshness
  - Schema Violations

Also scales the sample metrics up to the "production" 18.4M-row scale so
the numbers line up with an enterprise-scale narrative, and writes flat,
BI-tool-friendly CSVs (star-schema friendly, one row per grain) that can
be dropped straight into Power BI / Tableau as a data source.
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime

REPORTS_DIR = "/Users/macbook/Downloads/files/dq_framework/reports"
DATA_DIR = "/Users/macbook/Downloads/files/dq_framework/data"


def load_scale_factor():
    meta = {}
    with open(f"{DATA_DIR}/_scale_metadata.txt") as f:
        for line in f:
            k, v = line.strip().split("=")
            meta[k] = float(v)
    return meta


def main():
    with open(f"{REPORTS_DIR}/dq_rule_results.json") as f:
        payload = json.load(f)

    rules_df = pd.DataFrame(payload["rules"])
    meta = load_scale_factor()
    scale = meta["scale_factor"]

    # ------------------------------------------------------------------
    # KPI 1: Data Quality Score  (severity-weighted pass rate)
    # ------------------------------------------------------------------
    dq_score = payload["overall_score"]

    # ------------------------------------------------------------------
    # KPI 2: Total Records  (scaled to production volume)
    # ------------------------------------------------------------------
    fact_rows_sample = rules_df.loc[rules_df["table"] == "fact_sales", "records_checked"].max()
    total_records_production = int(round(fact_rows_sample * scale))

    # ------------------------------------------------------------------
    # KPI 3: Failed Records
    #   Distinct records with >=1 CRITICAL-severity defect (hard failures
    #   that would block a load), scaled to production volume. This is
    #   deliberately stricter than the DQ Score's CRITICAL+HIGH scope --
    #   it's the "must fix now" subset, not "everything imperfect".
    # ------------------------------------------------------------------
    sample_failed_distinct_est = payload["hard_failed_records"]
    failed_records_production = int(round(sample_failed_distinct_est * scale))

    # ------------------------------------------------------------------
    # KPI 4: Duplicate Rate
    # ------------------------------------------------------------------
    dup_rule = rules_df[rules_df["rule_id"] == "DUP_fact_sales_order_id"].iloc[0]
    duplicate_rate = round(100 * dup_rule["records_failed"] / dup_rule["records_checked"], 4)

    # ------------------------------------------------------------------
    # KPI 5: Freshness  (% of records within SLA)
    # ------------------------------------------------------------------
    fresh_rule = rules_df[rules_df["rule_id"] == "FRESH_fact_sales_48h_sla"].iloc[0]
    freshness_pct = round(fresh_rule["pass_rate"], 2)

    # ------------------------------------------------------------------
    # KPI 6: Schema Violations  (count, not %)
    # ------------------------------------------------------------------
    schema_rules = rules_df[rules_df["dimension"] == "Schema Validation"]
    schema_violations = int(schema_rules["records_failed"].sum())

    kpis = {
        "generated_at": datetime.now().isoformat(),
        "data_quality_score_pct": dq_score,
        "total_records": total_records_production,
        "failed_records": failed_records_production,
        "duplicate_rate_pct": duplicate_rate,
        "freshness_pct": freshness_pct,
        "schema_violations": schema_violations,
        "sample_size_analyzed": int(fact_rows_sample),
        "scale_factor_applied": round(scale, 2),
    }

    with open(f"{REPORTS_DIR}/dashboard_kpis.json", "w") as f:
        json.dump(kpis, f, indent=2)

    # ------------------------------------------------------------------
    # BI-ready exports
    # ------------------------------------------------------------------
    # 1. Rule-level results (Power BI table: fact_dq_rule_results)
    rules_df.to_csv(f"{REPORTS_DIR}/bi_fact_dq_rule_results.csv", index=False)

    # 2. Dimension-level rollup (Power BI table: fact_dq_by_dimension)
    dim_rollup = rules_df.groupby("dimension").agg(
        rules_total=("rule_id", "count"),
        rules_failed=("status", lambda s: (s == "FAIL").sum()),
        records_checked=("records_checked", "sum"),
        records_failed=("records_failed", "sum"),
    ).reset_index()
    dim_rollup["avg_pass_rate"] = rules_df.groupby("dimension")["pass_rate"].mean().values.round(2)
    dim_rollup.to_csv(f"{REPORTS_DIR}/bi_fact_dq_by_dimension.csv", index=False)

    # 3. Table-level rollup (Power BI table: fact_dq_by_table)
    table_rollup = rules_df.groupby("table").agg(
        rules_total=("rule_id", "count"),
        rules_failed=("status", lambda s: (s == "FAIL").sum()),
        records_checked=("records_checked", "max"),
        records_failed=("records_failed", "sum"),
    ).reset_index()
    table_rollup.to_csv(f"{REPORTS_DIR}/bi_fact_dq_by_table.csv", index=False)

    # 4. Single-row KPI summary (Power BI card visuals: fact_dq_kpi_summary)
    pd.DataFrame([kpis]).to_csv(f"{REPORTS_DIR}/bi_fact_dq_kpi_summary.csv", index=False)

    # 5. Severity breakdown (for a severity donut/bar chart)
    sev_rollup = rules_df.groupby("severity").agg(
        rules_total=("rule_id", "count"),
        rules_failed=("status", lambda s: (s == "FAIL").sum()),
    ).reset_index()
    sev_rollup.to_csv(f"{REPORTS_DIR}/bi_fact_dq_by_severity.csv", index=False)

    print("KPI Summary")
    print("=" * 50)
    for k, v in kpis.items():
        print(f"  {k:28s}: {v}")

    print("\nBI export files written to:", REPORTS_DIR)
    for fn in ["bi_fact_dq_rule_results.csv", "bi_fact_dq_by_dimension.csv",
               "bi_fact_dq_by_table.csv", "bi_fact_dq_kpi_summary.csv",
               "bi_fact_dq_by_severity.csv"]:
        print(f"  - {fn}")

    return kpis


if __name__ == "__main__":
    main()
