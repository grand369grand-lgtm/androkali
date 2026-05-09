#!/usr/bin/env python3
"""
Patch Anroot bootstrap zips to replace com.termux with com.anroot.

This script processes bootstrap zip files and replaces all references to
com.termux with com.anroot in both text files (scripts, configs) and
ELF binaries (RPATH/RUNPATH entries).

It also injects the libpath_remap.so LD_PRELOAD library and an
anroot-path.sh profile script for LD_PRELOAD persistence.

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

# Path to the pre-built libpath_remap.so files for each architecture
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATH_REMAP_LIBS = {
    "aarch64": os.path.join(SCRIPT_DIR, "libpath_remap_aarch64.so"),
    "arm": os.path.join(SCRIPT_DIR, "libpath_remap_arm.so"),
    "x86_64": os.path.join(SCRIPT_DIR, "libpath_remap_x86_64.so"),
    "x86": os.path.join(SCRIPT_DIR, "libpath_remap_x86.so"),
}

# Profile script for LD_PRELOAD persistence
# This ensures libpath_remap.so is always loaded, even after termux-exec
# sets its own LD_PRELOAD. The script appends our library to the existing
# LD_PRELOAD value if it's not already there.
ANROOT_PATH_PROFILE = """#!/data/data/com.anroot/files/usr/bin/sh
# Anroot path translation - ensure libpath_remap.so is in LD_PRELOAD
# This works alongside termux-exec's LD_PRELOAD library
if [ -f /data/data/com.anroot/files/usr/lib/libpath_remap.so ]; then
    case ":${LD_PRELOAD}:" in
        *":/data/data/com.anroot/files/usr/lib/libpath_remap.so:"*)
            # Already in LD_PRELOAD, do nothing
            ;;
        *)
            export LD_PRELOAD="/data/data/com.anroot/files/usr/lib/libpath_remap.so${LD_PRELOAD:+:$LD_PRELOAD}"
            ;;
    esac
fi
# Clear screen on Anroot startup
clear
"""

# The anubuntu script content
ANUBUNTU_SCRIPT = None  # Will be loaded from file if it exists

def load_anubuntu_script():
    """Load the anubuntu script if it exists."""
    global ANUBUNTU_SCRIPT
    anubuntu_path = os.path.join(SCRIPT_DIR, "anubuntu")
    if os.path.exists(anubuntu_path):
        with open(anubuntu_path, 'r') as f:
            ANUBUNTU_SCRIPT = f.read()
        print(f"  Loaded anubuntu script ({len(ANUBUNTU_SCRIPT)} bytes)")


def detect_arch_from_zip(zip_path):
    """Detect the architecture from the zip filename or contents."""
    basename = os.path.basename(zip_path)
    if "aarch64" in basename:
        return "aarch64"
    elif "x86_64" in basename or "x86-64" in basename:
        return "x86_64"
    elif "i686" in basename or "x86" in basename:
        return "x86"
    elif "arm" in basename:
        return "arm"
    
    # Try to detect from contents
    return None


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
    Also replaces standalone "Termux" with "Anroot" for branding, and termux.dev URLs.
    """
    try:
        text = data.decode('utf-8', errors='replace')
        # Replace the package name reference
        text = text.replace(OLD_PREFIX, NEW_PREFIX)
        # Replace full paths
        text = text.replace(OLD_PATH, NEW_PATH)
        # Replace branding: Termux -> Anroot (but not termux-* package names)
        # Only replace "Termux" when it appears as a standalone word (not in package names)
        import re
        # Replace "Termux" at word boundaries but NOT followed by a hyphen (package names like termux-exec)
        text = re.sub(r'(?<![a-zA-Z0-9_-])Termux(?![a-zA-Z0-9_-])', 'Anroot', text)
        # Replace termux.dev URLs
        text = text.replace('termux.dev/docs', 'crossberry.vercel.app')
        text = text.replace('termux.dev/donate', 'crossberry.vercel.app')
        text = text.replace('termux.dev/community', 'crossberry.vercel.app')
        text = text.replace('termux.dev/issues', 'github.com/grand369grand-lgtm/anroot/issues')
        text = text.replace('termux.dev', 'crossberry.vercel.app')
        # Replace wiki.termux.com
        text = text.replace('wiki.termux.com', 'crossberry.vercel.app')
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
    
    arch = detect_arch_from_zip(zip_path)
    print(f"  Detected architecture: {arch or 'unknown'}")
    
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
    
    # Inject libpath_remap.so if we have it for this architecture
    if arch and arch in PATH_REMAP_LIBS:
        lib_path = PATH_REMAP_LIBS[arch]
        if os.path.exists(lib_path):
            with open(lib_path, 'rb') as f:
                lib_data = f.read()
            lib_entry_name = "usr/lib/libpath_remap.so"
            patched_entries[lib_entry_name] = lib_data
            print(f"  Injected: {lib_entry_name} ({len(lib_data)} bytes) from {lib_path}")
        else:
            print(f"  WARNING: libpath_remap.so not found at {lib_path}")
    
    # Inject the anroot-path.sh profile script
    profile_data = ANROOT_PATH_PROFILE.encode('utf-8')
    profile_entry_name = "usr/etc/profile.d/anroot-path.sh"
    patched_entries[profile_entry_name] = profile_data
    print(f"  Injected: {profile_entry_name} ({len(profile_data)} bytes)")
    
    # Inject the anubuntu script if available
    if ANUBUNTU_SCRIPT:
        anubuntu_data = ANUBUNTU_SCRIPT.encode('utf-8')
        anubuntu_entry_name = "usr/bin/anubuntu"
        patched_entries[anubuntu_entry_name] = anubuntu_data
        print(f"  Injected: {anubuntu_entry_name} ({len(anubuntu_data)} bytes)")
    
    # Write the patched zip
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Write existing entries
        for entry in entries:
            if entry.is_dir():
                zf.writestr(entry, b'')
            elif entry.filename in patched_entries:
                zf.writestr(entry, patched_entries[entry.filename])
            else:
                zf.writestr(entry, b'')
        
        # Write new injected entries that don't exist in original
        existing_names = {e.filename for e in entries}
        for name, data in patched_entries.items():
            if name not in existing_names:
                # Create a new ZipInfo for injected files
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                # Set executable permissions for scripts
                if name.endswith('.sh') or name.endswith('/anubuntu'):
                    info.external_attr = 0o100755 << 16  # -rwxr-xr-x
                else:
                    info.external_attr = 0o100644 << 16  # -rw-r--r--
                zf.writestr(info, data)
    
    print(f"Done patching {zip_path}")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <zip_file> [zip_file ...]")
        sys.exit(1)
    
    # Load the anubuntu script
    load_anubuntu_script()
    
    for zip_path in sys.argv[1:]:
        if not os.path.exists(zip_path):
            print(f"Error: {zip_path} not found")
            continue
        patch_zip(zip_path)


if __name__ == '__main__':
    main()
