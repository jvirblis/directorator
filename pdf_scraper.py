import os
import re
import csv
import glob
import logging
from PyPDF2 import PdfReader
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('egrul_parser.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file."""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted
        return text
    except Exception as e:
        logger.error(f"Error extracting text from {pdf_path}: {str(e)}")
        return ""

def clean_text(text):
    """Clean extracted text for better parsing."""
    # Replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text)
    # Remove non-breaking spaces
    text = text.replace('\xa0', ' ')
    return text

def extract_with_patterns(text, patterns):
    """Try multiple patterns to extract data."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            result = match.group(1).strip()
            # Remove extra whitespace and newlines
            result = re.sub(r'\s+', ' ', result)
            return result
    return None

def extract_date(text, patterns):
    """Extract date with format validation."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            date_str = match.group(1).strip()
            # Validate date format (DD.MM.YYYY)
            if re.match(r'\d{2}\.\d{2}\.\d{4}', date_str):
                return date_str
    return None

def clean_address(address_text):
    """Clean address text by removing header and trailing info."""
    if not address_text:
        return None
        
    # Remove header
    cleaned = re.sub(r'^Адрес\s+юридического\s+лица\s+', '', address_text)
    
    # Look for pattern with digit followed by GRN (both with and without spaces)
    # Using unicode escape sequences instead of Cyrillic letters directly
    grn_index1 = re.search(r'\d+\s+\u0413\u0420\u041d', cleaned)  # digit + space + ГРН
    grn_index2 = re.search(r'\d+\u0413\u0420\u041d', cleaned)     # digit + ГРН (no space)
    
    if grn_index1:
        cleaned = cleaned[:grn_index1.start()].strip()
    elif grn_index2:
        cleaned = cleaned[:grn_index2.start()].strip()
    
    return cleaned

def clean_location(location_text):
    """Clean location text by removing header and trailing info."""
    if not location_text:
        return None
        
    # Remove header
    cleaned = re.sub(r'^Место нахождения юридического лица\s+', '', location_text)
    
    # Look for pattern with digit followed by GRN (both with and without spaces)
    # Using unicode escape sequences instead of Cyrillic letters directly
    grn_index1 = re.search(r'\d+\s+\u0413\u0420\u041d', cleaned)  # digit + space + ГРН
    grn_index2 = re.search(r'\d+\u0413\u0420\u041d', cleaned)     # digit + ГРН (no space)
    
    if grn_index1:
        cleaned = cleaned[:grn_index1.start()].strip()
    elif grn_index2:
        cleaned = cleaned[:grn_index2.start()].strip()
    
    return cleaned

def parse_egrul_data(text, filename):
    """Parse EGRUL data from text with multiple pattern fallbacks."""
    
    # Clean up the text for better parsing
    text = clean_text(text)
    
    # Debug text length
    logger.debug(f"Text length for {filename}: {len(text)}")
    if len(text) < 100:  # If text is too short, likely failed extraction
        logger.warning(f"Very short text extracted from {filename} ({len(text)} chars)")
    
    data = {
        'filename': filename,
        'full_name': None,
        'ogrn': None,
        'inn': None,
        'address': None,
        'location': None,
        'responsible_person_name': None,
        'responsible_person_inn': None,
        'responsible_person_position': None,
        'responsible_person_approval_date': None,
        'founder_full_name': None,
        'founder_inn': None,
        'founder_ogrn': None,
        'founder_date': None
    }
    
    # Extract OGRN (registration number)
    ogrn_patterns = [
        r'ОГРН\s+(\d[\s\d]*\d)',
        r'(?:ОГРН|OGRN)[\s:]+(\d{13})',
        r'основной государственный регистрационный номер[\s:]+(\d{13})'
    ]
    
    ogrn_match = None
    for pattern in ogrn_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            ogrn_match = match.group(1)
            # Remove spaces if present
            ogrn_match = re.sub(r'\s', '', ogrn_match)
            data['ogrn'] = ogrn_match
            break
    
    # Extract full name from first paragraph
    # Look for the entity name at the beginning of the document
    full_name_patterns = [
        r'(?:настоящая выписка содержит сведения о юридическом лице\s+)(.+?)(?=\s+полное наименование|\s+ОГРН)',
        r'(?:полное наименование юридического лица\s+)(.+?)(?=\s+ОГРН)',
        r'^(?:.*?выписка.*?содержит.*?сведения.*?)\s+(.+?)(?=\s+(?:ОГРН|полное))',
        r'(?:Полное наименование на русском языке\s+)(.+?)(?=\s+\d+\s+ГРН)'
    ]
    
    for pattern in full_name_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            data['full_name'] = match.group(1).strip()
            break
    
    # If still not found, try a different approach - look for the header section
    if not data['full_name']:
        # Try to extract from the top section of the document
        top_section = text[:1000]  # Look only at the beginning of the document
        header_match = re.search(r'настоящая выписка содержит сведения о юридическом лице\s+(.*?)(?=\s+ОГРН|\s+полное наименование)', top_section, re.IGNORECASE | re.DOTALL)
        if header_match:
            data['full_name'] = header_match.group(1).strip()
    
    # Extract organization INN
    inn_patterns = [
        r'ИНН юридического лица\s+(\d{10})',
        r'ИНН\s+(\d{10})',
        r'ИНН[\s:]+(\d{10})'
    ]
    data['inn'] = extract_with_patterns(text, inn_patterns)
    
    # Extract legal address - clean up the format
    address_section = None
    address_section_patterns = [
        r'Адрес(?:\s+юридического\s+лица)?\s+(\d{6},\s+.*?)(?=\d+\s+ГРН)',
        r'Адрес(?:\s+юридического\s+лица)?\s+(.*?)(?=\d+\s+ГРН)',
    ]
    
    data['address'] = extract_with_patterns(text, address_section_patterns)
    data['address'] = clean_address(data['address'])
    
    # Extract location (Место нахождения)
    location_patterns = [
        r'Место нахождения юридического лица\s+(.*?)(?=\d+\s+ГРН)',
        r'Место нахождения\s+(.*?)(?=\d+\s+ГРН)'
    ]
    
    data['location'] = extract_with_patterns(text, location_patterns)
    data['location'] = clean_location(data['location'])
    
    # Find responsible person section
    responsible_section_patterns = [
        r'Сведения о лице, имеющем право без доверенности действовать от имени юридического\s+лица(.*?)(?:Сведения об участниках|$)',
        r'Сведения о лице, имеющем право без доверенности(.*?)(?:Сведения об участниках|$)',
        # Extended list of possible position titles
        r'(?:Руководитель|Директор|Генеральный директор|Исполнительный директор|Управляющий директор|'
        r'Президент|Вице-президент|Министр|Заместитель министра|Первый заместитель министра|'
        r'Губернатор|Мэр|Глава администрации|Председатель|Начальник|Заведующий)(.*?)(?:Сведения об участниках|$)'
    ]
    
    responsible_section = None
    for pattern in responsible_section_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            responsible_section = match.group(1)
            break
    
    if responsible_section:
        # Extract responsible person name based on row structure
        # First look for the specific case of "Фамилия Имя Отчество" followed by the actual name
        name_with_headers_pattern = r'Фамилия\s+Имя\s+Отчество\s+([А-ЯЁ]+)\s+([А-ЯЁ]+)\s+([А-ЯЁ]+)'
        name_match = re.search(name_with_headers_pattern, responsible_section, re.IGNORECASE)
        if name_match:
            last_name = name_match.group(1)
            first_name = name_match.group(2)
            middle_name = name_match.group(3)
            data['responsible_person_name'] = f"{last_name} {first_name} {middle_name}"
        
        # If not found with that pattern, try a different structure
        if not data['responsible_person_name'] or "Фамилия Имя Отчество" in data['responsible_person_name']:
            # Fix for the specific case where "Фамилия Имя Отчество" appears in the output
            pattern = r'Фамилия\s+Имя\s+Отчество\s*[\n\r]*([А-ЯЁ]+)\s+([А-ЯЁ]+)\s+([А-ЯЁ]+)'
            match = re.search(pattern, responsible_section, re.IGNORECASE | re.DOTALL)
            if match:
                data['responsible_person_name'] = f"{match.group(1)} {match.group(2)} {match.group(3)}"
            else:
                # Try to find name as a column next to "Фамилия Имя Отчество"
                column_pattern = r'Фамилия\s+Имя\s+Отчество\s*[\n\r]*\s*([А-ЯЁ]+)'
                column_match = re.search(column_pattern, responsible_section, re.IGNORECASE | re.DOTALL)
                if column_match:
                    # Now try to find the first name and patronymic on subsequent lines
                    last_name = column_match.group(1)
                    rest_section = responsible_section[column_match.end():]
                    
                    # Look for next two uppercase words, likely the first name and patronymic
                    names_match = re.search(r'([А-ЯЁ]+)\s+([А-ЯЁ]+)', rest_section, re.IGNORECASE)
                    if names_match:
                        first_name = names_match.group(1)
                        middle_name = names_match.group(2)
                        data['responsible_person_name'] = f"{last_name} {first_name} {middle_name}"
        
        # If still not found, try to find the line above INN
        if not data['responsible_person_name'] or "Фамилия Имя Отчество" in data['responsible_person_name']:
            # Find lines with INN
            inn_lines = re.findall(r'(.*?)\n.*?ИНН.*?(\d+)', responsible_section, re.IGNORECASE | re.DOTALL)
            if inn_lines:
                for line_before, inn in inn_lines:
                    # Look for name pattern in the line before INN
                    name_match = re.search(r'([А-ЯЁ]+)\s+([А-ЯЁ]+)\s+([А-ЯЁ]+)', line_before, re.IGNORECASE)
                    if name_match:
                        last_name = name_match.group(1)
                        first_name = name_match.group(2)
                        middle_name = name_match.group(3)
                        data['responsible_person_name'] = f"{last_name} {first_name} {middle_name}"
                        # Also save the INN we found
                        data['responsible_person_inn'] = inn.strip()
                        break
        
        # If name still not found, try another approach - look for a three-word name
        if not data['responsible_person_name'] or "Фамилия Имя Отчество" in data['responsible_person_name']:
            name_match = re.search(r'([А-ЯЁ][А-ЯЁа-яё]+)\s+([А-ЯЁ][А-ЯЁа-яё]+)\s+([А-ЯЁ][А-ЯЁа-яё]+)', responsible_section, re.IGNORECASE)
            if name_match:
                data['responsible_person_name'] = f"{name_match.group(1)} {name_match.group(2)} {name_match.group(3)}"
        
        # Extract responsible person's INN if not already found
        if not data['responsible_person_inn']:
            resp_inn_patterns = [
                r'ИНН\s+(\d+)',
                r'ИНН[\s:]+(\d+)'
            ]
            data['responsible_person_inn'] = extract_with_patterns(responsible_section, resp_inn_patterns)
        
        # Extract responsible person's position
        position_patterns = [
            r'Должность\s+(.+?)(?=\d+\s+ГРН)',
            r'Должность[\s:]+(.+?)(?=\d+\s+|\s+ИНН|\s+Сведения)',
            r'(?:Роль|Position)[\s:]+(.+?)(?=\d+\s+ГРН|\s+ИНН)'
        ]
        data['responsible_person_position'] = extract_with_patterns(responsible_section, position_patterns)
        
        # Extract responsible person's approval date
        approval_date_patterns = [
            r'ГРН и дата внесения в ЕГРЮЛ сведений о\s+данном лице\s+\d+\s+(\d{2}\.\d{2}\.\d{4})',
            r'внесения в ЕГРЮЛ записи(?:.+?)(\d{2}\.\d{2}\.\d{4})',
            r'Дата внесения в ЕГРЮЛ[\s:]+(\d{2}\.\d{2}\.\d{4})'
        ]
        data['responsible_person_approval_date'] = extract_date(responsible_section, approval_date_patterns)
    
    # Log missing data
    missing_fields = [field for field, value in data.items() if value is None and field != 'filename']
    if missing_fields:
        logger.warning(f"Missing fields in {filename}: {', '.join(missing_fields)}")
    
    # Extract founder information
    founder_section_patterns = [
        r'Сведения об участниках\s*[/]\s*учредителях юридического лица(.*?)(?:Сведения о записях|$)',
        r'Сведения об участниках\s*[/]\s*учредителях(.*?)(?:Сведения о записях|$)', 
        r'Сведения об учредителях юридического лица(.*?)(?:Сведения о записях|$)',
        r'Сведения об учредителях(.*?)(?:Сведения о записях|$)'
    ]
    
    founder_section = None
    for pattern in founder_section_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            founder_section = match.group(1)
            break
    
    if founder_section:
        # Extract founder full name
        founder_name_patterns = [
            r'(?:Участник\s*[/]\s*учредитель|Учредитель)\s+([^0-9\n]{5,}?)(?=\s*(?:\d+\s+ГРН|\n|$))',
            r'(?:Полное наименование|Наименование)\s+([^0-9\n]{5,}?)(?=\s*(?:\d+\s+ГРН|\n|$))',
            # Look for the name in a tabular format - last column after other data
            r'(?:\d+\s+ГРН[^\n]*\n[^\n]*\n[^\n]*\n)\s*([А-ЯЁ][^0-9\n]{10,}?)(?=\s*$)',
            # Simple pattern for organizational names
            r'([А-ЯЁ][^0-9\n]{15,}?)(?=\s*(?:ИНН|ОГРН))'
        ]
        
        data['founder_full_name'] = extract_with_patterns(founder_section, founder_name_patterns)
        
        # Clean up founder name if found
        if data['founder_full_name']:
            # Remove any heading text
            data['founder_full_name'] = re.sub(r'^(?:Участник\s*[/]\s*учредитель|Учредитель|Полное наименование|Наименование)\s+', 
                                             '', data['founder_full_name'])
            data['founder_full_name'] = data['founder_full_name'].strip()
        
        # Extract founder OGRN
        founder_ogrn_patterns = [
            r'ОГРН\s+(\d[\s\d]*\d)',
            r'(?:ОГРН|OGRN)[\s:]+(\d{13})',
            # Look for OGRN in table structure
            r'(?:Участник[^0-9]*?)ОГРН[^\n]*?(\d{13})',
            # Pattern for OGRN with spaces in the numbers
            r'ОГРН[^\n]*?(\d\s+\d\s+\d\s+\d\s+\d\s+\d\s+\d\s+\d\s+\d\s+\d\s+\d\s+\d\s+\d)'
        ]
        
        data['founder_ogrn'] = extract_with_patterns(founder_section, founder_ogrn_patterns)
        
        # Clean up founder OGRN by removing spaces if present
        if data['founder_ogrn']:
            data['founder_ogrn'] = re.sub(r'\s', '', data['founder_ogrn'])
        
        # Extract founder INN
        founder_inn_patterns = [
            r'(?:ИНН|INN)[\s:]+(\d{10})',
            r'ИНН\s+(\d{10})',
            # Look for INN in table structure
            r'(?:Участник[^0-9]*?)ИНН[^\n]*?(\d{10})',
        ]
        data['founder_inn'] = extract_with_patterns(founder_section, founder_inn_patterns)
        
        # Extract founder date when they became a founder
        founder_date_patterns = [
            # Look for dates in GRN records related to founders
            r'ГРН и дата внесения в ЕГРЮЛ сведений о\s+данном лице\s+\d+\s+(\d{2}\.\d{2}\.\d{4})',
            # Look for "создание" or "регистрация" dates in founder section
            r'(?:создание|регистрация)[^\n]*?(\d{2}\.\d{2}\.\d{4})',
            # General date pattern in the founder section
            r'внесения в ЕГРЮЛ записи[^\n]*?(\d{2}\.\d{2}\.\d{4})',
            # Look for dates near founder information
            r'(\d{2}\.\d{2}\.\d{4})',
        ]
        
        data['founder_date'] = extract_date(founder_section, founder_date_patterns)
        
        # If founder information is incomplete, try alternative extraction methods
        if not all([data['founder_full_name'], data['founder_ogrn'], data['founder_inn']]):
            # Try to extract from a different section structure
            # Look for founder info in numbered sections
            numbered_founder_match = re.search(r'(\d+)\s+Участник\s*[/]\s*учредитель\s+([^0-9\n]+)(?:\n|$)', 
                                             founder_section, re.IGNORECASE)
            if numbered_founder_match:
                data['founder_full_name'] = numbered_founder_match.group(2).strip()
                
                # Find corresponding OGRN and INN after the numbered entry
                after_name = founder_section[numbered_founder_match.end():]
                ogrn_after = re.search(r'ОГРН[^\n]*?(\d{13})', after_name[:500])
                inn_after = re.search(r'ИНН[^\n]*?(\d{10})', after_name[:500])
                
                if ogrn_after and not data['founder_ogrn']:
                    data['founder_ogrn'] = ogrn_after.group(1)
                if inn_after and not data['founder_inn']:
                    data['founder_inn'] = inn_after.group(1)
        
        # Special handling for cases where multiple founders might exist
        # For now, we extract the first one found
        
        logger.debug(f"Extracted founder info for {filename}: "
                    f"Name={data['founder_full_name']}, OGRN={data['founder_ogrn']}, "
                    f"INN={data['founder_inn']}, Date={data['founder_date']}")
    else:
        logger.warning(f"No founder section found in {filename}")
    
    return data

def process_file(pdf_file):
    """Process a single PDF file."""
    filename = os.path.basename(pdf_file)
    logger.info(f"Processing {filename}")
    
    try:
        text = extract_text_from_pdf(pdf_file)
        if not text:
            return {'filename': filename, 'error': 'Failed to extract text'}
        
        data = parse_egrul_data(text, filename)
        return data
    except Exception as e:
        logger.error(f"Error processing {filename}: {str(e)}")
        return {'filename': filename, 'error': str(e)}

def process_files(input_dir, output_file, max_workers=4):
    """Process all PDF files in the directory and write data to CSV."""
    # Get all PDF files
    pdf_files = glob.glob(os.path.join(input_dir, '*.pdf'))
    total_files = len(pdf_files)
    
    if total_files == 0:
        logger.warning(f"No PDF files found in {input_dir}")
        return 0, 0
    
    logger.info(f"Found {total_files} PDF files to process")
    
    # Set up the CSV file
    fieldnames = [
        'filename', 'full_name', 'ogrn', 'inn', 'address', 'location',
        'responsible_person_name', 'responsible_person_inn', 
        'responsible_person_position', 'responsible_person_approval_date',
        'founder_full_name', 'founder_inn', 'founder_ogrn', 'founder_date',
        'error'
    ]
    
    # Process files in parallel
    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        for result in tqdm(executor.map(process_file, pdf_files), total=total_files, desc="Processing PDFs"):
            results.append(result)
    
    # Write results to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        success_count = 0
        error_count = 0
        
        for data in results:
            # Remove 'error' field if not present
            if 'error' in data and not data['error']:
                del data['error']
                success_count += 1
            elif 'error' in data and data['error']:
                error_count += 1
            else:
                success_count += 1
                
            # Write to CSV
            writer.writerow(data)
        
    logger.info(f"Processing complete. Successfully processed: {success_count}, Errors: {error_count}")
    logger.info(f"Data saved to {output_file}")
    
    return success_count, error_count

if __name__ == "__main__":
    # Directory containing PDF files
    input_directory = "pdfs"
    
    # Output CSV file
    output_csv = "egrul_data.csv"
    
    logger.info("Starting to process EGRUL PDF files...")
    logger.info(f"Looking for files in: {input_directory}")
    
    # Check if directory exists
    if not os.path.exists(input_directory):
        logger.warning(f"Directory {input_directory} not found. Creating it...")
        os.makedirs(input_directory)
        logger.info(f"Please place your EGRUL PDF files in the {input_directory} directory and run this script again.")
    else:
        # Process files
        success, errors = process_files(input_directory, output_csv)
        logger.info(f"Processing complete! Successfully processed: {success}, Errors: {errors}")
        logger.info(f"Data saved to {output_csv}")
        logger.info(f"Check 'egrul_parser.log' for detailed processing information.")
