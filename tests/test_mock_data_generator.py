"""Phase 2 tests for the mock transaction data generator."""

import pandas as pd
import pytest

from src.ingestion.generate_mock_transactions import generate

INGEST_COLUMNS = {
    "transaction_id", "account_id", "account_type", "date",
    "merchant_name", "raw_description", "amount", "currency", "pending",
    "category_truth", "is_recurring_truth", "is_anomaly_truth", "anomaly_type",
}


@pytest.fixture(scope="module")
def df():
    return generate(months=13, seed=42)


def test_schema_has_expected_columns(df):
    assert INGEST_COLUMNS.issubset(set(df.columns))


def test_no_nulls_in_required_fields(df):
    required = ["transaction_id", "account_id", "account_type", "date", "merchant_name", "amount"]
    for col in required:
        assert df[col].isnull().sum() == 0, f"unexpected nulls in {col}"


def test_transaction_ids_are_unique(df):
    assert df["transaction_id"].is_unique


def test_all_three_account_types_present(df):
    assert set(df["account_type"]) == {"checking", "credit_card", "savings"}


def test_income_transactions_are_negative_amounts(df):
    # Plaid sign convention: negative amount = money IN (income/credit).
    income = df[df["category_truth"] == "Income"]
    assert len(income) > 0
    assert (income["amount"] < 0).all()


def test_transfers_net_to_zero(df):
    # Every checking->savings transfer should have a matching offsetting leg.
    transfers = df[df["category_truth"] == "Transfers"]
    assert len(transfers) > 0
    assert round(transfers["amount"].sum(), 2) == 0.0


def test_recurring_transactions_are_flagged(df):
    assert df["is_recurring_truth"].sum() > 0


def test_anomalies_are_flagged_with_a_type(df):
    anomalies = df[df["is_anomaly_truth"]]
    assert len(anomalies) > 0
    assert anomalies["anomaly_type"].isnull().sum() == 0
    expected_types = {
        "duplicate_charge", "large_one_off_purchase",
        "new_rare_merchant", "category_spending_spike",
    }
    assert set(anomalies["anomaly_type"]) <= expected_types


def test_generation_is_deterministic_given_same_seed():
    df_a = generate(months=6, seed=7)
    df_b = generate(months=6, seed=7)
    non_id_cols = [c for c in df_a.columns if c != "transaction_id"]
    pd.testing.assert_frame_equal(
        df_a[non_id_cols].reset_index(drop=True),
        df_b[non_id_cols].reset_index(drop=True),
    )


def test_different_seeds_produce_different_data():
    df_a = generate(months=6, seed=1)
    df_b = generate(months=6, seed=2)
    assert len(df_a) != len(df_b) or not df_a["amount"].equals(df_b["amount"])