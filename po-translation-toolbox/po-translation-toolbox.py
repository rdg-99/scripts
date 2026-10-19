#!/usr/bin/env python3
r"""
po_toolkit.py — reduce Phrase/Memsource word-processing costs by splitting
.po files into a "work file" containing only untranslated/fuzzy strings,
sending that to translation, then merging the result back into a complete
.po file.

Usage:
    python po_toolkit.py                          (interactive prompt)
    python po_toolkit.py split  <path> [<path> ...]
    python po_toolkit.py merge  <path> [<path> ...]

Running with no arguments drops into an interactive prompt that asks for
split/merge and a file or folder path.

<path> can be:
  - a single .po file
  - multiple .po files
  - a directory (searched recursively for *.po files, skipping any
    _work or _final folders it finds along the way)

_work and _final folders are created INSIDE the given path itself (e.g.
<path>\_work, <path>\_final) — not relative to wherever you run the
script from.

Split:
    For each discovered original.po under <root>, writes a work file to
    <root>\_work\<relative-path-from-root>, containing only the entries
    that need translation. Fully-translated files produce no work file.

Merge:
    For each discovered original.po under <root>, looks for the matching
    file under <root>\_work\<relative-path>. Recomputes which entries
    needed translation (same rule as split), pulls their new msgstr from
    the work file, clears the fuzzy flag, and leaves every other entry
    untouched. Writes the complete result to <root>\_final\<relative-path>.

    Aborts (per file) if:
      - a key that was sent for translation is missing from the work file
      - the work file still has that key untranslated (empty msgstr)

    Warns (does not abort) if the work file contains extra keys that were
    never sent — those are ignored so nothing gets silently injected.

Matching key: (msgctxt, msgid, msgid_plural) — never line number or order,
since translation tools may reorder or restructure entries.

Requires: polib  (pip install polib --break-system-packages)
"""

import argparse
import logging
import sys
from pathlib import Path

try:
    import polib
except ImportError:
    sys.exit("This script requires 'polib'. Install with:\n"
              "    pip install polib --break-system-packages")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("po_toolkit")

WORK_DIR_NAME = "_work"
FINAL_DIR_NAME = "_final"
EXCLUDED_DIR_NAMES = {WORK_DIR_NAME, FINAL_DIR_NAME}


# ---------------------------------------------------------------------------
# Core rules — shared by split and merge so the definition of "needs work"
# can never drift between the two passes.
# ---------------------------------------------------------------------------

def needs_translation(entry: "polib.POEntry") -> bool:
    """True if this entry should be sent for translation.

    Obsolete entries never need translation — they're historical and are
    never touched by this tool in either direction.
    """
    if entry.obsolete:
        return False
    if entry.fuzzy:
        return True
    if entry.msgid_plural:
        return any(not (v or "").strip() for v in entry.msgstr_plural.values())
    return not (entry.msgstr or "").strip()


def entry_key(entry: "polib.POEntry"):
    """Stable identity for matching entries across files. Never use
    line number / order — translation tools may reorder entries."""
    return (entry.msgctxt, entry.msgid, entry.msgid_plural)


def entry_is_filled(entry: "polib.POEntry") -> bool:
    """True if this entry (as returned from the work file) actually has
    a translation now, regardless of any fuzzy flag the tool left on it."""
    if entry.msgid_plural:
        return all((v or "").strip() for v in entry.msgstr_plural.values())
    return bool((entry.msgstr or "").strip())


def clear_fuzzy(entry: "polib.POEntry") -> None:
    if "fuzzy" in entry.flags:
        entry.flags.remove("fuzzy")


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_po_files(input_paths):
    """Yields (root, po_file_path) pairs.

    root is the directory each po_file_path should be considered relative
    to, so mirrored output preserves folder structure. For a directory
    argument, root is that directory. For a single file argument, root is
    its parent.

    Skips anything inside a _work or _final folder, so re-running discovery
    over a parent directory doesn't pick up the tool's own output.
    """
    for raw in input_paths:
        p = Path(raw).resolve()
        if not p.exists():
            log.error("Path does not exist: %s", p)
            continue
        if p.is_dir():
            for po_path in sorted(p.rglob("*.po")):
                if EXCLUDED_DIR_NAMES & set(po_path.relative_to(p).parts[:-1]):
                    continue
                yield p, po_path
        elif p.suffix == ".po":
            yield p.parent, p
        else:
            log.warning("Skipping non-.po file: %s", p)


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------

