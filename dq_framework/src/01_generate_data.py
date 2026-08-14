"""
Enterprise Data Quality & Governance Framework
Step 1: Synthetic Data Generator

Simulates a SAP-style retail enterprise data warehouse:
  - dim_customer   (customer master data, ~SAP CMD-style)
  - dim_product    (product master data, ~SAP MARA-style)
  - fact_sales     (sales transactions, ~SAP VBAK/VBRP-style)

Intentionally injects realistic dirty-data patterns (nulls, duplicates,
bad types, out-of-range values, orphaned foreign keys, stale records,
schema drift) so the DQ engine has real issues to catch.

Target scale mirrors the dashboard KPIs (~18.4M fact rows would take too
long/large for a demo environment, so we generate a representative sample
at configurable scale and the DQ report extrapolates/labels accordingly).
"""

import pandas as pd
import numpy as np
import random
import string
from datetime import datetime, timedelta


# CONFIG

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

N_CUSTOMERS = 8_000
N_PRODUCTS = 1_200
N_SALES = 500_000          # sampled fact table (full framework scales linearly)
FULL_SCALE_ROWS = 18_400_000  # the "production" row count we report against

OUT_DIR = "/Users/macbook/Downloads/files/dq_framework/data"

FIRST_NAMES = ["James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda",
    "William","Elizabeth","David","Barbara","Richard","Susan","Joseph","Jessica",
    "Thomas","Sarah","Charles","Karen","Ahmed","Fatima","Wei","Mei","Raj","Priya",
    "Carlos","Sofia","Hans","Ingrid","Yuki","Sakura","Omar","Layla","Liam","Olivia"]
LAST_NAMES = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas",
    "Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson","White","Harris","Sanchez",
    "Clark","Ramirez","Lewis","Robinson","Walker","Young","Allen","King","Wright","Scott"]
COUNTRIES = ["USA","Canada","UK","Germany","France","UAE","India","China","Japan","Brazil",
    "Australia","Mexico","Saudi Arabia","Singapore","South Africa"]
SEGMENTS = ["Retail","Wholesale","E-Commerce","Corporate","VIP"]
PRODUCT_CATEGORIES = ["Electronics","Apparel","Home & Garden","Grocery","Beauty",
    "Sports","Toys","Automotive","Books","Furniture"]
CURRENCIES = ["USD","EUR","GBP","AED","INR","JPY"]
ORDER_STATUS = ["Completed","Shipped","Pending","Cancelled","Returned"]


def rand_date(start_year=2021, end_year=2026):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 8, 12)
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))


def make_sap_customer_id(i):
    # SAP-style zero-padded numeric customer master ID
    return f"CUST{str(i).zfill(7)}"


def make_sap_material_id(i):
    return f"MAT{str(i).zfill(6)}"


def make_sap_order_id(i):
    return f"SO{str(i).zfill(9)}"



# DIM_CUSTOMER

