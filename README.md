# EGRUL Scraper - Upgraded Version

## Overview

This upgraded version of the EGRUL scraper accepts text-based search queries (instead of INN numbers) and extracts structured data from **all search results** on the page.

**NEW**: The script now automatically separates **individual entrepreneurs** (ИП with ОГРНИП) into a separate CSV file containing only the raw text, while **legal entities** (with ОГРН) are parsed into structured fields.

**PAGINATION**: The script automatically navigates through all pages of search results and collects up to 500 records per query (configurable with `--max-records`).

**PDF DOWNLOADS**: Optionally downloads PDF documents for non-liquidated legal entities (use `--download-pdfs` flag). Liquidated entities are skipped to save time and storage.

## Key Changes from Original

### Input Format
- **Original**: Accepts INN numbers (10-12 digit numeric codes)
- **Upgraded**: Accepts any text search query (company names, person names, etc.)

### Output Format
- **Original**: Downloads PDF files for each INN
- **Upgraded**: Extracts structured data into a CSV file

### Processing
- **Original**: Processes only the first search result
- **Upgraded**: Processes ALL results across all pages (up to max-records limit)

## Output CSV Structure

The script generates **TWO separate CSV files**:

### 1. Legal Entities (Personnes Morales)
**File**: `egrul_results.csv` (default, configurable with `--output-file`)

Results with **ОГРН** (not ОГРНИП) are parsed into structured fields:

| Column | Description | Example |
|--------|-------------|---------|
| `search_query` | The original search text | "ООО Ромашка" |
| `entity_name` | Name of the entity from the search result | "Я-Я ИНТЕРНЕШНЛ АОЗТ" |
| `full_text` | Complete text from the result | "Г.Санкт-Петербург, ОГРН:..." |
| `region` | Text before the first comma | "Г.Санкт-Петербург" |
| `ogrn` | Numbers after "ОГРН" | "1127847079194" |
| `inn` | Numbers after "ИНН" | "7811513750" |
| `head_name` | Name of the head/director | "Мирошниченко Андрей Сергеевич" |
| `status` | "liquidated" or blank | "liquidated" |
| `stop_date` | Date after "Дата прекращения деятельности" | "16.06.2008" |
| `pdf_file` | Downloaded PDF filename (if `--download-pdfs` used) | "7811513750_20250115.pdf" |

## How Entity Types Are Distinguished

The script automatically identifies the type of entity based on the registration number:

- **ОГРН** (13 digits) → Legal Entity (Юридическое лицо) → Goes to `egrul_results.csv` with full parsing
- **ОГРНИП** (15 digits) → Individual Entrepreneur (ИП) → Goes to `egrul_entrepreneurs.csv` as raw text

This distinction is important because:
1. Legal entities have structured organizational data (directors, regions, legal status)
2. Individual entrepreneurs are simpler entities, often not requiring detailed parsing
3. Separating them keeps your legal entity analysis focused and clean

## Pagination Support

The script automatically handles multi-page search results:

### How It Works
1. After performing a search, the script detects the total number of result pages
2. It iterates through each page (1, 2, 3, ...) using the pagination links (`<a class="lnk-page" data-page="N">`)
3. Extracts all records from each page until reaching the `--max-records` limit
4. Default limit is 500 records per query (configurable for testing purposes)

### Why the Limit?
The 500-record default is set for the **testing stage** to:
- Avoid overwhelming the server with requests
- Allow faster testing and debugging
- Keep output files manageable during development

You can adjust this with `--max-records`:
```bash
# For production, increase the limit
python egrul_scraper_upgraded.py --input-file queries.csv --max-records 5000

# For quick testing, reduce it
python egrul_scraper_upgraded.py --input-file queries.csv --max-records 50
```

### Progress Tracking
The script provides detailed progress information:
- Number of pages detected
- Current page being processed
- Records extracted per page
- Total records collected when limit is reached

## PDF Download Feature

The script can optionally download PDF documents for legal entities using the `--download-pdfs` flag.

