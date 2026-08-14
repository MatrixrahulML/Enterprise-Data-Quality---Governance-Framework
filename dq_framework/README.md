# Enterprise Data Quality & Governance Framework

A rules-based data quality engine that scans a SAP-style retail data warehouse
(customer master, product master, sales transactions) across **9 DQ dimensions**,
scores the data, and exports Power BI / Tableau-ready KPI tables.

Built to demonstrate the core competencies in a **Senior Data & AI Engineer**
job description: *data quality, governance, security & performance* across
SAP-sourced enterprise data, with BI-tool-ready outputs (Power BI / Tableau).

---

## What it does

```
01_generate_data.py       -> synthesizes a SAP-style star schema with realistic
                              dirty-data patterns injected on purpose
02_dq_engine.py            -> the reusable rule engine (9 DQ dimensions)
03_run_checks.py           -> wires 29 concrete rules to the 3 tables, runs them
04_build_dashboard_data.py -> rolls results up into dashboard KPIs + BI exports
reports/dq_dashboard.html  -> the visual Data Quality Console (open in a browser)
```

## Data model

| Table | Grain | Rows (sample) | SAP analog |
|---|---|---|---|
| `dim_customer` | 1 row / customer | 8,064 | Customer Master (KNA1) |
| `dim_product` | 1 row / SKU | 1,200 | Material Master (MARA) |
| `fact_sales` | 1 row / order line | 500,600 | Sales Order Items (VBAK/VBRP) |

The sample is scaled to represent an **18.4M-row production fact table**
(scale factor recorded in `data/_scale_metadata.txt` and applied
transparently in the KPI rollup — see `04_build_dashboard_data.py`).

## The 9 DQ dimensions implemented

| # | Dimension | Example rule in this project |
|---|---|---|
| 1 | Null checks | `customer_id` cannot be NULL |
| 2 | Duplicate checks | no duplicate `order_id`; no full-row duplicates |
| 3 | Data type checks | `quantity`, `sales_amount` must be numeric |
| 4 | Range checks | `sales_amount >= 0`; `discount_pct` in [0,100] |
| 5 | Referential integrity | `fact_sales.customer_id` must exist in `dim_customer` |
| 6 | Schema validation | approved column contract; `order_status` domain list |
| 7 | Business rules | `order_date <= current_date`; `unit_price >= unit_cost` |
| 8 | Freshness checks | records loaded within a 48h SLA window |
| 9 | Row-count checks | daily load volume within ±5% of baseline |

All 29 rules and their pass/fail results are in `reports/dq_rule_results.csv`.

## Scoring methodology

`DQRuleEngine.overall_score()` computes the **% of fact_sales records with
zero CRITICAL or HIGH severity defects** — a de-duplicated union across
rules (not a naive average of rule-level pass rates), because a single bad
row can trip multiple rules and shouldn't be double-counted.

`hard_failed_records()` reports the stricter subset: records with at least
one **CRITICAL** defect — the records that would block a production load.

This mirrors how real DQ scorecards are built (e.g. Informatica IDQ, SAP
Information Steward, Great Expectations Checkpoints) and is documented
inline in `02_dq_engine.py` for transparency in an interview setting.

## Dashboard KPIs (current run)

| KPI | Value |
|---|---|
| Data Quality Score | 95.6% |
| Total Records | 18.4M |
| Failed Records | 55.1K |
| Duplicate Rate | 0.12% |
| Freshness | 99.8% |
| Schema Violations | 14 |

Open `reports/dq_dashboard.html` directly in a browser — no server needed.

## BI-tool integration

`04_build_dashboard_data.py` writes flat, star-schema-friendly CSVs designed
to be dropped straight into **Power BI** or **Tableau** as a data source:

- `bi_fact_dq_kpi_summary.csv` — single row, card visuals
- `bi_fact_dq_by_dimension.csv` — bar chart: pass rate by DQ dimension
- `bi_fact_dq_by_severity.csv` — donut: rules by severity
- `bi_fact_dq_by_table.csv` — rollup by source table
- `bi_fact_dq_rule_results.csv` — full rule-level detail table/drill-through

## How to extend this for a real interview conversation

- **Add a rule**: call any `engine.check_*()` method in `03_run_checks.py`
  with a new `table`/`column`/`severity` — no engine changes needed.
- **Add a custom business rule**: `engine.check_business_rule()` takes any
  `df -> boolean Series` function, so domain logic isn't limited to the
  built-in dimensions.
- **Swap in real data**: point `load_table()` at any CSV with the same
  column names, or adapt to read from a SQL connection instead of pandas
  CSVs — the rule logic is dataframe-agnostic.
- **Talk about what you'd add for production**: incremental/streaming
  checks, a rule-config YAML instead of Python, alerting on SLA breach,
  a proper metadata-driven rule catalog (rules stored in a table, not code),
  and integration with SAP BODS job status for freshness checks.

## Run it yourself (macbook users need to use pip3 and python3 always)

`data/fact_sales.csv` is gzipped in this package to keep the download small
(~500K rows, ~50MB uncompressed). Regenerate it fresh (recommended — takes
~15 seconds and reproduces the exact same data via a fixed random seed), or
unzip the provided copy:

```bash
cd ~/Downloads

git clone https://github.com/MatrixrahulML/Enterprise-Data-Quality---Governance-Framework.git

cd Enterprise-Data-Quality---Governance-Framework/dq_framework

python3 -m venv venv
source venv/bin/activate

pip3 install pandas numpy

python3 src/01_generate_data.py
python3 src/03_run_checks.py
python3 src/04_build_dashboard_data.py

open reports/dq_dashboard.html
