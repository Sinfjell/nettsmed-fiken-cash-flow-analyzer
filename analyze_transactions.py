#!/usr/bin/env python3
"""
Fiken Transaction Analysis Tool
Analyzes journal entries for a date window, filters those touching bank account 1920:10001,
categorizes inflows/outflows using transaction types, and generates CSV reports.

Usage:
    python analyze_transactions_clean.py
"""

import csv
import os
import sys
import time
import uuid
from typing import Dict, List, Tuple, Any
import requests

# -------------------------
# Configuration
# -------------------------
BASE_URL = "https://api.fiken.no/api/v2"
FIKEN_TOKEN = "5294010348.kuBGOemzaPEMSLqdtViPJed9njsO07vr"
FIKEN_COMPANY_SLUG = "nettsmed-as"

# Date window (inclusive)
DATE_FROM = "2025-10-01"
DATE_TO = "2025-10-31"

# Bank account to inspect
BANK_ACCOUNT_CODE = "1920:10001"

# Category rules
PERSONAL_KOSTNADS_ACCOUNTS = set(["5001","5092","5401","5405","5901","5950","2771"])
PROGRAMVARE_ACCOUNTS = set(["6420","6553"])
VAT_ACCOUNTS = set(["2700","2710","2711","2720","2740"])

# Transaction type to category mapping
TYPE_TO_CATEGORY = {
    "Salg": "Income",
    "Lønn": "Personalkostnader", 
    "Betaling av arbeidsgiveravgift": "Personalkostnader",
    "Mva-oppgjør": "MVA",
    "Bankomkostning": "ADK",
    "Kjøp": None,  # Determine from accounts
    "Fri": None,   # Determine from accounts
    "Inngående balanse": "ADK",
}