### Key Characteristics
1. **Only for Legal Entities**: PDFs are only downloaded for legal entities (with ОГРН), not for individual entrepreneurs
2. **Only Non-Liquidated**: Entities with status "liquidated" are automatically skipped to save time and storage
3. **Named by INN**: PDFs are renamed using the format `{INN}_{entity_name}.pdf` for easy identification
4. **Tracked in CSV**: The `pdf_file` column in the output CSV shows which PDF corresponds to each entity

### File Naming
PDFs are automatically renamed using a safe, consistent format:
- **Format**: `{INN}_{YYYYMMDD}.pdf`
- **Example**: `7811513750_20250115.pdf` (INN + download date)

Benefits of this format:
- **No Cyrillic characters**: Avoids encoding issues across different systems
- **Unique identifiers**: INN ensures each file is identifiable
- **Date tracking**: Shows when the document was downloaded
- **Safe for all systems**: Works reliably on Windows, Linux, macOS

If multiple PDFs are downloaded for the same INN on the same day, a timestamp is added: `7811513750_20250115_143022.pdf`

### Storage
PDFs are saved to the directory specified by `--pdf-dir` (default: `pdfs/` in the current directory).

### CSV Integration
The `pdf_file` column in the legal entities CSV will contain:
- The filename if PDF was downloaded successfully
- Empty string if entity is liquidated (no download attempted)
- Empty string if download failed

### Example
```bash
python egrul_scraper_upgraded.py \
    --input-file queries.csv \
    --download-pdfs \
    --pdf-dir company_documents
```

This will:
- Extract data to `egrul_results.csv` and `egrul_entrepreneurs.csv`
- Download PDFs for non-liquidated legal entities to `company_documents/`
- Record the PDF filename in the `pdf_file` column

## Data Extraction Logic

### Head Name Extraction
The script searches for various title patterns after the КПП field:
- ГЕНЕРАЛЬНЫЙ ДИРЕКТОР
- ДИРЕКТОР  
- руководитель юридического лица
- Any other title that follows КПП

### Status Determination
- **liquidated**: If "Дата прекращения деятельности" is present
- **blank**: Otherwise

### Stop Date
Extracted only when status is "liquidated"

### 2. Individual Entrepreneurs (Entrepreneurs Individuels / ИП)
**File**: `egrul_entrepreneurs.csv` (default, configurable with `--entrepreneurs-file`)

Results with **ОГРНИП** are stored in a simple format with only three columns:

| Column | Description | Example |
|--------|-------------|---------|
| `search_query` | The original search text | "ООО Ромашка" |
| `entity_name` | Name of the entrepreneur from the search result | "ИП Иванов Иван Иванович" |
| `full_text` | Complete raw text from the result | "ОГРНИП: 305690610400436, ИНН: 691900027385..." |

**Why separate?** Individual entrepreneurs are not in focus for legal entity analysis, so they're kept in a simple format for reference without detailed parsing.

**Note**: The `entity_name` field is extracted from the search result's caption (the text content between `<a>` and `</a>` tags in the `<div class="res-caption">` element), which displays the official name of the entity or entrepreneur as it appears in the registry.

## Usage

### Basic Usage

```bash
python egrul_scraper_upgraded.py --input-file queries.csv --output-file results.csv
```

This will create:
- `results.csv` - Legal entities with structured data
- `egrul_entrepreneurs.csv` - Individual entrepreneurs with raw text

### With Custom Entrepreneur File

```bash
python egrul_scraper_upgraded.py \
    --input-file queries.csv \
    --output-file legal_entities.csv \
    --entrepreneurs-file individual_entrepreneurs.csv
```

### With Custom Record Limit

```bash
# Collect up to 1000 records per query instead of default 500
python egrul_scraper_upgraded.py \
    --input-file queries.csv \
    --max-records 1000
```

### With PDF Downloads

```bash
# Download PDFs for non-liquidated entities
python egrul_scraper_upgraded.py \
    --input-file queries.csv \
    --download-pdfs

# Download PDFs to a custom directory
python egrul_scraper_upgraded.py \
    --input-file queries.csv \
    --download-pdfs \
    --pdf-dir my_pdfs
```

### With All Options

