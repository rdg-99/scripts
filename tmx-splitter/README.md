# TMX Splitter by Date

Python script that filters TMX (Translation Memory eXchange) files by date, creating new files containing only translation units (TUs) created or modified on or after a specified date.

## Use Case

Useful when clients require ownership of their translated content and regular TM deliveries. Instead of sending the entire Translation Memory every quarter, which can be several GB in size, this script generates smaller TMX files containing only new or updated entries since the last delivery.

## Features

- Batch processes multiple TMX files in a folder.
- Filters translation units using creation or modification dates.
- Checks TUV-level dates when TU-level dates are unavailable.
- Preserves the original TMX header.
- Displays progress bars for individual files and overall processing.
- Saves filtered files alongside the originals without modifying them.

## Usage

Install the required dependency:

```bash
pip install tqdm
```

Run the script:

```bash
python TMX_Splitter.py
```

Enter the folder containing the TMX files and the cutoff date in `YYYY/MM/DD` format.

Output files are saved as `filename_after_YYYYMMDD.tmx`.

## Development

This script is continuously improved with updates and new features as new requirements arise.
