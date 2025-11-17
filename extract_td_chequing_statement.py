#!/usr/bin/env python3
"""
Extract transaction data from TD chequing bank statement PDF using pdfplumber.
Usage: python extract_td_chequing_statement_pdfplumber.py <pdf_path> <output_json>
"""

import sys
import json
import re
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("Error: pdfplumber is not installed. Install it with: pip install pdfplumber")
    sys.exit(1)


def extract_text(pdf_path):
    """Extract text from PDF using pdfplumber."""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
    return pages_text


def parse_header(pages):
    """Parse header information from the statement."""
    header = {}
    
    for page_text in pages:
        lines = page_text.split('\n')
        
        # Extract account holder name (typically after address lines)
        for i, line in enumerate(lines):
            # Look for MR/MS pattern
            if re.match(r'^(MR|MS|MRS|DR)[A-Z]+', line.strip()):
                header['AccountHolder'] = line.strip()
                break
        
        # Extract account type
        for line in lines:
            if 'ALLINCLUSIVE' in line or 'INCLUSIVE' in line:
                header['AccountType'] = 'ALL INCLUSIVE'
                break
            elif 'CHEQUING' in line.upper() or 'SAVINGS' in line.upper():
                match = re.search(r'([A-Z\s]+(CHEQUING|SAVINGS|CHECKING)[A-Z\s]*)', line, re.IGNORECASE)
                if match:
                    header['AccountType'] = match.group(1).strip()
                    break
        
        # Extract statement period
        # Format: "SEP 29/23-OCT31/23" or similar
        period_match = re.search(r'([A-Z]{3})\s*(\d+)/(\d{2})\s*-\s*([A-Z]{3})\s*(\d+)/(\d{2})', page_text, re.IGNORECASE)
        if period_match:
            month1, day1, year1, month2, day2, year2 = period_match.groups()
            year = 2000 + int(year2)
            header['StatementPeriod'] = f"{month1} {day1} - {month2} {day2}, {year}"
        else:
            # Try alternative format
            period_match = re.search(r'([A-Z][a-z]+)\s+(\d+)\s*-\s*([A-Z][a-z]+)\s+(\d+),\s*(\d{4})', page_text)
            if period_match:
                month1, day1, month2, day2, year = period_match.groups()
                header['StatementPeriod'] = f"{month1} {day1} - {month2} {day2}, {year}"
        
        # Extract branch number
        branch_match = re.search(r'Branch\s*No\.\s*(\d+)', page_text, re.IGNORECASE)
        if not branch_match:
            branch_match = re.search(r'(\d{4})\s+\d{4}-\d{7}', page_text)  # Pattern like "8181 8181-6258056"
        if branch_match:
            header['BranchNumber'] = branch_match.group(1)
        
        # Extract account number
        account_match = re.search(r'Account\s*No\.\s*(\d+[-\s]?\d+)', page_text, re.IGNORECASE)
        if not account_match:
            account_match = re.search(r'\d{4}\s+(\d{4}-\d{7})', page_text)  # Pattern like "8181 8181-6258056"
        if account_match:
            header['AccountNumber'] = account_match.group(1).replace(' ', '')
        
        # Break after first page for header info
        if header:
            break
    
    return header


