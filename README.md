# Fiken Transaction Analyzer

A Python script that analyzes Fiken journal entries for October 1-10, 2025, filtering transactions that touch bank account 1920:10001, and categorizing them based on expense accounts with proportional allocation.

## Setup

1. Copy `.env.template` to `.env` and fill in your Fiken API credentials:
   ```
   FIKEN_COMPANY_SLUG=your-company-slug-here
   FIKEN_TOKEN=your-fiken-api-token-here
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the analyzer:
```bash
python analyze_transactions.py
```

This will:
1. Fetch all journal entries from October 1-10, 2025
2. Filter for entries touching bank account 1920:10001
3. Fetch full transaction details for each entry
4. Categorize transactions based on expense accounts
5. Export results to `fiken_transactions_2025-10-01_to_2025-10-10.csv`

## Categorization Rules

- **Inflow** (positive bank amount) → `Income`
- **Outflow** (negative bank amount) → Categorized by expense accounts:
  - `5001, 5092, 5401, 5405, 5901, 5950, 2771, 2400:20024` → `Personalkostnader`
  - `6420, 6553` → `Programvare og datasystemer`
  - All others → `ADK`

## Output Format

The CSV contains one row per expense line with proportional bank amount allocation:
- Date, Description, Transaction ID, Journal Entry ID
- Bank Amount (NOK) - proportional amount allocated to this expense line
- Direction (Inflow/Outflow), Category, Expense Account
- Expense Account Amount (NOK) - original expense line amount
