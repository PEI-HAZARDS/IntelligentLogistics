import re
import json
import csv
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    print("Note: PyPDF2 not installed. Using manual text input mode.")

def extract_from_pdf_file(pdf_path):
    """Extract text directly from PDF file using PyPDF2"""
    if not HAS_PYPDF2:
        raise ImportError("PyPDF2 required. Install with: pip install PyPDF2")
    
    text = ""
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text()
    return text

def extract_un_numbers(text):
    """
    Extract UN numbers and their corresponding descriptions from the PDF text.
    Returns a list of dictionaries with 'description' and 'un_code' keys.
    """
    entries = []
    
    # Split text into lines
    lines = text.split('\n')
    
    # Pattern to match entries: Description followed by UN/NA number (4 digits)
    pattern = r'^(.+?)\s+(\d{4})$'
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Try to match the pattern
        match = re.match(pattern, line)
        if match:
            description = match.group(1).strip()
            un_code = match.group(2).strip()
            
            # Filter out headers, page numbers, and invalid entries
            skip_keywords = ['Hazardous Materials', 'UN or NA', 'Code', 'CONTENTS']
            if (description and 
                not any(keyword in description for keyword in skip_keywords) and
                len(description) > 5):  # Minimum description length
                entries.append({
                    'un_code': un_code,
                    'description': description
                })
    
    # Remove duplicates while preserving order
    seen = set()
    unique_entries = []
    for entry in entries:
        key = f"{entry['un_code']}:{entry['description']}"
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)
    
    return unique_entries

def save_to_json(data, filename='un_numbers.json'):
    """Save extracted data to JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data)} entries to {filename}")

def save_to_csv(data, filename='un_numbers.csv'):
    """Save extracted data to CSV file"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['un_code', 'description'])
        writer.writeheader()
        writer.writerows(data)
    print(f"Saved {len(data)} entries to {filename}")

def save_to_txt(data, filename='un_numbers.txt'):
    """Save extracted data to plain text file"""
    with open(filename, 'w', encoding='utf-8') as f:
        for entry in data:
            f.write(f"{entry['un_code']}|{entry['description']}\n")
    print(f"Saved {len(data)} entries to {filename}")

def save_to_sql_insert(data, table_name='un_numbers', filename='un_numbers.sql'):
    """Generate SQL INSERT statements"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"-- SQL INSERT statements for {table_name}\n")
        f.write(f"-- CREATE TABLE {table_name} (un_code VARCHAR(10) PRIMARY KEY, description TEXT);\n\n")
        
        for entry in data:
            # Escape single quotes in description
            desc = entry['description'].replace("'", "''")
            f.write(f"INSERT INTO {table_name} (un_code, description) VALUES ('{entry['un_code']}', '{desc}');\n")
    
    print(f"Saved {len(data)} SQL INSERT statements to {filename}")

# Main execution
if __name__ == "__main__":
    import sys
    
    # Check if PDF file path is provided
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        print(f"Extracting from PDF: {pdf_path}")
        pdf_text = extract_from_pdf_file(pdf_path)
    else:
        print("No PDF file provided. Please provide text manually or specify PDF path.")
        print("Usage: python extract.py <path_to_pdf>")
        sys.exit(1)
    
    # Extract the data
    un_data = extract_un_numbers(pdf_text)
    
    # Display first few entries as preview
    print(f"\nExtracted {len(un_data)} UN number entries\n")
    print("First 5 entries:")
    for entry in un_data[:5]:
        print(f"  {entry['un_code']}: {entry['description']}")
    
    # Save in multiple formats
    print("\nSaving data in multiple formats...")
    save_to_json(un_data)
    save_to_csv(un_data)
    save_to_txt(un_data)
    save_to_sql_insert(un_data)
    
    print("\nDone! Files created:")
    print("  - un_numbers.json (for APIs/NoSQL databases)")
    print("  - un_numbers.csv (for spreadsheets/imports)")
    print("  - un_numbers.txt (pipe-delimited text)")
    print("  - un_numbers.sql (SQL INSERT statements)")