def parse_transactions(pages, statement_period):
    """Parse transactions from the statement pages."""
    transactions = []
    
    # Extract year from statement period
    # Try to find 4-digit year first
    year_match = re.search(r'(\d{4})', statement_period) if statement_period else None
    if year_match:
        statement_year = int(year_match.group(1))
    else:
        # Try 2-digit year
        year_match = re.search(r'/(\d{2})', statement_period) if statement_period else None
        if year_match:
            statement_year = 2000 + int(year_match.group(1))
        else:
            statement_year = datetime.now().year
    
    for page_text in pages:
        lines = page_text.split('\n')
        
        transaction_started = False
        
        for line in lines:
            line_orig = line.strip()
            if not line_orig:
                continue
            
            # Check for transaction section start
            if re.search(r'(Description\s+Withdrawals?\s+Deposits?\s+Date\s+Balance)', line_orig, re.IGNORECASE):
                transaction_started = True
                continue
            
            # Check for starting balance
            if re.search(r'STARTINGBALANCE', line_orig, re.IGNORECASE):
                # Extract date and balance
                # Format: STARTINGBALANCE SEP29 9,597.75
                date_match = re.search(r'([A-Z]{3})(\d{1,2})', line_orig, re.IGNORECASE)
                balance_match = re.search(r'([\d,]+\.\d{2})$', line_orig)
                
                if date_match and balance_match:
                    month_abbr = date_match.group(1).upper()
                    day = date_match.group(2).zfill(2)
                    balance = balance_match.group(1).replace(',', '')
                    
                    transactions.append({
                        'date': f"{month_abbr}-{day}-{statement_year}",
                        'description': 'STARTING BALANCE',
                        'withdrawal': None,
                        'deposit': None,
                        'balance': balance
                    })
                continue
            
            # Check for closing balance - skip it as requested
            if re.search(r'CLOSINGBALANCE', line_orig, re.IGNORECASE):
                break
            
            # Parse regular transactions
            # Pattern with pdfplumber (cleaner): DESCRIPTION AMOUNT DATE [BALANCE]
            # Example: "MAXIMABAKERY _F 22.00 OCT03"
            # Example: "WY572TFR-FR0525308 82.00 OCT03"
            # Example: "CREDITMEMO 3,000.00 OCT03"
            
            if not transaction_started:
                continue
            
            # Look for lines with dates at the end (e.g., "OCT03", "SEP29")
            # Pattern: uppercase month + 1-2 digit day
            date_pattern = r'([A-Z]{3})(\d{1,2})(?:\s|$)'
            date_matches = list(re.finditer(date_pattern, line_orig))
            
            if len(date_matches) >= 1:
                # Use the last date as the transaction date
                last_date = date_matches[-1]
                month_abbr = last_date.group(1).upper()
                day = last_date.group(2).zfill(2)
                date_str = f"{month_abbr}-{day}-{statement_year}"
                
                # Extract everything before the last date
                before_date = line_orig[:last_date.start()].strip()
                # Extract everything after the last date (might be balance)
                after_date = line_orig[last_date.end():].strip()
                
                # Find all monetary amounts in the line
                amount_pattern = r'([\d,]+\.\d{2})'
                all_amounts = re.findall(amount_pattern, line_orig)
                
                if not all_amounts:
                    continue
                
                # Determine description and amounts
                # Typically: Description Amount Date [Balance]
                # Or: Description Date Balance
                
                # Find amounts before the date
                amounts_before_date = re.findall(amount_pattern, before_date)
                amounts_after_date = re.findall(amount_pattern, after_date)
                
                withdrawal = None
                deposit = None
                balance = None
                
                if amounts_before_date:
                    # First amount before date is the transaction amount
                    transaction_amount = amounts_before_date[0].replace(',', '')
                    
                    # Remove the transaction amount from before_date to get description
                    description = before_date
                    for amt in amounts_before_date:
                        description = description.replace(amt, '', 1).strip()
                    
                    # Check if it's a deposit or withdrawal based on description keywords
                    desc_upper = description.upper()
                    is_deposit = any(keyword in desc_upper for keyword in 
                                    ['CREDIT', 'DEPOSIT', 'TRANSFERTO', 'MEMO', 'E-TRANSFER', 'ETRANSFER'])
                    
                    if is_deposit:
                        deposit = transaction_amount
                    else:
                        withdrawal = transaction_amount
                    
                    # If there are more amounts, the last one is likely the balance
                    if len(amounts_before_date) > 1:
                        balance = amounts_before_date[-1].replace(',', '')
                    elif amounts_after_date:
                        balance = amounts_after_date[-1].replace(',', '')
                elif amounts_after_date:
                    # Amount is after the date (unusual but possible)
                    balance = amounts_after_date[0].replace(',', '')
                    description = before_date
                else:
                    description = before_date
                
                # Clean up description
                description = re.sub(r'\s+', ' ', description).strip()
                
                if description:  # Only add if we have a description
                    transactions.append({
                        'date': date_str,
                        'description': description,
                        'withdrawal': withdrawal,
                        'deposit': deposit,
                        'balance': balance
                    })
    
    return transactions


def parse_footer(pages):
    """Parse footer information (fees, rebates, etc.)."""
    footer = {}
    
    for page_text in pages:
        # Look for fees section
        fee_match = re.search(r'TOTAL\s+FEES[:\s]+([\d,]+\.\d{2})', page_text, re.IGNORECASE)
        if fee_match:
            footer['TotalFees'] = fee_match.group(1)
        
        # Look for rebates
        rebate_match = re.search(r'REBATE[:\s]+([\d,]+\.\d{2})', page_text, re.IGNORECASE)
        if rebate_match:
            footer['Rebate'] = rebate_match.group(1)
        
        # Look for issuer information
        if 'TD CANADA TRUST' in page_text:
            footer['Issuer'] = 'TD CANADA TRUST'
    
    return footer


def main(pdf_path, output_json):
    """Main function to extract and save statement data."""
    print(f"Extracting text from {pdf_path} using pdfplumber...")
    pages = extract_text(pdf_path)
    
    if not pages:
        print("Error: Could not extract text from PDF")
        sys.exit(1)
    
    print("Parsing header information...")
    header = parse_header(pages)
    
    print("Parsing transactions...")
    statement_period = header.get('StatementPeriod', '')
    transactions = parse_transactions(pages, statement_period)
    
    print("Parsing footer information...")
    footer = parse_footer(pages)
    
    # Combine all data
    data = {
        'header': header,
        'transactions': transactions,
        'footer': footer
    }
    
    # Save to JSON
    with open(output_json, 'w') as f:
        json.dump(data, f, indent=4)
    
    print(f"Extracted {len(transactions)} transactions from {pdf_path}")
    print(f"Output saved to {output_json}")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python extract_td_chequing_statement_pdfplumber.py <pdf_path> <output_json>")
        sys.exit(1)
    
    main(sys.argv[1], sys.argv[2])

