#!/usr/bin/env python3
"""
Fiken Transaction Analysis Tool
Analyzes journal entries for a date window, filters those touching bank account 1920:10001,
dereferences transactions, categorizes inflows/outflows, and writes a CSV report.

Usage:
    python analyze_transactions.py
"""

import csv
import os
import sys
import time
import uuid
from typing import Dict, List, Tuple, Any
import requests

# -------------------------
# Configuration (hardcoded per user request)
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
PERSONAL_KOSTNADS_ACCOUNTS = set(["5001","5092","5401","5405","5901","5950","2771","2400:20024"])  # includes AP subaccount Fjellestad AS
PROGRAMVARE_ACCOUNTS = set(["6420","6553"])
VAT_ACCOUNTS = set(["2700","2710","2711","2720","2740"])  # common VAT accounts, not categorized as expenses

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

def _get(session: requests.Session, url: str, params: Dict[str, Any] = None, retries: int = 3, backoff: float = 0.8):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, headers=_headers(), params=params, timeout=30)
            if r.status_code >= 200 and r.status_code < 300:
                return r
            # Basic retry on 429/5xx
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(backoff * attempt)
                continue
            r.raise_for_status()
        except requests.RequestException as e:
            last_exc = e
            time.sleep(backoff * attempt)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"GET failed: {url}")

# -------------------------
# API helpers
# -------------------------
def fetch_journal_entries(session: requests.Session, company_slug: str, date_from: str, date_to: str) -> List[Dict[str, Any]]:
    """
    Fetch all journal entries for a date window [date_from, date_to], inclusive.
    Paginates using Fiken-Api-Page* headers.
    Includes offsetTransactionId for reversal detection.
    """
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
            # If API returns a dict, try extracting 'items' (future-proof)
            all_entries.extend(data.get("items", []))

        # Pagination headers
        total_pages = int(resp.headers.get("Fiken-Api-Page-Count", "1"))
        # Stop if last page
        if page + 1 >= total_pages:
            break
        page += 1
    return all_entries

def fetch_transaction(session: requests.Session, company_slug: str, transaction_id: int) -> Dict[str, Any]:
    url = f"{BASE_URL}/companies/{company_slug}/transactions/{transaction_id}"
    resp = _get(session, url)
    return resp.json()

# -------------------------
# Net effect calculation
# -------------------------


# -------------------------
# Categorization logic
# -------------------------
def determine_direction_and_amount(bank_line: Dict[str, Any]) -> Tuple[str, float]:
    """
    From a bank line (with signed 'amount' in øre), determine direction and amount in NOK.
    Negative amount => outflow; positive => inflow.
    """
    amount_ore = int(bank_line.get("amount", 0))
    direction = "Inflow" if amount_ore > 0 else "Outflow"
    amount_nok = abs(amount_ore) / 100.0
    return direction, amount_nok

def extract_relevant_accounts_from_transaction(txn: Dict[str, Any]) -> List[str]:
    """
    Collect all account codes from all entries' lines within the transaction.
    Keep them as strings (they may include subaccounts like 2400:20024).
    """
    accounts: List[str] = []
    for entry in txn.get("entries", []):
        for line in entry.get("lines", []):
            acct = str(line.get("account", "")).strip()
            if acct:
                accounts.append(acct)
    return accounts

def categorize_by_transaction_type(transaction_type: str, accounts: List[str], descriptions: List[str]) -> str:
    """
    Categorize transaction based on its type field.
    For Kjøp and Fri types, fall back to account-based categorization.
    """
    # Check if type has direct mapping
    if transaction_type in TYPE_TO_CATEGORY:
        category = TYPE_TO_CATEGORY[transaction_type]
        if category is not None:
            return category
    
    # For Kjøp, Fri, and unknown types, use account-based categorization
    return categorize_outflow(accounts, descriptions)

def categorize_outflow(accounts: List[str], descriptions: List[str]) -> str:
    """
    Apply user's rules to derive a single category for an Outflow.
    If multiple rules match, apply in priority: MVA -> Personal -> Programvare -> ADK.
    """
    # Normalize accounts (strip spaces)
    accs = set(a.strip() for a in accounts if a)
    
    # Check for MVA/VAT payments first
    desc_text = " ".join(descriptions).lower()
    if "merverdiavgift" in desc_text or "mva" in desc_text:
        # Verify it's a VAT payment, not just VAT in purchase
        if any(acc.startswith("274") or acc.startswith("270") for acc in accs):
            return "MVA"

    # Personalkostnader
    if accs & PERSONAL_KOSTNADS_ACCOUNTS:
        return "Personalkostnader"
    # Heuristic: description hints for AGA/Employer's tax
    if "aga" in desc_text or "arbeidsgiveravgift" in desc_text:
        return "Personalkostnader"

    # Programvare og datasystemer
    if accs & PROGRAMVARE_ACCOUNTS:
        return "Programvare og datasystemer"

    # Default bucket
    return "ADK"

