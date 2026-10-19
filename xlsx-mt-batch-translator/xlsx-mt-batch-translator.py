import pandas as pd
import requests
import time
import os
import re
import html
from openpyxl import load_workbook
from tqdm import tqdm

# --- Configuration ---
API_KEY = ""  # Replace with your key
REQUEST_TIMEOUT = 30  # API timeout in seconds
API_COST_PER_MILLION = 20.00  # Google Cloud Translation API cost per 1M characters

# --- HTML Entity Decoding Function ---
def decode_html_entities(text):
    """Decode HTML entities in text."""
    return html.unescape(text)

# --- Language-Aware Counting Functions ---
def uses_character_counting(language_code):
    """
    Check if language should be counted by characters instead of words.
    Languages without spaces between words (Chinese, Japanese, Korean, Thai, etc.)
    """
    character_counted_languages = [
        'zh', 'zh-CN', 'zh-TW',  # Chinese
        'ja',                     # Japanese
        'ko',                     # Korean
        'th'                      # Thai
    ]
    return language_code in character_counted_languages

def count_source_units(text, source_language):
    """
    Count appropriate units based on source language.
    For character-counted languages: count characters (excluding punctuation/spaces/numbers)
    For word-counted languages: count words by whitespace
    """
    clean_text = re.sub(r'[\s\d\W]', '', str(text))
    
    if uses_character_counting(source_language):
        # Count characters for languages without word spaces
        return len(clean_text)
    else:
        # Count words for languages with spaces
        return len(str(text).split())

def count_api_chars(text):
    """
    Count ALL characters sent to API (spaces, punctuation, everything).
    This is what Google bills for.
    """
    return len(str(text))

