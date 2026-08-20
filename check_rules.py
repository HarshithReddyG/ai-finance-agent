import pandas as pd
from src.categorization.rules import categorize_by_rules

df = pd.read_csv("data/mock_transactions.csv")
eval_df = pd.read_csv("data/mock_transactions_eval.csv")
merged = df.merge(eval_df, on="transaction_id")

merged["predicted"] = merged.apply(
    lambda r: categorize_by_rules(r["merchant_name"], r["raw_description"]), axis=1
)

matched = merged["predicted"].notna()
correct = merged["predicted"] == merged["category_truth"]

print(f"Coverage (rules matched something): {matched.mean():.1%}")
print(f"Accuracy on matched rows: {correct[matched].mean():.1%}")
print(f"Unmatched (falls through to LLM): {(~matched).sum()} rows")


print("--- Unmatched ---")
print(merged[~matched][["merchant_name", "raw_description", "category_truth"]])

print("--- Matched but wrong ---")
print(merged[matched & ~correct][["merchant_name", "raw_description", "category_truth", "predicted"]])
