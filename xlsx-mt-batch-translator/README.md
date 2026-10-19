XLSX MT Batch Translator

Python script that performs batch machine translation of Excel files using the Google Cloud Translation API. Translates text across all columns while keeping the original workbook structure.

Use Case

Designed for projects where clients request raw machine translation (MT) only. In these scenarios, the script offers faster and more efficient processing than traditional CAT tools, while also saving CAT tool processing quotas.

It allows large volumes of Excel files to be translated directly through the API, avoiding unnecessary CAT tool workflows.

Features

Translates individual XLSX files or entire folders, including subfolders.

Processes text in batches with API rate limiting and automatic retries.

Skips numeric and symbol-only cells.

Preserves the original workbook structure and saves translated copies.

Supports language-aware word and character counting.

Tracks processing time, translation volume, and estimated API costs.

Generates detailed summaries and error logs for failed translations.

Displays progress bars during processing.

Usage

Install the required dependencies:

pip install pandas requests openpyxl tqdm

Add your Google Cloud Translation API key to the API_KEY variable in the script.

Run:

python xlsx-raw-mt-batch.py

Enter the XLSX file or folder path, source and target language codes, and whether to include subfolders.

Translated files are saved as filename_translated.xlsx, with summary reports and error logs generated alongside them.
