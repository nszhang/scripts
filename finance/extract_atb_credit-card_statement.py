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
    """Parse statement date from first page."""
    for page in pages:
        # Match "Statement date: January 13, 2025"
        match = re.search(r'Statement\s*date:\s*([A-Za-z]+)\s+(\d+),?\s*(\d{4})', page, re.IGNORECASE)
        if match:
            month_str, day, year = match.groups()
            month = datetime.strptime(month_str, '%B').month
            day = int(day)
            year = int(year)
            return f"{month_str} {day:02d}, {year}", month, year
    return "January 01, 1001", 1, 1

def parse_summary(page_text):
    """Parse account summary from the first page."""
    summary = {}
    
    # Statement date
    match = re.search(r'Statement\s*date:\s*([A-Za-z]+\s+\d+,?\s*\d{4})', page_text, re.IGNORECASE)
    if match:
        summary['StatementDate'] = match.group(1).strip()
    
    # Your previous balance
    match = re.search(r'Your previous balance\s*\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['PreviousBalance'] = match.group(1).replace(',', '')
    
    # Payments made
    match = re.search(r'Payments made.*?-?\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['Payments'] = '-' + match.group(1).replace(',', '')
    
    # Credits
    match = re.search(r'Credits\s*-?\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['Credits'] = '-' + match.group(1).replace(',', '')
    
    # Total payments and credits
    match = re.search(r'Total payments and credits\s*-?\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['TotalPaymentsAndCredits'] = '-' + match.group(1).replace(',', '')
    
    # Purchases and returns
    match = re.search(r'Purchases and returns\s*\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['PurchasesAndReturns'] = match.group(1).replace(',', '')
    
    # Cash advances and Mastercard cheques
    match = re.search(r'Cash advances and Mastercard cheques\s*\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['CashAdvances'] = match.group(1).replace(',', '')
    
    # Fees and adjustments
    match = re.search(r'Fees and adjustments\s*\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['FeesAndAdjustments'] = match.group(1).replace(',', '')
    
    # Interest charges
    match = re.search(r'Interest charges\s*\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['InterestCharges'] = match.group(1).replace(',', '')
    
    # Total new charges
    match = re.search(r'Total new charges\s*\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['TotalNewCharges'] = match.group(1).replace(',', '')
    
    # Your new balance
    match = re.search(r'Your new balance\s*\$?([\d,]+\.\d{2})', page_text)
    if match:
        summary['NewBalance'] = match.group(1).replace(',', '')
    
    return summary

def format_date(month_abbr, day, statement_month, statement_year):
    """Format date with proper year handling for year boundaries."""
    month_num = datetime.strptime(month_abbr, '%b').month
    day = int(day)
    year = statement_year
    # Handle year boundary cases
    if month_num == 1 and statement_month == 12:
        year += 1
    elif month_num == 12 and statement_month == 1:
        year -= 1
    return f"{month_abbr}-{day:02d}-{year}"

def parse_transactions(pages, statement_month, statement_year):
    """Parse transactions from all pages."""
    transactions = []
    
    # Pattern: Dec 12 Dec 13 DESCRIPTION 1,476.29
    # Date Charged, Date Posted, Description, Amount
    transaction_pattern = re.compile(
        r'([A-Z][a-z]{2})\s*(\d{1,2})\s+([A-Z][a-z]{2})\s*(\d{1,2})\s+(.+?)\s+([\d,]+\.\d{2})$'
    )
    
    for page in pages:
        lines = page.split('\n')
        for line in lines:
            line = line.strip()
            match = transaction_pattern.match(line)
            if match:
                charged_month, charged_day, posted_month, posted_day, description, amount = match.groups()
                
                tdate = format_date(charged_month, charged_day, statement_month, statement_year)
                pdate = format_date(posted_month, posted_day, statement_month, statement_year)
                
                # Clean amount
                amt_clean = amount.replace(',', '')
                
                transactions.append({
                    'tdate': tdate,
                    'pdate': pdate,
                    'description': description.strip(),
                    'amount': amt_clean
                })
    
    return transactions

def main(pdf_path, output_json):
    pages = extract_text(pdf_path)
    
    statement_date_str, statement_month, statement_year = parse_statement_date(pages)
    
    # Parse summary from first page
    summary = parse_summary(pages[0] if pages else "")
    if not summary.get('StatementDate'):
        summary['StatementDate'] = statement_date_str
    summary['StatementYear'] = statement_year
    
    # Parse transactions from all pages
    transactions = parse_transactions(pages, statement_month, statement_year)
    
    data = {
        'summary': summary,
        'transactions': transactions
    }
    
    with open(output_json, 'w') as f:
        json.dump(data, f, indent=4)
    
    print(f"Extracted {len(transactions)} transactions")
    print(f"Output saved to: {output_json}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print("Usage: python extract_atb_credit-card_statement.py <pdf_path> <output_json>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