# -------------------------
# Main routine
# -------------------------
def main():
    session = requests.Session()

    print(f"Fetching journal entries for {FIKEN_COMPANY_SLUG} {DATE_FROM}..{DATE_TO} ...")
    entries = fetch_journal_entries(session, FIKEN_COMPANY_SLUG, DATE_FROM, DATE_TO)
    print(f"Fetched {len(entries)} journal entries.")

    # Filter: keep only entries with bank account line 1920:10001
    filtered = []
    for je in entries:
        lines = je.get("lines", [])
        for ln in lines:
            if str(ln.get("account")) == BANK_ACCOUNT_CODE:
                filtered.append(je)
                break
    print(f"Kept {len(filtered)} entries hitting account {BANK_ACCOUNT_CODE}.")

    # Generate both full and net transaction reports
    generate_full_report(session, filtered)
    generate_net_report(session, filtered)
    
    # Generate monthly analysis report using transaction types
    generate_monthly_analysis_by_type(session, filtered)

def generate_full_report(session: requests.Session, filtered: List[Dict[str, Any]]):
    """Generate full transaction report with offset information."""
    fieldnames = [
        "date",
        "description", 
        "transactionId",
        "journalEntryId",
        "offsetTransactionId",
        "amount_nok_on_1920_10001",
        "direction",
        "category",
        "expense_accounts",
        "has_reversals"
    ]
    
    out_path = f"fiken_full_transactions_{DATE_FROM}_to_{DATE_TO}.csv"
    rows = []

    for idx, je in enumerate(filtered, 1):
        journal_entry_id = je.get("journalEntryId")
        transaction_id = je.get("transactionId")
        offset_id = je.get("offsetTransactionId")
        date = je.get("date", "")
        description = je.get("description", "") or ""

        # Find the bank line
        bank_lines = [ln for ln in je.get("lines", []) if str(ln.get("account")) == BANK_ACCOUNT_CODE]
        if not bank_lines:
            continue

        # Fetch full transaction for categorization
        txn = {}
        expense_accounts: List[str] = []
        descriptions: List[str] = [description]
        if transaction_id is not None:
            try:
                txn = fetch_transaction(session, FIKEN_COMPANY_SLUG, int(transaction_id))
                expense_accounts = extract_relevant_accounts_from_transaction(txn)
                descriptions.extend([
                    str(entry.get("description", "")) for entry in txn.get("entries", [])
                ])
            except Exception as e:
                print(f"Warning: failed to fetch transaction {transaction_id}: {e}", file=sys.stderr)

        # Check if this transaction has reversals
        has_reversals = False
        if "motlinje" in description.lower():
            has_reversals = True

        # Emit one row per bank line
        for bline in bank_lines:
            direction, amount_nok = determine_direction_and_amount(bline)
            if direction == "Inflow":
                category = "Income"
            else:
                category = categorize_outflow(expense_accounts, descriptions)

            rows.append({
                "date": date,
                "description": description,
                "transactionId": transaction_id,
                "journalEntryId": journal_entry_id,
                "offsetTransactionId": offset_id or "",
                "amount_nok_on_1920_10001": f"{amount_nok:.2f}",
                "direction": direction,
                "category": category,
                "expense_accounts": ",".join(sorted(set(expense_accounts))),
                "has_reversals": "Yes" if has_reversals else "No"
            })

        if idx % 25 == 0 or idx == len(filtered):
            print(f"Processed {idx}/{len(filtered)} entries for full report...")

    # Write full CSV
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Full report: Wrote {len(rows)} rows to {out_path}")

