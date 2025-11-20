#!/usr/bin/env python3
"""
TD Bank Chequing Statement PDF Extractor
Extracts transaction data from TD bank monthly chequing statements
"""

import re
import json
import sys
from pathlib import Path
import pdfplumber
from PyPDF2 import PdfReader


def extract_text_from_pdf(pdf_path):
    """Extract text content from PDF file or handle text content directly"""
    try:
        # Check if this is a text file (for testing with provided content)
        with open(pdf_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # If it starts with typical PDF content, it's a real PDF
            if content.startswith('%PDF'):
                # It's a real PDF, try PyPDF2 first for better space preservation
                return extract_with_pypdf2(pdf_path)
            else:
                # It's already extracted text content
                return content
    except UnicodeDecodeError:
        # Binary file, try as PDF
        return extract_with_pypdf2(pdf_path)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)


def extract_with_pypdf2(pdf_path):
    """Extract text from PDF using PyPDF2 for better space preservation"""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        # If PyPDF2 extraction is too sparse, fall back to pdfplumber
        if len(text.strip()) < 100:  # If very little text extracted
            return extract_with_pdfplumber(pdf_path)
            
        return text
    except Exception as e:
        print(f"Error with PyPDF2: {e}", file=sys.stderr)
        return extract_with_pdfplumber(pdf_path)