def split_one(root: Path, po_path: Path, work_root: Path) -> None:
    original = polib.pofile(str(po_path))

    work_po = polib.POFile(wrapwidth=original.wrapwidth or 78)
    work_po.metadata = dict(original.metadata)

    count = 0
    for entry in original:
        if needs_translation(entry):
            work_po.append(entry)
            count += 1

    rel = po_path.relative_to(root)
    out_path = work_root / rel

    if count == 0:
        log.info("Fully translated, no work file needed: %s", rel)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_po.save(str(out_path))
    log.info("Wrote %d entries to work file: %s", count, out_path)


def cmd_split(args) -> int:
    any_found = False
    for root, po_path in discover_po_files(args.paths):
        any_found = True
        work_root = root / WORK_DIR_NAME
        split_one(root, po_path, work_root)
    if not any_found:
        log.error("No .po files found for the given path(s).")
        return 1
    return 0


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

class MergeAbort(Exception):
    pass


def merge_one(root: Path, po_path: Path, work_root: Path, final_root: Path) -> None:
    rel = po_path.relative_to(root)
    original = polib.pofile(str(po_path))

    sent_keys = {entry_key(e) for e in original if needs_translation(e)}
    work_path = work_root / rel

    if not sent_keys:
        # Nothing was sent for this file originally — it was already
        # complete. Just carry it through untouched.
        final_path = final_root / rel
        final_path.parent.mkdir(parents=True, exist_ok=True)
        original.save(str(final_path))
        log.info("No entries were sent; copied through untouched: %s", rel)
        return

    if not work_path.exists():
        raise MergeAbort(
            f"{rel}: expected work file at {work_path} but it does not exist "
            f"({len(sent_keys)} entries were sent for translation)."
        )

    work_po = polib.pofile(str(work_path))
    work_index = {}
    for entry in work_po:
        key = entry_key(entry)
        work_index[key] = entry

    # Extra entries in the work file that were never sent: warn, ignore.
    extra = set(work_index) - sent_keys
    for key in extra:
        log.warning("%s: work file has an entry that was never sent, ignoring: %r", rel, key)

    for entry in original:
        if entry.obsolete:
            continue
        if not needs_translation(entry):
            continue

        key = entry_key(entry)
        if key not in work_index:
            raise MergeAbort(f"{rel}: missing translation for entry {key!r}")

        w = work_index[key]
        if not entry_is_filled(w):
            raise MergeAbort(f"{rel}: work file still has entry untranslated: {key!r}")

        if entry.msgid_plural:
            entry.msgstr_plural = dict(w.msgstr_plural)
        else:
            entry.msgstr = w.msgstr
        clear_fuzzy(entry)

    final_path = final_root / rel
    final_path.parent.mkdir(parents=True, exist_ok=True)
    original.save(str(final_path))
    log.info("Merged and wrote complete file: %s", final_path)


def cmd_merge(args) -> int:
    any_found = False
    had_error = False
    for root, po_path in discover_po_files(args.paths):
        any_found = True
        work_root = root / WORK_DIR_NAME
        final_root = root / FINAL_DIR_NAME
        try:
            merge_one(root, po_path, work_root, final_root)
        except MergeAbort as e:
            had_error = True
            log.error("ABORTED %s", e)
    if not any_found:
        log.error("No .po files found for the given path(s).")
        return 1
    return 1 if had_error else 0


# ---------------------------------------------------------------------------

def prompt_interactive():
    print("PO Toolbox")
    print("----------")
    while True:
        choice = input("Choose action — [S]plit or [M]erge: ").strip().lower()
        if choice in ("s", "split"):
            command = "split"
            break
        if choice in ("m", "merge"):
            command = "merge"
            break
        print("Please enter 's' or 'm'.")

    while True:
        raw_path = input("Enter file or folder path: ").strip().strip('"').strip("'")
        if raw_path and Path(raw_path).exists():
            break
        print(f"Path not found: {raw_path!r} — try again.")

    return command, [raw_path]


def main():
    if len(sys.argv) == 1:
        command, paths = prompt_interactive()
        args = argparse.Namespace(paths=paths)
        func = cmd_split if command == "split" else cmd_merge
        result = func(args)
        input("\nDone. Press Enter to exit...")
        sys.exit(result)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_split = sub.add_parser("split", help="Extract untranslated/fuzzy entries into <path>/_work")
    p_split.add_argument("paths", nargs="+", help="File(s) or directory(ies) to process")
    p_split.set_defaults(func=cmd_split)

    p_merge = sub.add_parser("merge", help="Merge <path>/_work translations into <path>/_final")
    p_merge.add_argument("paths", nargs="+", help="Original file(s)/directory(ies) (same as used for split)")
    p_merge.set_defaults(func=cmd_merge)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