# --- Translation Functions ---
def translate_batch(texts, source_language, target_language):
    """Translate a batch of texts using Google Cloud Translation API."""
    url = "https://translation.googleapis.com/language/translate/v2"
    
    data = {
        "q": texts,
        "source": source_language,
        "target": target_language,
        "format": "text"
    }
    
    params = {"key": API_KEY}
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(
            url,
            params=params,
            json=data,
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        translated_texts = []
        for t in response.json()["data"]["translations"]:
            decoded_text = decode_html_entities(t["translatedText"])
            translated_texts.append(decoded_text)
        
        return translated_texts
    except requests.exceptions.RequestException as e:
        raise Exception(f"API request failed: {e}")

# --- Helper Functions ---
def is_non_translatable(text):
    """Check if a cell contains only numbers/symbols."""
    return bool(re.match(r'^[\W\d_]+$', str(text)))

def get_xlsx_files(input_path, recursive=False):
    """Get all XLSX files from a path (file or directory), optionally scanning subfolders."""
    if os.path.isfile(input_path):
        if input_path.lower().endswith('.xlsx'):
            return [input_path]
        else:
            print(f"Warning: {input_path} is not an XLSX file.")
            return []
    elif os.path.isdir(input_path):
        xlsx_files = []
        if recursive:
            for root, dirs, files in os.walk(input_path):
                for file in files:
                    if file.lower().endswith('.xlsx') and not file.startswith('~$'):
                        xlsx_files.append(os.path.join(root, file))
        else:
            for file in os.listdir(input_path):
                if file.lower().endswith('.xlsx') and not file.startswith('~$'):
                    xlsx_files.append(os.path.join(input_path, file))
        return xlsx_files
    else:
        print(f"Error: Path '{input_path}' does not exist.")
        return []

# --- Main Translation Function (for single file) ---
def translate_single_file(input_file, source_language, target_language, file_index=None, total_files=None):
    """
    Translate a single XLSX file (all columns).
    
    Args:
        input_file: Path to input XLSX file
        source_language: Source language code
        target_language: Target language code
        file_index: Current file number for progress display
        total_files: Total number of files for progress display
    """
    # Initialize counters
    source_units = 0  # Words/characters based on source language
    api_chars = 0     # Total characters sent to API (billing)
    failed_units = 0
    failed_api_chars = 0
    
    # Set up file paths
    input_dir = os.path.dirname(input_file)
    input_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(input_dir, f"{input_name}_translated.xlsx")
    log_file = os.path.join(input_dir, f"{input_name}_log.xlsx")

    # Load workbook
    try:
        wb = load_workbook(input_file)
        ws = wb.active
    except Exception as e:
        print(f"Error loading file {input_file}: {e}")
        return None
    
    log_data = []

    # --- Translation Process (all columns included) ---
    MAX_CHARS_PER_MINUTE = 3000000
    MAX_TEXTS_PER_BATCH = 32
    MAX_CHARS_PER_BATCH = 50000
    total_chars = 0
    start_time = time.time()
    file_start_time = time.time()  # Track file-specific timing

    # Prepare texts to translate (all columns)
    texts = []
    cell_refs = []
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and not is_non_translatable(cell.value):
                texts.append(cell.value)
                cell_refs.append(cell)

    # Skip if no translatable texts
    if not texts:
        print(f"No translatable text found in {os.path.basename(input_file)}. Skipping...")
        return {
            'file': os.path.basename(input_file),
            'source_units': 0,
            'api_chars': 0,
            'failed_units': 0,
            'failed_api_chars': 0,
            'total_source_units': 0,
            'total_api_chars': 0,
            'status': 'skipped'
        }

    # Process in batches with progress bar
    file_desc = f"File {file_index}/{total_files}" if file_index and total_files else os.path.basename(input_file)
    with tqdm(total=len(texts), desc=f"Translating {file_desc}", position=0, leave=True) as pbar:
        i = 0
        while i < len(texts):
            # Create batch
            batch = []
            batch_cells = []
            batch_chars = 0
            while i < len(texts) and len(batch) < MAX_TEXTS_PER_BATCH and batch_chars + len(texts[i]) <= MAX_CHARS_PER_BATCH:
                batch.append(texts[i])
                batch_cells.append(cell_refs[i])
                batch_chars += len(texts[i])
                i += 1

            # Rate limiting
            elapsed = time.time() - start_time
            if total_chars + batch_chars > MAX_CHARS_PER_MINUTE:
                delay = max(60 - elapsed, 0)
                if delay > 0:
                    print(f"\nRate limit: Waiting {delay:.1f}s...")
                    time.sleep(delay)
                total_chars = 0
                start_time = time.time()

            # Translate with retries
            translated = None
            for attempt in range(3):
                try:
                    translated = translate_batch(batch, source_language, target_language)
                    break
                except Exception as e:
                    print(f"\nAttempt {attempt + 1} failed: {e}")
                    if attempt < 2:  # Don't sleep on last attempt
                        time.sleep(2 ** attempt)

            # Update results
            if translated:
                for original_text, cell, translated_text in zip(batch, batch_cells, translated):
                    cell.value = translated_text
                    # Count source units (words or characters based on language)
                    source_units += count_source_units(original_text, source_language)
                    # Count API characters (all characters sent)
                    api_chars += count_api_chars(original_text)
            else:
                for original_text, cell in zip(batch, batch_cells):
                    log_data.append([cell.coordinate, original_text, "Failed"])
                    failed_units += count_source_units(original_text, source_language)
                    failed_api_chars += count_api_chars(original_text)

            total_chars += batch_chars
            pbar.update(len(batch))

    # Calculate file processing time
    file_elapsed = time.time() - file_start_time
    file_minutes = int(file_elapsed // 60)
    file_seconds = int(file_elapsed % 60)

    # Save results
    try:
        wb.save(output_file)
        if log_data:
            pd.DataFrame(log_data, columns=["Cell", "Original", "Translated"]).to_excel(log_file, index=False)
        
        total_source_units = source_units + failed_units
        total_api_chars = api_chars + failed_api_chars
        
        # Calculate API cost
        api_cost = (total_api_chars / 1_000_000) * API_COST_PER_MILLION
        
        # Print single file summary
        unit_label = "characters" if uses_character_counting(source_language) else "words"
        print(f"\n{'='*60}")
        print(f"TRANSLATION COMPLETE: {os.path.basename(input_file)}")
        print(f"{'='*60}")
        print(f"Source language: {source_language} → Target: {target_language}")
        print(f"Processing time: {file_minutes}m {file_seconds}s")
        print(f"\n📊 Source Statistics:")
        print(f"  → Total source {unit_label}: {total_source_units:,}")
        print(f"     - Translated: {source_units:,}")
        print(f"     - Failed: {failed_units:,}")
        print(f"\n💰 API Statistics:")
        print(f"  → Total characters sent: {total_api_chars:,}")
        print(f"     - Translated: {api_chars:,}")
        print(f"     - Failed: {failed_api_chars:,}")
        print(f"  → Estimated API cost: ${api_cost:.4f} USD")
        print(f"     (Google Cloud Translation API: ${API_COST_PER_MILLION}/million chars)")
        print(f"\n📁 Output files:")
        print(f"  → Translated file: {os.path.basename(output_file)}")
        if log_data:
            print(f"  → Error log: {os.path.basename(log_file)}")
        print(f"{'='*60}")
        
        # Save single file summary to log.txt
        parent_dir = input_dir
        log_file_summary = os.path.join(parent_dir, f"{input_name}_summary.txt")
        
        with open(log_file_summary, 'w', encoding='utf-8') as f:
            f.write("SINGLE FILE TRANSLATION SUMMARY\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Source language: {source_language}\n")
            f.write(f"Target language: {target_language}\n")
            f.write(f"Input file: {os.path.basename(input_file)}\n")
            f.write(f"Output file: {os.path.basename(output_file)}\n")
            f.write(f"Processing time: {file_minutes}m {file_seconds}s\n\n")
            f.write("Translation mode: ALL columns translated\n")
            f.write(f"Counting method: {'Characters' if uses_character_counting(source_language) else 'Words'}\n\n")
            
            f.write("SOURCE STATISTICS\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total source {unit_label}: {total_source_units:,}\n")
            f.write(f"  → Translated: {source_units:,}\n")
            f.write(f"  → Failed: {failed_units:,}\n\n")
            
            f.write("API STATISTICS\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total characters sent to API: {total_api_chars:,}\n")
            f.write(f"  → Translated: {api_chars:,}\n")
            f.write(f"  → Failed: {failed_api_chars:,}\n")
            f.write(f"Estimated API cost: ${api_cost:.4f} USD\n")
            f.write(f"(Google Cloud Translation API: ${API_COST_PER_MILLION}/million chars)\n\n")
            
            if log_data:
                f.write("ERROR LOG\n")
                f.write("-" * 40 + "\n")
                f.write(f"Failed translations: {len(log_data)}\n")
                f.write(f"Error log saved to: {os.path.basename(log_file)}\n")
        
        print(f"\n📄 Detailed summary saved to: {log_file_summary}")
        
        return {
            'file': os.path.basename(input_file),
            'source_units': source_units,
            'api_chars': api_chars,
            'failed_units': failed_units,
            'failed_api_chars': failed_api_chars,
            'total_source_units': total_source_units,
            'total_api_chars': total_api_chars,
            'api_cost': api_cost,
            'output': os.path.basename(output_file),
            'status': 'success'
        }
    except Exception as e:
        print(f"Error saving results for {input_file}: {e}")
        total_source_units = source_units + failed_units
        total_api_chars = api_chars + failed_api_chars
        api_cost = (total_api_chars / 1_000_000) * API_COST_PER_MILLION
        
        print(f"\n⚠️ Partial Summary (save failed):")
        unit_label = "characters" if uses_character_counting(source_language) else "words"
        print(f"  → Source {unit_label}: {total_source_units:,} total")
        print(f"  → API characters sent: {total_api_chars:,}")
        print(f"  → Estimated API cost: ${api_cost:.4f} USD")
        
        return {
            'file': os.path.basename(input_file),
            'source_units': source_units,
            'api_chars': api_chars,
            'failed_units': failed_units,
            'failed_api_chars': failed_api_chars,
            'total_source_units': total_source_units,
            'total_api_chars': total_api_chars,
            'api_cost': api_cost,
            'status': 'partial'
        }

# --- Batch Processing Function ---
def process_batch(input_path, source_language, target_language, recursive=False):
    """Process multiple XLSX files in batch mode (all columns translated)."""
    
    # Get list of XLSX files
    xlsx_files = get_xlsx_files(input_path, recursive=recursive)
    
    if not xlsx_files:
        print("No XLSX files found to process.")
        return
    
    print(f"\nFound {len(xlsx_files)} XLSX file(s) to process:")
    for i, file in enumerate(xlsx_files, 1):
        print(f"  {i}. {os.path.relpath(file, input_path)}")
    
    # Display counting method based on source language
    if uses_character_counting(source_language):
        print(f"\n📊 Counting method: Characters (character-counted language detected)")
    else:
        print(f"\n📊 Counting method: Words (word-counted language detected)")
    
    # Process all files
    results = []
    start_time = time.time()
    
    print(f"\n{'='*60}")
    print(f"Starting batch translation of {len(xlsx_files)} file(s)")
    print(f"Source: {source_language} → Target: {target_language}")
    print(f"{'='*60}\n")
    
    for idx, file_path in enumerate(xlsx_files, 1):
        print(f"\n[{idx}/{len(xlsx_files)}] Processing: {os.path.relpath(file_path, input_path)}")
        print("-" * 40)
        
        result = translate_single_file(
            file_path, 
            source_language, 
            target_language,
            file_index=idx,
            total_files=len(xlsx_files)
        )
        
        if result:
            results.append(result)
        
        # Add a small delay between files to avoid overwhelming the API
        if idx < len(xlsx_files):
            time.sleep(2)
    
    # Generate batch summary
    elapsed_time = time.time() - start_time
    minutes = int(elapsed_time // 60)
    seconds = int(elapsed_time % 60)
    
    print(f"\n{'='*60}")
    print("BATCH TRANSLATION COMPLETE")
    print(f"{'='*60}")
    print(f"Total files processed: {len(results)}")
    print(f"Total time: {minutes}m {seconds}s")
    print("\nDetailed Results:")
    print("-" * 70)
    
    total_source_units = 0
    total_api_chars = 0
    total_failed_units = 0
    total_failed_api_chars = 0
    successful_files = 0
    
    for r in results:
        status_icon = "✓" if r['status'] == 'success' else "⚠" if r['status'] == 'partial' else "✗"
        unit_label = "chars" if uses_character_counting(source_language) else "words"
        print(f"{status_icon} {r['file']}:")
        print(f"   → {r['source_units']:,} {unit_label} translated, {r['failed_units']:,} failed")
        print(f"   → API chars: {r['api_chars']:,} sent, {r['failed_api_chars']:,} failed")
        
        total_source_units += r['source_units']
        total_api_chars += r['api_chars']
        total_failed_units += r['failed_units']
        total_failed_api_chars += r['failed_api_chars']
        
        if r['status'] in ['success', 'partial']:
            successful_files += 1
    
    # Calculate API cost
    total_api_chars_all = total_api_chars + total_failed_api_chars
    api_cost = (total_api_chars_all / 1_000_000) * API_COST_PER_MILLION
    
    print("-" * 70)
    unit_label = "chars" if uses_character_counting(source_language) else "words"
    print(f"TOTALS:")
    print(f"  → Source {unit_label}: {total_source_units + total_failed_units:,} total")
    print(f"     - Translated: {total_source_units:,}")
    print(f"     - Failed: {total_failed_units:,}")
    print(f"  → API Characters Sent: {total_api_chars_all:,}")
    print(f"     - Translated: {total_api_chars:,}")
    print(f"     - Failed: {total_failed_api_chars:,}")
    print(f"  → Estimated API Cost: ${api_cost:.4f} USD")
    print(f"Successfully processed: {successful_files}/{len(results)} files")
    
    # Save batch summary to log.txt
    if len(xlsx_files) > 0:
        parent_dir = input_path if os.path.isdir(input_path) else os.path.dirname(input_path)
        log_file = os.path.join(parent_dir, "log.txt")
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("BATCH TRANSLATION SUMMARY\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Source language: {source_language}\n")
            f.write(f"Target language: {target_language}\n")
            f.write(f"Total files: {len(xlsx_files)}\n")
            f.write(f"Processing time: {minutes}m {seconds}s\n\n")
            f.write("Translation mode: ALL columns translated\n")
            f.write(f"Counting method: {'Characters' if uses_character_counting(source_language) else 'Words'}\n\n")
            
            f.write("Files processed:\n")
            for r in results:
                f.write(f"  - {r['file']}:\n")
                unit_label = "chars" if uses_character_counting(source_language) else "words"
                f.write(f"      {r['source_units']:,} {unit_label} translated, {r['failed_units']:,} failed\n")
                f.write(f"      {r['api_chars']:,} API chars sent, {r['failed_api_chars']:,} failed\n")
            
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"TOTAL SOURCE {unit_label.upper()}: {total_source_units + total_failed_units:,}\n")
            f.write(f"  → Translated: {total_source_units:,}\n")
            f.write(f"  → Failed: {total_failed_units:,}\n")
            f.write(f"TOTAL API CHARACTERS SENT: {total_api_chars_all:,}\n")
            f.write(f"  → Translated: {total_api_chars:,}\n")
            f.write(f"  → Failed: {total_failed_api_chars:,}\n")
            f.write(f"ESTIMATED API COST: ${api_cost:.4f} USD\n")
            f.write(f"(Google Cloud Translation API: ${API_COST_PER_MILLION}/million chars)\n")
        
        print(f"\n📄 Batch summary saved to: {log_file}")

# --- Run Script ---
if __name__ == "__main__":
    print("XLSX Raw MT Translator")
    print("=======================================================")
    input_path = input("Enter path to XLSX file OR folder containing XLSX files: ").strip('"')
    
    # Check if input is a file or folder
    if os.path.isfile(input_path) and input_path.lower().endswith('.xlsx'):
        print("\n--- Single File Mode ---")
        print("Language codes: https://cloud.google.com/translate/docs/languages")
        source_language = input("Enter source language code (e.g., 'zh-CN' for Chinese): ").strip()
        target_language = input("Enter target language code (e.g., 'en' for English): ").strip()
        translate_single_file(input_path, source_language, target_language)
    else:
        print("\n--- Batch Processing Mode ---")
        print("Language codes: https://cloud.google.com/translate/docs/languages")
        source_language = input("Enter source language code (e.g., 'zh-CN' for Chinese): ").strip()
        target_language = input("Enter target language code (e.g., 'en' for English): ").strip()
        recursive = input("Include subfolders? (y/n): ").strip().lower() == 'y'
        process_batch(input_path, source_language, target_language, recursive=recursive)