def extract_with_pdfplumber(pdf_path):
    """Extract text from PDF using pdfplumber as fallback"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
    except Exception as e:
        print(f"Error reading PDF: {e}", file=sys.stderr)
        sys.exit(1)


def clean_extracted_text(text):
    """Clean up text extracted from PDF that has spaces between characters"""
    # Check if text has excessive spacing (likely from PDF extraction)
    if ' ' in text and len(text) > 100:
        # Count ratio of spaces to characters
        space_ratio = text.count(' ') / len(text)
        if space_ratio > 0.3:  # More than 30% spaces indicates spaced-out text
            # Remove spaces between characters but preserve word boundaries
            # This is a heuristic approach for this specific PDF format
            text = re.sub(r'(?<=[a-zA-Z0-9])\s+(?=[a-zA-Z0-9])', '', text)
    
    return text


def parse_statement_summary(text):
    """Extract summary information from statement"""
    # Clean the text first
    text = clean_extracted_text(text)
    
    summary = {
        "statement_period": "",
        "account_number": "",
        "branch_number": ""
    }
    
    # Extract statement period (format: SEP29/23-OCT31/23)
    period_match = re.search(r'([A-Z]{3}\d{2}/\d{2}-[A-Z]{3}\d{2}/\d{2})', text)
    if period_match:
        summary["statement_period"] = period_match.group(1)
    
    # Extract account and branch numbers (format: 81818181-6258056)
    account_match = re.search(r'(\d{4})(\d{4}-\d{7})', text)
    if account_match:
        summary["branch_number"] = account_match.group(1)
        summary["account_number"] = account_match.group(2)
    
    return summary


def parse_transactions(text):
    """Parse transaction data from statement text"""
    transactions = []
    
    # Clean the text first
    text = clean_extracted_text(text)
    
    # Find the transaction table section
    # Look for the line with "DescriptionWithdrawalsDepositsDateBalance"
    table_start = text.find("DescriptionWithdrawalsDepositsDateBalance")
    if table_start == -1:
        return transactions
    
    # Get the transaction section (from table start to before summary totals)
    transaction_section = text[table_start:]
    
    # Split into lines and process
    lines = transaction_section.split('\n')
    
    # Skip the header line
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
            
        # Stop when we reach the totals or closing balance
        if "CLOSINGBALANCE" in line or "TOTALS" in line or "Account/TransactionTypeFees" in line:
            break
            
        # Skip starting balance line
        if "STARTINGBALANCE" in line:
            continue
            
        # Parse transaction line
        transaction = parse_transaction_line(line)
        if transaction:
            transactions.append(transaction)
    
    return transactions


def parse_transaction_line(line):
    """Parse a single transaction line with space-removed format"""
    # Pattern to match: Description[Reference][Amount]Date[Balance]
    # The date is always in format: OCT03, SEP29, etc (3 letters + 2 digits)

    # Find date pattern - this is our anchor
    date_pattern = r'([A-Z]{3}\d{2})'
    date_matches = list(re.finditer(date_pattern, line))

    if not date_matches:
        return None

    # Use the first date as the transaction date
    date_match = date_matches[0]
    date_str = date_match.group(1)

    # Everything before the date is description + amounts + references
    before_date = line[:date_match.start()]

    # Look for amount patterns: numbers with commas and 2 decimal places
    amount_pattern = r'[\d,]+\.\d{2}'
    amounts = re.findall(amount_pattern, before_date)

    if not amounts:
        # No amounts found, might be a description-only line
        return None

    # Convert all amounts to float values
    parsed_amounts = [(amt, float(amt.replace(',', ''))) for amt in amounts]

    # Sort by value to prioritize reasonable transaction amounts
    parsed_amounts.sort(key=lambda x: x[1])

    # Filter out obvious non-transaction amounts:
    # - Very large numbers (> 100,000) are likely balances or references
    # - Numbers starting with 0 followed by 7+ digits are references
    # - Keep amounts that look like normal banking transactions

    candidate_amounts = []
    for amt_str, amt_val in parsed_amounts:
        # Skip if it looks like a reference number
        if re.match(r'^0\d{7,}\.\d{2}$', amt_str):
            continue
        # Skip very large amounts (likely balances)
        if amt_val > 100000:
            continue
        candidate_amounts.append((amt_str, amt_val))

    if not candidate_amounts:
        # Skip lines with no reasonable amounts (only references or large numbers)
        return None
    else:
        # Take the first (smallest) candidate as the transaction amount
        transaction_amount_str, transaction_amount = candidate_amounts[0]

    # The description is everything before the transaction amount
    first_amount_pos = before_date.find(transaction_amount_str)
    if first_amount_pos == -1:
        return None

    description = before_date[:first_amount_pos].strip()

    # Clean up description - remove any trailing numbers/characters
    description = re.sub(r'[\d\-\*]+$', '', description)

    # Determine deposit or withdrawal based on description
    desc_upper = description.upper()

    # Deposits usually contain: CREDIT, MEMO, TFR-TO, E-TRANSFER, REBATE, TOC/C
    deposit_keywords = ['CREDIT', 'MEMO', 'TFR-TO', 'REBATE', 'TOC/C', 'E-TRANSFER']
    # Withdrawals usually contain: TFR-FR, W/D, PYMT, BAKERY, MASTRCRD, VISA, FEE
    withdrawal_keywords = ['TFR-FR', 'W/D', 'PYMT', 'BAKERY', 'MASTRCRD', 'VISA', 'FEE']

    deposit = None
    withdrawal = None

    if any(keyword in desc_upper for keyword in deposit_keywords):
        deposit = transaction_amount
    elif any(keyword in desc_upper for keyword in withdrawal_keywords):
        withdrawal = transaction_amount
    else:
        # Default logic for ambiguous cases
        if 'TFR' in desc_upper:
            # TFR-TO is deposit, TFR-FR is withdrawal
            if 'TFR-TO' in desc_upper:
                deposit = transaction_amount
            else:
                withdrawal = transaction_amount
        elif 'E-TRANSFER' in desc_upper:
            # E-TRANSFER is usually a deposit
            deposit = transaction_amount
        else:
            # Default to withdrawal for safety
            withdrawal = transaction_amount

    return {
        "date": date_str,
        "description": description,
        "deposits": deposit,
        "withdrawals": withdrawal
    }


def main():
    """Main function to process PDF and output JSON"""
    if len(sys.argv) < 2:
        print("Usage: python extract_td_chequing_statement.py <pdf_file> [output_file]", file=sys.stderr)
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(pdf_path).exists():
        print(f"Error: File '{pdf_path}' not found", file=sys.stderr)
        sys.exit(1)
    
    # Extract text from PDF
    print(f"Processing {pdf_path}...", file=sys.stderr)
    text = extract_text_from_pdf(pdf_path)
    
    # Debug: Print first 1000 characters of extracted text
    print("DEBUG: Extracted text sample:", file=sys.stderr)
    print(text[:1000], file=sys.stderr)
    print("..." + "="*50, file=sys.stderr)
    
    # Parse summary and transactions
    summary = parse_statement_summary(text)
    transactions = parse_transactions(text)
    
    # Create output structure
    output = {
        "summary": summary,
        "transactions": transactions
    }
    
    # Output as JSON
    json_output = json.dumps(output, indent=2)
    
    if output_path:
        # Save to file
        with open(output_path, 'w') as f:
            f.write(json_output)
        print(f"Output saved to {output_path}", file=sys.stderr)
    else:
        # Print to stdout
        print(json_output)


if __name__ == "__main__":
    main()