def generate_customers(n):
    rows = []
    for i in range(1, n + 1):
        cid = make_sap_customer_id(i)
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        email = f"{first.lower()}.{last.lower()}{random.randint(1,999)}@{'example.com'}"
        country = random.choice(COUNTRIES)
        segment = random.choice(SEGMENTS)
        signup_date = rand_date(2018, 2026)
        credit_limit = round(np.random.exponential(scale=5000) + 500, 2)
        active_flag = random.choices(["Y", "N"], weights=[0.9, 0.1])[0]

        rows.append([cid, first, last, email, country, segment,
                     signup_date.strftime("%Y-%m-%d"), credit_limit, active_flag])

    df = pd.DataFrame(rows, columns=[
        "customer_id", "first_name", "last_name", "email", "country",
        "segment", "signup_date", "credit_limit", "active_flag"
    ])

    # ---- inject dirty data ----
    n_dirty = int(n * 0.03)
    dirty_idx = np.random.choice(df.index, n_dirty, replace=False)

    # NULL emails / missing last names
    df.loc[dirty_idx[:len(dirty_idx)//3], "email"] = None
    df.loc[dirty_idx[len(dirty_idx)//3: 2*len(dirty_idx)//3], "last_name"] = None

    # duplicate customer records (same customer, re-inserted with new surrogate row)
    dup_sample = df.sample(int(n * 0.008), random_state=1).copy()
    df = pd.concat([df, dup_sample], ignore_index=True)

    # bad/negative credit limits
    bad_credit_idx = np.random.choice(df.index, int(n * 0.005), replace=False)
    df.loc[bad_credit_idx, "credit_limit"] = -abs(df.loc[bad_credit_idx, "credit_limit"])

    # malformed emails (schema/format violation)
    malformed_idx = np.random.choice(df.dropna(subset=["email"]).index, int(n*0.004), replace=False)
    df.loc[malformed_idx, "email"] = "not_an_email"

    return df



# DIM_PRODUCT

def generate_products(n):
    rows = []
    for i in range(1, n + 1):
        pid = make_sap_material_id(i)
        category = random.choice(PRODUCT_CATEGORIES)
        name = f"{category[:4].upper()}-{''.join(random.choices(string.ascii_uppercase, k=3))}-{i}"
        unit_cost = round(np.random.uniform(1, 500), 2)
        unit_price = round(unit_cost * np.random.uniform(1.2, 2.5), 2)
        weight_kg = round(np.random.uniform(0.05, 40), 2)
        active_flag = random.choices(["Y", "N"], weights=[0.93, 0.07])[0]
        created_date = rand_date(2015, 2026)
        rows.append([pid, name, category, unit_cost, unit_price, weight_kg,
                     active_flag, created_date.strftime("%Y-%m-%d")])

    df = pd.DataFrame(rows, columns=[
        "product_id", "product_name", "category", "unit_cost", "unit_price",
        "weight_kg", "active_flag", "created_date"
    ])

    # ---- inject dirty data ----
    # missing category (schema/business rule violation)
    idx = np.random.choice(df.index, int(n * 0.01), replace=False)
    df.loc[idx, "category"] = None

    # price < cost (business rule violation -> negative margin)
    idx2 = np.random.choice(df.index, int(n * 0.006), replace=False)
    df.loc[idx2, "unit_price"] = df.loc[idx2, "unit_cost"] * 0.5

    # zero/negative weight (range violation)
    idx3 = np.random.choice(df.index, int(n * 0.003), replace=False)
    df.loc[idx3, "weight_kg"] = -1.0

    return df



# FACT_SALES

def generate_sales(n, customer_ids, product_ids):
    rows = []
    for i in range(1, n + 1):
        order_id = make_sap_order_id(i)
        cust = random.choice(customer_ids)
        prod = random.choice(product_ids)
        order_date = rand_date(2023, 2026)
        qty = random.randint(1, 25)
        unit_price = round(np.random.uniform(5, 900), 2)
        sales_amount = round(qty * unit_price, 2)
        discount_pct = round(random.choice([0, 0, 0, 5, 10, 15, 20]), 2)
        status = random.choices(ORDER_STATUS, weights=[0.65, 0.15, 0.1, 0.06, 0.04])[0]
        currency = random.choices(CURRENCIES, weights=[0.55,0.15,0.1,0.08,0.07,0.05])[0]
        region = random.choice(COUNTRIES)
        load_ts = datetime.now() - timedelta(hours=random.randint(0, 30))

        rows.append([order_id, cust, prod, order_date.strftime("%Y-%m-%d"), qty,
                     unit_price, sales_amount, discount_pct, status, currency,
                     region, load_ts.strftime("%Y-%m-%d %H:%M:%S")])

    df = pd.DataFrame(rows, columns=[
        "order_id", "customer_id", "product_id", "order_date", "quantity",
        "unit_price", "sales_amount", "discount_pct", "order_status",
        "currency", "region", "load_timestamp"
    ])

    # ---- inject dirty data (mirrors dashboard target ~ small % failure rate) ----

    # 1. NULL customer_id (mandatory field violation) - CRITICAL, kept tight
    idx = np.random.choice(df.index, int(n * 0.0004), replace=False)
    df.loc[idx, "customer_id"] = None

    # 2. Orphaned customer_id -> referential integrity violation - CRITICAL, kept tight
    idx2 = np.random.choice(df.index, int(n * 0.0005), replace=False)
    df.loc[idx2, "customer_id"] = [make_sap_customer_id(999000 + j) for j in range(len(idx2))]

    # 3. Orphaned product_id -> referential integrity violation - CRITICAL, kept tight
    idx3 = np.random.choice(df.index, int(n * 0.0004), replace=False)
    df.loc[idx3, "product_id"] = [make_sap_material_id(888000 + j) for j in range(len(idx3))]

    # 4. Negative sales_amount (range violation / business rule: sales_amount >= 0) - CRITICAL
    idx4 = np.random.choice(df.index, int(n * 0.0005), replace=False)
    df.loc[idx4, "sales_amount"] = -abs(df.loc[idx4, "sales_amount"])

    # 5. Future order_date (business rule: order_date <= current_date) - HIGH
    idx5 = np.random.choice(df.index, int(n * 0.024), replace=False)
    future_dates = [(datetime.now() + timedelta(days=random.randint(1, 60))).strftime("%Y-%m-%d")
                     for _ in range(len(idx5))]
    df.loc[idx5, "order_date"] = future_dates

    # 6. Duplicate order records (full duplicate rows -> duplicate check) - HIGH/CRITICAL dup rule
    dup_sample = df.sample(int(n * 0.0012), random_state=2).copy()
    df = pd.concat([df, dup_sample], ignore_index=True)

    # 7. Bad data type in quantity (string injected into numeric column) - HIGH
    idx6 = np.random.choice(df.index, int(n * 0.015), replace=False)
    df["quantity"] = df["quantity"].astype(object)
    df.loc[idx6, "quantity"] = "N/A"

    # 8. Zero/negative quantity (range violation) - HIGH
    idx7 = np.random.choice(df.index, int(n * 0.018), replace=False)
    df.loc[idx7, "quantity"] = 0

    # 9. Stale load_timestamp (freshness violation) - simulate ~0.2% of records
    #    loaded more than 48 hours ago (SLA breach)
    idx8 = np.random.choice(df.index, int(n * 0.002), replace=False)
    stale_ts = [(datetime.now() - timedelta(hours=random.randint(50, 400))).strftime("%Y-%m-%d %H:%M:%S")
                for _ in range(len(idx8))]
    df.loc[idx8, "load_timestamp"] = stale_ts

    # 10. Schema drift: a handful of rows carry an unexpected extra status value
    idx9 = np.random.choice(df.index, 14, replace=False)  # matches dashboard "Schema Violations: 14"
    df.loc[idx9, "order_status"] = "UNKNOWN_LEGACY_CODE"

    return df


def main():
    print("Generating dim_customer...")
    customers = generate_customers(N_CUSTOMERS)
    customers.to_csv(f"{OUT_DIR}/dim_customer.csv", index=False)
    print(f"  -> {len(customers):,} rows")

    print("Generating dim_product...")
    products = generate_products(N_PRODUCTS)
    products.to_csv(f"{OUT_DIR}/dim_product.csv", index=False)
    print(f"  -> {len(products):,} rows")

    print("Generating fact_sales...")
    valid_cust_ids = customers["customer_id"].dropna().unique().tolist()
    valid_prod_ids = products["product_id"].dropna().unique().tolist()
    sales = generate_sales(N_SALES, valid_cust_ids, valid_prod_ids)
    sales.to_csv(f"{OUT_DIR}/fact_sales.csv", index=False)
    print(f"  -> {len(sales):,} rows")

    # metadata file recording the "production scale" this sample represents
    with open(f"{OUT_DIR}/_scale_metadata.txt", "w") as f:
        f.write(f"sample_fact_rows={len(sales)}\n")
        f.write(f"production_scale_rows={FULL_SCALE_ROWS}\n")
        f.write(f"scale_factor={FULL_SCALE_ROWS/len(sales):.4f}\n")

    print("\nDone. Files written to:", OUT_DIR)


if __name__ == "__main__":
    main()