# -------------------------
# HTTP helpers
# -------------------------
def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {FIKEN_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Fiken-Transaction-Analysis/1.0 (+https://nettsmed.no)",
        "X-Request-ID": str(uuid.uuid4())
    }

def _get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    """Make GET request with retries and error handling."""
    for attempt in range(3):
        try:
            resp = session.get(url, headers=_headers(), **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            time.sleep(1)
    return resp

# -------------------------
# API functions
# -------------------------
def fetch_journal_entries(session: requests.Session, company_slug: str, date_from: str, date_to: str) -> List[Dict[str, Any]]:
    """Fetch all journal entries for date range with pagination."""
    all_entries: List[Dict[str, Any]] = []
    page = 0
    page_size = 100
    
    while True:
        params = {
            "dateGe": date_from,
            "dateLe": date_to,
            "page": page,
            "pageSize": page_size
        }
        url = f"{BASE_URL}/companies/{company_slug}/journalEntries"
        resp = _get(session, url, params=params)
        data = resp.json()
        
        if isinstance(data, list):
            all_entries.extend(data)
        else:
            all_entries.extend(data.get("items", []))
        
        total_pages = int(resp.headers.get("Fiken-Api-Page-Count", "1"))
        if page + 1 >= total_pages:
            break
        page += 1
    
    return all_entries

def fetch_transaction(session: requests.Session, company_slug: str, transaction_id: int) -> Dict[str, Any]:
    """Fetch full transaction details."""
    url = f"{BASE_URL}/companies/{company_slug}/transactions/{transaction_id}"
    resp = _get(session, url)
    return resp.json()

# -------------------------
# Data processing
# -------------------------
def extract_relevant_accounts_from_transaction(txn: Dict[str, Any]) -> List[str]:
    """Extract expense accounts from transaction entries."""
    accounts = []
    for entry in txn.get("entries", []):
        for line in entry.get("lines", []):
            acct = str(line.get("account", "")).strip()
            if acct and acct != BANK_ACCOUNT_CODE:
                accounts.append(acct)
    return accounts

def categorize_by_transaction_type(transaction_type: str, accounts: List[str], descriptions: List[str]) -> str:
    """Categorize transaction based on its type field."""
    if transaction_type in TYPE_TO_CATEGORY:
        category = TYPE_TO_CATEGORY[transaction_type]
        if category is not None:
            return category
    
    # For Kjøp, Fri, and unknown types, use account-based categorization
    return categorize_outflow(accounts, descriptions)

def categorize_outflow(accounts: List[str], descriptions: List[str]) -> str:
    """Apply rules to derive a single category for an Outflow."""
    accs = set(a.strip() for a in accounts if a)
    desc_text = " ".join(descriptions).lower()
    
    # Check for MVA/VAT payments first
    if "merverdiavgift" in desc_text or "mva" in desc_text:
        if any(acc.startswith("274") or acc.startswith("270") for acc in accs):
            return "MVA"

    # Personalkostnader
    if accs & PERSONAL_KOSTNADS_ACCOUNTS:
        return "Personalkostnader"
    if "aga" in desc_text or "arbeidsgiveravgift" in desc_text:
        return "Personalkostnader"

    # Programvare og datasystemer
    if accs & PROGRAMVARE_ACCOUNTS:
        return "Programvare og datasystemer"

    # Default bucket
    return "ADK"

def determine_direction_and_amount(bank_line: Dict[str, Any]) -> Tuple[str, float]:
    """Determine if this is an inflow or outflow and return amount in NOK."""
    amount_ore = bank_line.get("amount", 0)
    amount_nok = amount_ore / 100.0
    
    if amount_nok > 0:
        return "Inflow", amount_nok
    else:
        return "Outflow", abs(amount_nok)

def extract_invoice_number(description: str) -> str:
    """Extract invoice number from description."""
    import re
    match = re.search(r'faktura\s*#?(\w+)', description, re.IGNORECASE)
    return match.group(1) if match else ""

# -------------------------
# Report generation
# -------------------------
def generate_net_report(session: requests.Session, filtered: List[Dict[str, Any]]):
    """Generate net transaction report using transaction types."""
    fieldnames = [
        "date", "description", "transactionId", "journalEntryId", "transaction_type",
        "net_amount_nok", "direction", "category", "expense_accounts", "has_reversals"
    ]
    
    out_path = f"fiken_net_transactions_{DATE_FROM}_to_{DATE_TO}.csv"
    rows = []
    processed_transactions = set()
    processed_invoices = set()

    print("Processing transactions by type...")
    
    for je in filtered:
        journal_entry_id = je.get("journalEntryId")
        transaction_id = je.get("transactionId")
        
        if transaction_id in processed_transactions:
            continue
            
        bank_lines = [ln for ln in je.get("lines", []) if str(ln.get("account")) == BANK_ACCOUNT_CODE]
        if not bank_lines:
            continue
        
        # Fetch transaction to get type
        transaction_type = ""
        try:
            if transaction_id is not None:
                txn = fetch_transaction(session, FIKEN_COMPANY_SLUG, int(transaction_id))
                transaction_type = txn.get("type", "")
        except Exception as e:
            print(f"Warning: failed to fetch transaction {transaction_id}: {e}", file=sys.stderr)
            continue
        
        # Skip cancelled transactions
        if transaction_type == "Annullering":
            print(f"Skipping cancelled transaction {transaction_id} (type: {transaction_type})")
            continue
        
        # Process each bank line
        for i, bline in enumerate(bank_lines):
            amount_ore = bline.get("amount", 0)
            net_amount_nok = amount_ore / 100.0
            
            if abs(net_amount_nok) < 0.01:
                continue
            
            # Get categorization
            expense_accounts: List[str] = []
            descriptions: List[str] = [je.get("description", "")]
            
            try:
                if transaction_id is not None:
                    txn = fetch_transaction(session, FIKEN_COMPANY_SLUG, int(transaction_id))
                    expense_accounts = extract_relevant_accounts_from_transaction(txn)
                    descriptions.extend([
                        str(entry.get("description", "")) for entry in txn.get("entries", [])
                    ])
            except Exception as e:
                print(f"Warning: failed to fetch transaction {transaction_id}: {e}", file=sys.stderr)

            # Determine direction and category
            direction = "Inflow" if net_amount_nok > 0 else "Outflow"
            if direction == "Inflow":
                category = "Income"
            else:
                category = categorize_by_transaction_type(transaction_type, expense_accounts, descriptions)
            
            # Check for reversals
            has_reversals = "motlinje" in je.get("description", "").lower()
            
            # Check for invoice deduplication
            invoice_num = extract_invoice_number(je.get("description", ""))
            if invoice_num and invoice_num in processed_invoices:
                print(f"Skipping duplicate invoice {invoice_num}")
                continue
            
            if invoice_num:
                processed_invoices.add(invoice_num)
            
            rows.append({
                "date": je.get("date", ""),
                "description": je.get("description", ""),
                "transactionId": transaction_id,
                "journalEntryId": journal_entry_id,
                "transaction_type": transaction_type,
                "net_amount_nok": f"{abs(net_amount_nok):.2f}",
                "direction": direction,
                "category": category,
                "expense_accounts": ",".join(sorted(set(expense_accounts))),
                "has_reversals": "Yes" if has_reversals else "No"
            })
        
        if transaction_id is not None:
            processed_transactions.add(transaction_id)

    # Write CSV
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Net report: Wrote {len(rows)} rows to {out_path}")
    generate_summary_stats(rows)

def generate_monthly_analysis_by_type(session: requests.Session, filtered: List[Dict[str, Any]]):
    """Generate monthly analysis using transaction types."""
    print("\nGenerating monthly analysis by transaction type...")
    
    monthly_data = {}
    processed_transactions = set()
    
    for je in filtered:
        journal_entry_id = je.get("journalEntryId")
        transaction_id = je.get("transactionId")
        
        if transaction_id in processed_transactions:
            continue
            
        bank_lines = [ln for ln in je.get("lines", []) if str(ln.get("account")) == BANK_ACCOUNT_CODE]
        if not bank_lines:
            continue
        
        # Fetch transaction to get type
        transaction_type = ""
        try:
            if transaction_id is not None:
                txn = fetch_transaction(session, FIKEN_COMPANY_SLUG, int(transaction_id))
                transaction_type = txn.get("type", "")
        except Exception as e:
            print(f"Warning: failed to fetch transaction {transaction_id}: {e}", file=sys.stderr)
            continue
        
        # Skip cancelled transactions
        if transaction_type == "Annullering":
            print(f"Skipping cancelled transaction {transaction_id} (type: {transaction_type})")
            continue
        
        # Process each bank line
        for i, bline in enumerate(bank_lines):
            amount_ore = bline.get("amount", 0)
            net_amount_nok = amount_ore / 100.0
            
            if abs(net_amount_nok) < 0.01:
                continue
            
            # Get month from journal entry
            date_str = je.get("date", "")
            if not date_str:
                continue
                
            month_key = date_str[:7]  # YYYY-MM format
            
            # Get categorization
            expense_accounts: List[str] = []
            descriptions: List[str] = [je.get("description", "")]
            
            try:
                if transaction_id is not None:
                    txn = fetch_transaction(session, FIKEN_COMPANY_SLUG, int(transaction_id))
                    expense_accounts = extract_relevant_accounts_from_transaction(txn)
                    descriptions.extend([
                        str(entry.get("description", "")) for entry in txn.get("entries", [])
                    ])
            except Exception as e:
                print(f"Warning: failed to fetch transaction {transaction_id}: {e}", file=sys.stderr)

            # Determine direction and category
            direction = "Inflow" if net_amount_nok > 0 else "Outflow"
            if direction == "Inflow":
                category = "Income"
            else:
                category = categorize_by_transaction_type(transaction_type, expense_accounts, descriptions)
            
            # Add to monthly data
            if month_key not in monthly_data:
                monthly_data[month_key] = {}
            if category not in monthly_data[month_key]:
                monthly_data[month_key][category] = {"inflow": 0.0, "outflow": 0.0, "count": 0}
            
            if direction == "Inflow":
                monthly_data[month_key][category]["inflow"] += abs(net_amount_nok)
            else:
                monthly_data[month_key][category]["outflow"] += abs(net_amount_nok)
            monthly_data[month_key][category]["count"] += 1
        
        if transaction_id is not None:
            processed_transactions.add(transaction_id)
    
    # Generate monthly CSV report
    generate_monthly_csv(monthly_data)
    
    # Generate monthly summary
    generate_monthly_summary(monthly_data)

def generate_monthly_csv(monthly_data: Dict[str, Dict[str, Dict[str, Any]]]):
    """Generate CSV file with monthly breakdown by category."""
    fieldnames = [
        "month", "category", "inflow_nok", "outflow_nok", "net_nok", "transaction_count"
    ]
    
    out_path = f"fiken_monthly_analysis_{DATE_FROM}_to_{DATE_TO}.csv"
    rows = []
    
    # Define all possible categories
    all_categories = ["Income", "Personalkostnader", "Programvare og datasystemer", "MVA", "ADK"]
    
    for month in sorted(monthly_data.keys()):
        # Add all categories for this month, even if zero
        for category in all_categories:
            if category in monthly_data[month]:
                totals = monthly_data[month][category]
                inflow = totals["inflow"]
                outflow = totals["outflow"]
                net = inflow - outflow
                count = totals["count"]
            else:
                inflow = 0.0
                outflow = 0.0
                net = 0.0
                count = 0
            
            rows.append({
                "month": month,
                "category": category,
                "inflow_nok": f"{inflow:.2f}",
                "outflow_nok": f"{outflow:.2f}",
                "net_nok": f"{net:.2f}",
                "transaction_count": count
            })
    
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Monthly analysis: Wrote {len(rows)} rows to {out_path}")

def generate_monthly_summary(monthly_data: Dict[str, Dict[str, Dict[str, Any]]]):
    """Generate monthly summary statistics."""
    print("\n" + "="*80)
    print("MONTHLY CASH FLOW ANALYSIS")
    print("="*80)
    
    # Define all possible categories
    all_categories = ["Income", "Personalkostnader", "Programvare og datasystemer", "MVA", "ADK"]
    
    # Print header
    print(f"{'Month':<12} ", end="")
    for category in all_categories:
        print(f"{category:<20} ", end="")
    print("TOTAL")
    print("-" * (12 + 21 * len(all_categories) + 10))
    
    # Print monthly data
    for month in sorted(monthly_data.keys()):
        print(f"{month:<12} ", end="")
        month_total = 0
        
        for category in all_categories:
            if category in monthly_data[month]:
                outflow = monthly_data[month][category]["outflow"]
                inflow = monthly_data[month][category]["inflow"]
                net = inflow - outflow
                month_total += net
                print(f"{net:>19.2f} ", end="")
            else:
                print(f"{'0.00':>19} ", end="")
        
        print(f"{month_total:>9.2f}")
    
    # Print totals row
    print("-" * (12 + 21 * len(all_categories) + 10))
    print(f"{'TOTAL':<12} ", end="")
    grand_total = 0
    
    for category in all_categories:
        category_total = 0
        for month_data in monthly_data.values():
            if category in month_data:
                inflow = month_data[category]["inflow"]
                outflow = month_data[category]["outflow"]
                category_total += inflow - outflow
        grand_total += category_total
        print(f"{category_total:>19.2f} ", end="")
    
    print(f"{grand_total:>9.2f}")
    print("="*80)

def generate_summary_stats(rows: List[Dict[str, Any]]):
    """Generate summary statistics by category."""
    category_totals = {}
    
    for row in rows:
        category = row["category"]
        amount = float(row["net_amount_nok"])
        direction = row["direction"]
        
        if category not in category_totals:
            category_totals[category] = {"inflow": 0.0, "outflow": 0.0, "count": 0}
        
        if direction == "Inflow":
            category_totals[category]["inflow"] += amount
        else:
            category_totals[category]["outflow"] += amount
        category_totals[category]["count"] += 1
    
    print("\n" + "="*60)
    print("CASH FLOW SUMMARY (Net Effects)")
    print("="*60)
    print(f"{'Category':<25} {'Inflow':>11} {'Outflow':>11} {'Net':>11} {'Count':>7}")
    print("-"*60)
    
    total_inflow = 0
    total_outflow = 0
    
    for category in sorted(category_totals.keys()):
        inflow = category_totals[category]["inflow"]
        outflow = category_totals[category]["outflow"]
        net = inflow - outflow
        count = category_totals[category]["count"]
        
        total_inflow += inflow
        total_outflow += outflow
        
        print(f"{category:<25} {inflow:>11.2f} {outflow:>11.2f} {net:>11.2f} {count:>7}")
    
    print("-"*60)
    print(f"{'TOTAL':<25} {total_inflow:>11.2f} {total_outflow:>11.2f} {total_inflow-total_outflow:>11.2f}")
    print("="*60)

# -------------------------
# Main routine
# -------------------------
def main():
    print(f"Fetching journal entries for {FIKEN_COMPANY_SLUG} {DATE_FROM}..{DATE_TO} ...")
    
    with requests.Session() as session:
        # Fetch all journal entries
        all_entries = fetch_journal_entries(session, FIKEN_COMPANY_SLUG, DATE_FROM, DATE_TO)
        print(f"Fetched {len(all_entries)} journal entries.")
        
        # Filter entries that touch our bank account
        filtered = []
        for je in all_entries:
            for line in je.get("lines", []):
                if str(line.get("account")) == BANK_ACCOUNT_CODE:
                    filtered.append(je)
                    break
        print(f"Kept {len(filtered)} entries hitting account {BANK_ACCOUNT_CODE}.")
        
        # Generate reports
        generate_net_report(session, filtered)
        generate_monthly_analysis_by_type(session, filtered)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(1)
