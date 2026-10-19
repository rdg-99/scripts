# PO Translation Toolbox

Python tool that splits and merges GNU gettext (.po) files to reduce CAT tool processing costs by sending only untranslated or fuzzy entries for translation.

## Use Case

Useful for localization projects involving large PO files with significant amounts of already translated content. Instead of processing the entire file in Phrase/Memsource, the script extracts only the entries requiring translation, reducing word processing quota usage and associated costs.

Once translated, the updated entries are merged back into the original PO files.

## Features

- Extracts untranslated and fuzzy entries into separate PO files.
- Merges translated entries back while preserving existing translations.
- Supports individual files, multiple files, and recursive folder processing.
- Handles plural forms and translation context.
- Matches entries by identifiers rather than file order.
- Validates translated entries before merging to prevent missing translations.
- Preserves the original folder structure and files.
- Supports interactive and command-line execution.

## Usage

Install the required dependency:

```bash
pip install polib
```

Run interactively:

```bash
python po-translation-toolbox.py
```

Or use command-line arguments:

```bash
python po-translation-toolbox.py split /path/to/files
python po-translation-toolbox.py merge /path/to/files
```

The script creates two folders:

- `_work` — PO files containing entries requiring translation.
- `_final` — Complete PO files with translated entries merged back.

## Development

This script is updated with improvements and new features as new requirements arise.
