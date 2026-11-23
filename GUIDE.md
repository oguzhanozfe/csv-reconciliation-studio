# Reconciliation method

Paste a bank CSV and a book CSV into the two string fields. Each uses id, date, currency, amount, reference and description columns. IDs are unique within a source. Dates use ISO calendar notation. Signed amounts must already use the same debit/credit convention in both exports. Amounts have up to two decimal places; currencies are never converted.

Only equal currency and amount enter the same comparison group. The date window excludes distant entries. Remaining pairs are ordered by exact nonblank reference, date distance, description similarity and stable ID. Every competing pair remains visible; a close description cannot prove settlement. The score is not a probability.

Approve individual pairs. Conflicting approvals are rejected rather than silently assigning either transaction twice. The reconciled.csv register includes both source IDs and dates. unmatched.csv retains every unused row on both sides, including rejected or unreviewed alternatives. Split payments, bank fees folded into a total and foreign-exchange settlements require separate review.

## Controller-reviewed payment exceptions

An input can include a `settlement_signoffs` array for ambiguous payments. Each entry identifies a unique case and a bank/book pair, records the role `settlement_controller`, and cites an advice reference and a written reason. Use an empty array when no controller has signed off. Analysis rejects unknown pairs, overlapping authorizations, missing evidence or an unsupported role.

In this mode, clearing an ambiguous pair requires both its matching controller record and the reviewer's explicit selection. The output `payment-decisions.json` records which pairs still need a controller or reviewer, which were approved, and which were excluded because their bank or book row was already used. Approving one pair leaves any unused ledger rows in the unmatched queue. Repeating the export on the same source and choices preserves file contents and their checksums.

The role and advice reference are assertions supplied by the input. This local exercise assumes a trusted upstream sign-off register. It provides no identity verification, signature check or connection to a bank or payment processor.