def generate_net_report(session: requests.Session, filtered: List[Dict[str, Any]]):
    """Generate net transaction report using invoice-based grouping."""
    fieldnames = [
        "date",
        "description",
        "invoice_number",
        "transactionId",
        "journalEntryId", 
        "net_amount_nok",
        "direction",
        "category",
        "expense_accounts",
        "transaction_count",
        "has_reversals",
        "related_transaction_ids"
    ]
    
    out_path = f"fiken_net_transactions_{DATE_FROM}_to_{DATE_TO}.csv"
    rows = []

    # Process transactions using transaction types
    print("Processing transactions by type...")
    processed_transactions = set()

    for je in filtered:
        journal_entry_id = je.get("journalEntryId")
        transaction_id = je.get("transactionId")
        
        # Skip if we've already processed this transaction
        if transaction_id in processed_transactions:
            continue
            
        # Find bank lines for this journal entry
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
        
        # Skip cancelled transactions (including Motlinje reversals with type Annullering)
        if transaction_type == "Annullering":
            print(f"Skipping cancelled transaction {transaction_id} (type: {transaction_type})")
            continue
        
        # Process each bank line
        for i, bline in enumerate(bank_lines):
            amount_ore = bline.get("amount", 0)
            net_amount_nok = amount_ore / 100.0
            
            # Skip zero amounts
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
            
            rows.append({
                "date": je.get("date", ""),
                "description": je.get("description", ""),
                "invoice_number": "",  # No longer using invoice grouping
                "transactionId": transaction_id,
                "journalEntryId": journal_entry_id,
                "net_amount_nok": f"{abs(net_amount_nok):.2f}",
                "direction": direction,
                "category": category,
                "expense_accounts": ",".join(sorted(set(expense_accounts))),
                "transaction_count": 1,
                "has_reversals": "Yes" if has_reversals else "No",
                "related_transaction_ids": str(transaction_id) if transaction_id else ""
            })
        
        # Mark transaction as processed
        if transaction_id is not None:
            processed_transactions.add(transaction_id)

    # Write net CSV
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Net report: Wrote {len(rows)} rows to {out_path}")
    
    # Generate summary statistics
    generate_summary_stats(rows)

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
    print(f"{'Category':<25} {'Inflow':<12} {'Outflow':<12} {'Net':<12} {'Count':<8}")
    print("-"*60)
    
    total_inflow = 0
    total_outflow = 0
    
    for category, totals in sorted(category_totals.items()):
        inflow = totals["inflow"]
        outflow = totals["outflow"]
        net = inflow - outflow
        count = totals["count"]
        
        total_inflow += inflow
        total_outflow += outflow
        
        print(f"{category:<25} {inflow:>11.2f} {outflow:>11.2f} {net:>11.2f} {count:>7}")
    
    print("-"*60)
    print(f"{'TOTAL':<25} {total_inflow:>11.2f} {total_outflow:>11.2f} {total_inflow-total_outflow:>11.2f}")
    print("="*60)


def generate_monthly_csv(monthly_data: Dict[str, Dict[str, Dict[str, Any]]]):
    """Generate CSV file with monthly breakdown by category."""
    fieldnames = [
        "month",
        "category",
        "inflow_nok",
        "outflow_nok",
        "net_nok",
        "transaction_count"
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
    
    # Define all possible categories (including Income)
    all_categories = ["Income", "Personalkostnader", "Programvare og datasystemer", "MVA", "ADK"]
    
    # Add any additional categories found in data
    for month_data in monthly_data.values():
        all_categories.extend(month_data.keys())
    all_categories = sorted(set(all_categories))
    
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

def generate_monthly_analysis_by_type(session: requests.Session, filtered: List[Dict[str, Any]]):
    """Generate monthly analysis using transaction types instead of invoice grouping."""
    print("\nGenerating monthly analysis by transaction type...")
    
    monthly_data = {}
    processed_transactions = set()
    
    for je in filtered:
        journal_entry_id = je.get("journalEntryId")
        transaction_id = je.get("transactionId")
        
        # Skip if we've already processed this transaction
        if transaction_id in processed_transactions:
            continue
            
        # Find bank lines for this journal entry
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
        
        # Skip cancelled transactions (including Motlinje reversals with type Annullering)
        if transaction_type == "Annullering":
            print(f"Skipping cancelled transaction {transaction_id} (type: {transaction_type})")
            continue
        
        # Process each bank line
        for i, bline in enumerate(bank_lines):
            amount_ore = bline.get("amount", 0)
            net_amount_nok = amount_ore / 100.0
            
            # Skip zero amounts
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
        
        # Mark transaction as processed
        if transaction_id is not None:
            processed_transactions.add(transaction_id)
    
    # Generate monthly CSV report
    generate_monthly_csv(monthly_data)
    
    # Generate monthly summary
    generate_monthly_summary(monthly_data)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(1)
