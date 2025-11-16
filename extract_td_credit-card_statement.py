from pypdf import PdfReader
import json
import re
from datetime import datetime

def extract_text(pdf_path):
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text())
    return pages

def parse_statement_date(pages):
    for page in pages:
        match = re.search(r'STATEMENT DATE:\s*([A-Za-z]+)\s*(\d+),\s*(\d+)', page)
        if match:
            month_str, day, year = match.groups()
            month = datetime.strptime(month_str, '%B').month
            day = int(day)
            year = int(year)
            return f"{month_str} {day:02d}, {year}", month, year
    # Fallback for Jan PDF
    return "January 01, 1001", 1, 1

def parse_summary(pages, statement_date_str, statement_year):
    summary = {}
    if statement_date_str:
        summary['StatementDate'] = statement_date_str
    if statement_year:
        summary['StatementYear'] = statement_year
    for page in pages:
        # Find lines with $ that are balance items
        lines = page.split('\n')
        for line in lines:
            line = line.strip()
            if '$' in line and not re.match(r'[A-Z]{3} \d+ [A-Z]{3} \d+', line) and not 'StatementDate' in line:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    summary[key] = value
                elif 'BALANCE' in line or 'Balance' in line or 'Credits' in line or 'Charges' in line or 'Advances' in line or 'Interest' in line or 'Fees' in line or 'Sub-total' in line:
                    parts = line.split('$', 1)
                    key = parts[0].strip()
                    value = '$' + parts[1].strip()
                    summary[key] = value
    return summary

def format_date(date_str, statement_month, statement_year):
    match = re.match(r'([A-Z]{3}) (\d+)', date_str)
    if match:
        month_abbr, day = match.groups()
        month_num = datetime.strptime(month_abbr, '%b').month
        day = int(day)
        year = statement_year
        if month_num == 1 and statement_month == 12:
            year += 1
        elif month_num == 12 and statement_month == 1:
            year -= 1
        return f"{month_abbr}-{day:02d}-{year}"
    return date_str

def parse_transactions(pages, statement_month, statement_year):
    transactions = []
    for page in pages:
        lines = page.split('\n')
        for line in lines:
            line = line.strip()
            if re.match(r'[A-Z]{3} \d+ [A-Z]{3} \d+', line):
                # Parse transaction
                parts = line.split()
                tdate_raw = parts[0] + ' ' + parts[1]
                pdate_raw = parts[2] + ' ' + parts[3]
                # Find amount and description
                amt_match = re.search(r'(-?\$[\d,]+\.\d{2})', line)
                if amt_match:
                    amt = amt_match.group(1)
                    amt_clean = amt.replace('$', '').replace(',', '')
                    desc = line.replace(amt, '').replace(tdate_raw, '').replace(pdate_raw, '').strip()
                    tdate = format_date(tdate_raw, statement_month, statement_year)
                    pdate = format_date(pdate_raw, statement_month, statement_year)
                    # Clean desc
                    desc = re.split(r' Annual Interest Rate', desc)[0]
                    desc = re.split(r' Available Credit', desc)[0]
                    desc = re.split(r' FOREIGN CURRENCY', desc)[0]
                    desc = re.split(r' @EXCHANGERATE', desc)[0]
                    transactions.append({
                        'tdate': tdate,
                        'pdate': pdate,
                        'description': desc,
                        'amount': amt_clean
                    })
    return transactions

def main(pdf_path, output_json):
    pages = extract_text(pdf_path)
    statement_date_str, statement_month, statement_year = parse_statement_date(pages)
    summary = parse_summary(pages, statement_date_str, statement_year)
    transactions = parse_transactions(pages, statement_month, statement_year)
    data = {
        'summary': summary,
        'transactions': transactions
    }
    with open(output_json, 'w') as f:
        json.dump(data, f, indent=4)

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print("Usage: python extract_statement_pypdf.py <pdf_path> <output_json>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])