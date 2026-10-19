# UTF-8 BOM Switch

PowerShell utility to add or remove the UTF-8 Byte Order Mark (BOM) from files, or check their encoding without modifying them.

## Use Case

Useful in localization workflows where CAT tools, clients, or other systems require UTF-8 files with or without a BOM. It can fix BOM-related compatibility issues across multiple files without re-encoding their content.

## Features

- Adds or removes the UTF-8 BOM without changing the remaining file bytes.
- Checks file encoding in read-only mode.
- Processes a single file or multiple files filtered by extension in a folder.
- Skips UTF-16, UTF-32, and other non-UTF-8 files when adding a BOM.
- Asks for confirmation before modifying files.
- Displays per-file results and a processing summary.

## Usage

Run in PowerShell:

```powershell
.\utf8-bom-switch.ps1
```

Choose **Add BOM**, **Remove BOM**, or **Check encoding**, then enter a file or folder path. For folders, specify the file extension to process.

Changes are applied directly to the selected files. Make a backup if you need to retain the originals.
