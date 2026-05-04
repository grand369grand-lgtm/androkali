#!/usr/bin/env python3
"""
Patch Anroot bootstrap zips to replace com.termux with com.anroot.

This script processes bootstrap zip files and replaces all references to
com.termux with com.anroot in both text files (scripts, configs) and
ELF binaries (RPATH/RUNPATH entries).

Usage: python3 patch-bootstrap.py <zip_file> [zip_file ...]
"""

import os
import sys
import struct
import tempfile
import shutil
import zipfile

# The old and new package names
OLD_PREFIX = "com.termux"
NEW_PREFIX = "com.anroot"
OLD_PATH = "/data/data/com.termux"
NEW_PATH = "/data/data/com.anroot"


def is_elf(data):
    """Check if data starts with ELF magic bytes."""
    return data[:4] == b'\x7fELF'


def patch_elf_rpath(data):
    """
    Patch ELF binary RPATH/RUNPATH entries.
    Replace /data/data/com.termux with /data/data/com.anroot in .dynstr.
    
    Since the new path is shorter, we pad the remaining bytes with nulls.
    This is safe because C strings are null-terminated.
    """
    if not is_elf(data):
        return data
    
    old_bytes = OLD_PATH.encode('ascii')
    new_bytes = NEW_PATH.encode('ascii')
    
    # We need the replacement to be the same length for ELF structural integrity
    # Pad with null bytes since C strings are null-terminated
    if len(new_bytes) < len(old_bytes):
        padded_new = new_bytes + b'\x00' * (len(old_bytes) - len(new_bytes))
    else:
        padded_new = new_bytes[:len(old_bytes)]
    
    # Replace all occurrences of the old path with the padded new path
    patched = data.replace(old_bytes, padded_new)
    
    return patched


def patch_text(data):
    """
    Patch text files (scripts, configs) by replacing com.termux with com.anroot.
    For text files, the replacement can be shorter since there's no structural constraint.
    """
    try:
        text = data.decode('utf-8', errors='replace')
        # Replace the package name reference
        text = text.replace(OLD_PREFIX, NEW_PREFIX)
        # Also replace full paths
        text = text.replace(OLD_PATH, NEW_PATH)
        return text.encode('utf-8', errors='replace')
    except Exception:
        return data


def is_text_file(data, filename):
    """Determine if a file is likely a text file."""
    # Check by extension
    text_extensions = {
        '.sh', '.bash', '.zsh', '.py', '.pl', '.rb', '.conf', '.cfg',
        '.txt', '.md', '.xml', '.json', '.yaml', '.yml', '.toml',
        '.properties', '.list', '.sources', '.installs', '.control',
        '.desc', '.pro', '.cmake', '.pc', '.la', '.header',
    }
    _, ext = os.path.splitext(filename)
    if ext.lower() in text_extensions:
        return True
    
    # Check for shebang
    if data[:2] == b'#!':
        return True
    
    # Check if data contains null bytes (binary)
    if b'\x00' in data[:8192]:
        return False
    
    # Try to decode as UTF-8
    try:
        data[:8192].decode('utf-8')
        return True
    except (UnicodeDecodeError, ValueError):
        return False


def patch_zip(zip_path):
    """Patch a bootstrap zip file in place."""
    print(f"Patching {zip_path}...")
    
    # Read the original zip
    with zipfile.ZipFile(zip_path, 'r') as zf:
        entries = zf.infolist()
        patched_entries = {}
        
        for entry in entries:
            if entry.is_dir():
                continue
            
            data = zf.read(entry.filename)
            original_size = len(data)
            
            if is_elf(data):
                # Patch ELF binary
                patched_data = patch_elf_rpath(data)
                patch_type = "ELF"
            elif is_text_file(data, entry.filename):
                # Patch text file
                patched_data = patch_text(data)
                patch_type = "text"
            else:
                # For other binary files, try ELF-style byte replacement
                patched_data = data.replace(
                    OLD_PATH.encode('ascii'),
                    NEW_PATH.encode('ascii') + b'\x00' * (len(OLD_PATH) - len(NEW_PATH))
                )
                patched_data = patched_data.replace(
                    OLD_PREFIX.encode('ascii'),
                    NEW_PREFIX.encode('ascii') + b'\x00' * (len(OLD_PREFIX) - len(NEW_PREFIX))
                )
                patch_type = "binary"
            
            if patched_data != data:
                print(f"  Patched ({patch_type}): {entry.filename} ({original_size} bytes)")
            
            patched_entries[entry.filename] = patched_data
    
    # Write the patched zip
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            if entry.is_dir():
                zf.writestr(entry, b'')
            elif entry.filename in patched_entries:
                zf.writestr(entry, patched_entries[entry.filename])
            else:
                zf.writestr(entry, patched_entries.get(entry.filename, b''))
    
    print(f"Done patching {zip_path}")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <zip_file> [zip_file ...]")
        sys.exit(1)
    
    for zip_path in sys.argv[1:]:
        if not os.path.exists(zip_path):
            print(f"Error: {zip_path} not found")
            continue
        patch_zip(zip_path)


if __name__ == '__main__':
    main()