```bash
python egrul_scraper_upgraded.py \
    --input-file queries.csv \
    --output-file results.csv \
    --entrepreneurs-file entrepreneurs.csv \
    --max-records 500 \
    --download-pdfs \
    --pdf-dir pdfs \
    --column 0 \
    --headless \
    --chromedriver-path /path/to/chromedriver
```

### Command Line Arguments

- `--input-file`: Path to CSV file containing search queries (required)
- `--output-file`: Path for output CSV file with legal entities (default: `egrul_results.csv`)
- `--entrepreneurs-file`: Path for output CSV file with individual entrepreneurs (default: `egrul_entrepreneurs.csv`)
- `--max-records`: Maximum number of records to collect per query (default: 500, for testing)
- `--download-pdfs`: Enable PDF downloads for non-liquidated legal entities (flag, default: disabled)
- `--pdf-dir`: Directory for downloaded PDFs (default: `pdfs`)
- `--column`: Column index containing queries, 0-indexed (default: 0)
- `--headless`: Run Chrome in headless mode (no visible browser window)
- `--chromedriver-path`: Path to chromedriver executable (optional with Selenium 4.10+)

## Input File Format

The input CSV can have any structure. You specify which column contains the search queries using `--column`.

### Example 1: Single Column
```csv
search_query
ООО "Ромашка"
АО "Технология"
```

### Example 2: Multiple Columns
```csv
id,company_name,city
1,ООО "Ромашка",Москва
2,АО "Технология",Санкт-Петербург
```

To use the `company_name` column (index 1):
```bash
python egrul_scraper_upgraded.py --input-file companies.csv --column 1
```

## Example Results

For a search query like "Ромашка", if 2 legal entities and 1 individual entrepreneur are found:

### Legal Entities File (egrul_results.csv)
```csv
search_query,entity_name,full_text,region,ogrn,inn,head_name,status,stop_date
"Ромашка","ООО РОМАШКА","Г.Санкт-Петербург, ОГРН: 1127847079194...","Г.Санкт-Петербург","1127847079194","7811513750","Мирошниченко Андрей Сергеевич","",""
"Ромашка","АО РОМАШКА","Краснодарский край, ОГРН: 1082308006846...","Краснодарский край","1082308006846","2308023678","Аведисян Акоп Арутюнович","liquidated","16.06.2008"
```

### Individual Entrepreneurs File (egrul_entrepreneurs.csv)
```csv
search_query,entity_name,full_text
"Ромашка","ИП Петров Иван Иванович","ОГРНИП: 305690610400436, ИНН: 691900027385, Дата присвоения ОГРНИП: 14.04.2005, Дата прекращения деятельности: 01.01.2005"
```

## Requirements

```bash
pip install selenium tqdm
```

You'll also need Chrome/Chromium browser installed.

## Performance Notes

- The script includes automatic driver recovery mechanisms
- Pauses between requests to avoid overloading the server
- Checks driver health every 20 queries
- Handles session timeouts gracefully

## Error Handling

The script will:
- Retry failed searches up to 2 times
- Automatically refresh the driver if it becomes unresponsive
- Continue processing remaining queries even if some fail
- Report success/failure statistics at the end

## Differences from Original Script

1. **Selective PDF Downloads**: PDFs are only downloaded for non-liquidated legal entities (optional with `--download-pdfs`)
2. **Multiple Results**: All results for each query are captured across all pages
3. **Structured Output**: Data is parsed and organized into CSV fields alongside PDFs
4. **Text Input**: Accepts any search text, not just INN numbers
5. **Two Output Files**: Separates legal entities (with detailed parsing) from individual entrepreneurs (raw text only)
6. **Pagination**: Automatically navigates through all result pages (up to max-records limit)

## Migration from Original Script

If you were using the original script to:
```bash
python egrul_scraper.py --inn-file inns.csv --output-dir pdfs/
```

You can now use:
```bash
python egrul_scraper_upgraded.py --input-file inns.csv --output-file results.csv
```

The INN numbers will be used as search queries, but results will be structured data instead of PDFs.

## Notes

- The script uses the same reliable driver management from the original
- All existing safety features (rate limiting, error recovery) are preserved
- The regex patterns for data extraction handle various Russian text formats
- Empty fields are left blank in the CSV rather than using "N/A"
