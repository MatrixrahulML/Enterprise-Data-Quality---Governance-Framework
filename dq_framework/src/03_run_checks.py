"""
Enterprise Data Quality & Governance Framework
Step 3: Rule Configuration & Execution

Wires up the DQRuleEngine against dim_customer, dim_product, and
fact_sales, applying all 9 DQ dimensions. This is the file you'd point
to in an interview to show concrete, named business rules -- e.g.:

    - Customer ID cannot be NULL
    - Sales amount >= 0
    - Order date <= current date
    - Customer ID must exist in customer dimension
"""

import sys
sys.path.insert(0, "/Users/macbook/Downloads/files/dq_framework/src")
import importlib.util
spec = importlib.util.spec_from_file_location("dq_engine", "/Users/macbook/Downloads/files/dq_framework/src/02_dq_engine.py")
dq_engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dq_engine)
DQRuleEngine = dq_engine.DQRuleEngine

import pandas as pd
from datetime import datetime

DATA_DIR = "/Users/macbook/Downloads/files/dq_framework/data"
REPORTS_DIR = "/Users/macbook/Downloads/files/dq_framework/reports"


def main():
    engine = DQRuleEngine()

    customers = engine.load_table("dim_customer", f"{DATA_DIR}/dim_customer.csv")
    products = engine.load_table("dim_product", f"{DATA_DIR}/dim_product.csv")
    sales = engine.load_table("fact_sales", f"{DATA_DIR}/fact_sales.csv")

    print(f"Loaded dim_customer: {len(customers):,} rows")
    print(f"Loaded dim_product:  {len(products):,} rows")
    print(f"Loaded fact_sales:   {len(sales):,} rows")
    print("\nRunning data quality checks...\n")

    # =====================================================================
    # SCHEMA VALIDATION
    # =============================================================
    engine.check_schema("dim_customer", [
        "customer_id", "first_name", "last_name", "email", "country",
        "segment", "signup_date", "credit_limit", "active_flag"
    ])
    engine.check_schema("dim_product", [
        "product_id", "product_name", "category", "unit_cost", "unit_price",
        "weight_kg", "active_flag", "created_date"
    ])
    engine.check_schema("fact_sales", [
        "order_id", "customer_id", "product_id", "order_date", "quantity",
        "unit_price", "sales_amount", "discount_pct", "order_status",
        "currency", "region", "load_timestamp"
    ])
    engine.check_allowed_values(
        "fact_sales", "order_status",
        ["Completed", "Shipped", "Pending", "Cancelled", "Returned"],
        severity="MEDIUM", rule_id="SCHEMA_order_status_domain"
    )

    # =================================================================
    # NULL CHECKS
    # =====================================================================
    engine.check_not_null("fact_sales", "customer_id", severity="CRITICAL",
                           rule_id="NULL_customer_id")           # <- "Customer ID cannot be NULL"
    engine.check_not_null("fact_sales", "product_id", severity="CRITICAL")
    engine.check_not_null("fact_sales", "order_date", severity="CRITICAL")
    engine.check_not_null("dim_customer", "email", severity="MEDIUM")
    engine.check_not_null("dim_customer", "last_name", severity="MEDIUM")
    engine.check_not_null("dim_product", "category", severity="HIGH")

    # ==============================================================
    # DUPLICATE CHECKS
    # =====================================================================
    engine.check_duplicates("fact_sales", subset=None, severity="HIGH",
                             rule_id="DUP_fact_sales_full_row")
    engine.check_duplicates("fact_sales", subset=["order_id"], severity="CRITICAL",
                             rule_id="DUP_fact_sales_order_id")
    engine.check_duplicates("dim_customer", subset=["customer_id"], severity="HIGH",
                             rule_id="DUP_dim_customer_id")

    # =====================================================================
    # DATA TYPE CHECKS
    # ===========================================================
    engine.check_data_type("fact_sales", "quantity", "numeric", severity="HIGH")
    engine.check_data_type("fact_sales", "sales_amount", "numeric", severity="HIGH")
    engine.check_data_type("fact_sales", "order_date", "date", severity="HIGH")
    engine.check_data_type("dim_customer", "signup_date", "date", severity="MEDIUM")

    # ================================================================
    # RANGE CHECKS
    # =====================================================================
    engine.check_range("fact_sales", "sales_amount", min_val=0, severity="CRITICAL",
                        rule_id="RANGE_sales_amount_nonneg")     # <- "Sales amount >= 0"
    engine.check_range("fact_sales", "quantity", min_val=1, severity="HIGH")
    engine.check_range("fact_sales", "discount_pct", min_val=0, max_val=100, severity="MEDIUM")
    engine.check_range("dim_customer", "credit_limit", min_val=0, severity="HIGH")
    engine.check_range("dim_product", "weight_kg", min_val=0, severity="MEDIUM")

    # ==========================================================
    # REFERENTIAL INTEGRITY
    # ==================================================================
    engine.check_referential_integrity(
        "fact_sales", "customer_id", "dim_customer", "customer_id",
        severity="CRITICAL", rule_id="REFINT_customer_id"
    )   # <- "Customer ID must exist in customer dimension"
    engine.check_referential_integrity(
        "fact_sales", "product_id", "dim_product", "product_id",
        severity="CRITICAL", rule_id="REFINT_product_id"
    )

    # ============================================================
    # BUSINESS RULES
    # ===============================================================
    today = pd.Timestamp(datetime.now().date())

    def order_date_not_future(df):
        d = pd.to_datetime(df["order_date"], errors="coerce")
        return d.notna() & (d <= today)

    engine.check_business_rule(
        "fact_sales", "BIZ_order_date_not_future",
        "order_date must be <= current date",
        order_date_not_future, severity="HIGH"
    )   # <- "Order date <= current date"

    def price_covers_cost(df):
        # business rule: unit_price should not be below unit_cost (would be a loss)
        return pd.Series([True] * len(df), index=df.index)  # placeholder, evaluated on product table below

    def product_margin_positive(df):
        return df["unit_price"] >= df["unit_cost"]

    engine.check_business_rule(
        "dim_product", "BIZ_positive_margin",
        "unit_price must be >= unit_cost (no negative margin)",
        product_margin_positive, severity="MEDIUM"
    )

    def credit_limit_positive(df):
        return df["credit_limit"] >= 0

    engine.check_business_rule(
        "dim_customer", "BIZ_credit_limit_nonneg",
        "credit_limit must be >= 0",
        credit_limit_positive, severity="HIGH"
    )

    # =====================================================================
    # FRESHNESS CHECKS
    # =====================================================================
    engine.check_freshness("fact_sales", "load_timestamp", sla_hours=48,
                            severity="MEDIUM", rule_id="FRESH_fact_sales_48h_sla")

    # =====================================================================
    # ROW-COUNT / VOLUME CHECKS
    # =====================================================================
    engine.check_row_count("fact_sales", expected_min=int(len(sales) * 0.95),
                            expected_max=int(len(sales) * 1.05),
                            severity="LOW", rule_id="VOLUME_fact_sales_daily_load")

    # =====================================================================
    # OUTPUT
    # =====================================================================
    summary = engine.summary_df()
    summary.to_csv(f"{REPORTS_DIR}/dq_rule_results.csv", index=False)
    payload = engine.export_json(f"{REPORTS_DIR}/dq_rule_results.json")

    print(summary.to_string(index=False))
    print(f"\n{'='*70}")
    print(f"OVERALL DATA QUALITY SCORE: {engine.overall_score()}%")
    print(f"{'='*70}")

    n_failed_rules = (summary["status"] == "FAIL").sum()
    print(f"\nRules executed: {len(summary)}")
    print(f"Rules failed:   {n_failed_rules}")
    print(f"Total records failed (sum across rules): {summary['records_failed'].sum():,}")

    return engine


if __name__ == "__main__":
    main()
