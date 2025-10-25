# Fiken Cash Flow Analyzer

Analyzes Fiken journal entries for bank account 1920:10001, categorizes transactions by type, and generates comprehensive cash flow reports with balance validation.

## Features

- **Transaction Analysis**: Fetches journal entries for date range and filters bank account transactions
- **Smart Categorization**: Uses Fiken transaction types with fallback to account-based rules
- **Balance Validation**: Validates opening/closing balances against calculated cash flow
- **Monthly Reports**: Generates monthly breakdown by category
- **Cancellation Handling**: Automatically filters out cancelled transactions (type: "Annullering")

## Quick Start

1. **Setup Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure**:
   - Copy `.env.template` to `.env`
   - Add your Fiken token and company slug

3. **Run Analysis**:
   ```bash
   python analyze_transactions.py
   ```

## Output Files

- `fiken_net_transactions_YYYY-MM-DD_to_YYYY-MM-DD.csv` - Detailed transaction report
- `fiken_monthly_analysis_YYYY-MM-DD_to_YYYY-MM-DD.csv` - Monthly category breakdown

## Categories

- **Income**: Sales transactions (type: "Salg")
- **Personalkostnader**: Salary, payroll taxes (accounts: 5001, 5092, 5401, 5405, 5901, 5950, 2771, 6795)
- **Programvare og datasystemer**: Software/IT (accounts: 6420, 6553)
- **MVA**: VAT payments (type: "Mva-oppgjør" or merverdiavgift in description)
- **ADK**: Other/Administrative (default)

## Configuration

Edit `analyze_transactions.py` to change:
- Date range: `DATE_FROM` and `DATE_TO`
- Bank account: `BANK_ACCOUNT_CODE`
- Category rules: Account sets and type mappings

## Balance Validation

The analyzer validates that:
```
Opening Balance + Net Cash Flow = Closing Balance
```

If validation fails, check for:
- Bank transfers not in journal entries
- Interest payments
- Transactions outside date range
- API data inconsistencies

## Requirements

- Python 3.7+
- requests
- python-dotenv

## License

Private use only.