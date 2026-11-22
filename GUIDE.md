# Reconciliation method

Paste a bank CSV and a book CSV into the two string fields. Each uses id, date, currency, amount, reference and description columns. IDs are unique within a source. Dates use ISO calendar notation. Signed amounts must already use the same debit/credit convention in both exports. Amounts have up to two decimal places; currencies are never converted.

Only equal currency and amount enter the same comparison group. The date window excludes distant entries. Remaining pairs are ordered by exact nonblank reference, date distance, description similarity and stable ID. Every competing pair remains visible; a close description cannot prove settlement. The score is not a probability.

Approve individual pairs. Conflicting approvals are rejected rather than silently assigning either transaction twice. The reconciled.csv register includes both source IDs and dates. unmatched.csv retains every unused row on both sides, including rejected or unreviewed alternatives. Split payments, bank fees folded into a total and foreign-exchange settlements require separate review.
