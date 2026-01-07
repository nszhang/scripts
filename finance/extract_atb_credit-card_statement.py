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
    """Parse transactions from all pages.
    
    Handles multi-line transactions where description spans multiple lines
    and amount appears on the last line.
    """
    transactions = []
    
    # Pattern for transaction start: "Nov 15 Nov 15 DESCRIPTION..."
    # May or may not have amount on same line
    transaction_start_pattern = re.compile(
        r'^([A-Z][a-z]{2})\s+(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(.+)$'
    )
    
    # Pattern for split date start: just "Sep 14" alone on a line
    split_date_start_pattern = re.compile(r'^([A-Z][a-z]{2})\s+(\d{1,2})$')
    
    # Pattern for amount at end of line (may be negative)
    amount_pattern = re.compile(r'(-?[\d,]+\.\d{2})$')
    
    for page in pages:
        lines = page.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Check for split date pattern (date on its own line)
            split_match = split_date_start_pattern.match(line)
            if split_match:
                charged_month, charged_day = split_match.groups()
                # Look ahead for posted date on next line
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    posted_match = split_date_start_pattern.match(next_line)
                    if posted_match:
                        posted_month, posted_day = posted_match.groups()
                        i += 2
                        # Now collect description and amount
                        description_parts = []
                        amount = None
                        while i < len(lines):
                            next_line = lines[i].strip()
                            if transaction_start_pattern.match(next_line) or split_date_start_pattern.match(next_line):
                                break
                            if next_line.startswith('Total ') or next_line.startswith('PURCHASES') or next_line.startswith('PAYMENTS'):
                                break
                            if not next_line:
                                i += 1
                                continue
                            
                            amt_match = amount_pattern.search(next_line)
                            if amt_match:
                                amount = amt_match.group(1)
                                desc_part = next_line[:amt_match.start()].strip()
                                if desc_part:
                                    description_parts.append(desc_part)
                                i += 1
                                break
                            else:
                                description_parts.append(next_line)
                            i += 1
                        
                        if amount:
                            tdate = format_date(charged_month, charged_day, statement_month, statement_year)
                            pdate = format_date(posted_month, posted_day, statement_month, statement_year)
                            amt_clean = amount.replace(',', '')
                            description = ' '.join(description_parts)
                            
                            transactions.append({
                                'tdate': tdate,
                                'pdate': pdate,
                                'description': description.strip(),
                                'amount': amt_clean
                            })
                        continue
            
            match = transaction_start_pattern.match(line)
            if match:
                charged_month, charged_day, posted_month, posted_day, rest = match.groups()
                
                # Check if amount is on this line
                amt_match = amount_pattern.search(rest)
                if amt_match:
                    amount = amt_match.group(1)
                    description = rest[:amt_match.start()].strip()
                else:
                    # Amount is on a subsequent line, collect description lines
                    description_parts = [rest]
                    amount = None
                    i += 1
                    while i < len(lines):
                        next_line = lines[i].strip()
                        # Stop if we hit another transaction start or section header
                        if transaction_start_pattern.match(next_line) or split_date_start_pattern.match(next_line):
                            break
                        if next_line.startswith('Total ') or next_line.startswith('PURCHASES') or next_line.startswith('PAYMENTS'):
                            break
                        if not next_line:
                            i += 1
                            continue
                        
                        # Check if this line ends with amount
                        amt_match = amount_pattern.search(next_line)
                        if amt_match:
                            amount = amt_match.group(1)
                            desc_part = next_line[:amt_match.start()].strip()
                            if desc_part:
                                description_parts.append(desc_part)
                            i += 1
                            break
                        else:
                            description_parts.append(next_line)
                        i += 1
                    
                    description = ' '.join(description_parts)
                    i -= 1  # Adjust since we'll increment at end of loop
                
                if amount:
                    tdate = format_date(charged_month, charged_day, statement_month, statement_year)
                    pdate = format_date(posted_month, posted_day, statement_month, statement_year)
                    amt_clean = amount.replace(',', '')
                    
                    transactions.append({
                        'tdate': tdate,
                        'pdate': pdate,
                        'description': description.strip(),
                        'amount': amt_clean
                    })
            i += 1
    
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
