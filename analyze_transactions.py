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
DATE_TO = "2025-10-10"

# Bank account to inspect
BANK_ACCOUNT_CODE = "1920:10001"

# Output CSV path
OUTPUT_CSV = f"fiken_transactions_{DATE_FROM}_to_{DATE_TO}.csv"

# Category rules
PERSONAL_KOSTNADS_ACCOUNTS = set(["5001","5092","5401","5405","5901","5950","2771","2400:20024"])  # includes AP subaccount Fjellestad AS
PROGRAMVARE_ACCOUNTS = set(["6420","6553"])
VAT_ACCOUNTS = set(["2700","2710","2711","2720","2740"])  # common VAT accounts, not categorized as expenses

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

def categorize_outflow(accounts: List[str], descriptions: List[str]) -> str:
    """
    Apply user's rules to derive a single category for an Outflow.
    If multiple rules match, apply in priority: Personal -> Programvare -> ADK.
    """
    # Normalize accounts (strip spaces)
    accs = set(a.strip() for a in accounts if a)

    # Personalkostnader
    if accs & PERSONAL_KOSTNADS_ACCOUNTS:
        return "Personalkostnader"
    # Heuristic: description hints for AGA/Employer's tax
    desc_text = " ".join(descriptions).lower()
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

    # Prepare CSV
    fieldnames = [
        "date",
        "description",
        "transactionId",
        "journalEntryId",
        "amount_nok_on_1920_10001",
        "direction",
        "category",
        "expense_accounts"
    ]
    out_path = OUTPUT_CSV
    rows = []

    for idx, je in enumerate(filtered, 1):
        journal_entry_id = je.get("journalEntryId")
        transaction_id = je.get("transactionId")
        date = je.get("date", "")
        description = je.get("description", "") or ""

        # Find the bank line (there can be multiple; consider each separately)
        bank_lines = [ln for ln in je.get("lines", []) if str(ln.get("account")) == BANK_ACCOUNT_CODE]
        if not bank_lines:
            # Shouldn't happen due to filter, but guard anyway
            continue

        # Fetch full transaction
        txn = {}
        expense_accounts: List[str] = []
        descriptions: List[str] = [description]
        if transaction_id is not None:
            try:
                txn = fetch_transaction(session, FIKEN_COMPANY_SLUG, int(transaction_id))
                # Gather expense/counter accounts across the whole transaction
                expense_accounts = extract_relevant_accounts_from_transaction(txn)
                # collect descriptions to scan for "AGA"
                descriptions.extend([
                    str(entry.get("description", "")) for entry in txn.get("entries", [])
                ])
            except Exception as e:
                print(f"Warning: failed to fetch transaction {transaction_id}: {e}", file=sys.stderr)

        # Determine category and emit one row per bank line
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
                "amount_nok_on_1920_10001": f"{amount_nok:.2f}",
                "direction": direction,
                "category": category,
                "expense_accounts": ",".join(sorted(set(expense_accounts)))
            })

        # Progress indicator
        if idx % 25 == 0 or idx == len(filtered):
            print(f"Processed {idx}/{len(filtered)} entries...")

    # Write CSV
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. Wrote {len(rows)} rows to {out_path}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(1)
