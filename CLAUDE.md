# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MetallibSupportPkg patches macOS Metal shader libraries (`.metallib`) to restore support for Metal 3802-based GPUs (Intel Ivy Bridge/Haswell iGPUs, Nvidia Kepler dGPUs) on macOS Sequoia (15.x) and macOS 26. Part of the Dortania/OpenCore Legacy Patcher ecosystem.

## Commands

```bash
# Install dependencies (requires Xcode for metal, metal-objdump, metallib, xcrun)
python3 -m pip install -r requirements.txt

# Full pipeline steps:
python3 metallib.py -d                          # Download latest IPSW (both macOS 15 and 26)
python3 metallib.py -d --os-version 15          # Download macOS 15 only
python3 metallib.py -d --os-version 26          # Download macOS 26 only
python3 metallib.py -e <ipsw_path>              # Extract system volume DMG
python3 metallib.py -f <dmg_path>               # Fetch .metallib files → outputs <version>-<build>/
python3 metallib.py -p <metallib_dir_or_file>   # Patch metallib files
python3 metallib.py -b <metallib_dir>           # Generate sys_patch_dict.py
python3 metallib.py -z <metallib_dir>           # Build signed .pkg

# CI mode (skips already-released builds):
python3 metallib.py -d -c --os-version 15

# Custom -mmacos-version-min for recompilation:
python3 metallib.py -p <dir> --mmacos-version-min 15.0
```

There are no tests in this project. No linter is configured.

## Architecture

Entry: `metallib.py` → `metal_libraries.main()` (cli.py) — argparse-based CLI dispatching to pipeline stages.

### Pipeline (sequential stages)

1. **IPSW Fetch** (`ipsw/fetch.py`): Queries AppleDB API for latest macOS IPSWs/OTAs targeting VirtualMac2,1. Supports multiple version ranges (15.x and 26.x) via `os_versions` parameter. Deduplicates builds, prefers IPSWs over OTAs and releases over betas. `MacPro7,1` device filter is only applied for macOS < 26. Updates `deploy/manifest.json` via `ipsw/manifest.py`.

2. **IPSW Extract** (`ipsw/extract.py`): Two code paths — `IPSWExtract` (zip-based IPSW) and `OTAExtract` (Apple Archive payloads). Both handle AEA decryption via bundled `ipsw/bins/aastuff` binary. OTA extraction uses `/usr/bin/aa` and manually resolves hardlinks from `links.txt`.

3. **Metallib Fetch** (`metallib/fetch.py`): Walks `System/Library`, `System/Applications`, `System/iOSSupport` (excluding `Extensions/` and symlinks). Skips known-broken files using broad prefix matching (e.g., `GPUCompiler.framework/Versions/` to handle version changes across macOS versions). Reads `SystemVersion.plist` to build output directory name `<version>-<build>`.

4. **Metallib Patch** (`metallib/patch.py`): The core logic, per-file:
   - **Thin** FAT Mach-O → extract AIR64 slice (custom parser, Apple's `lipo` doesn't support AIR64)
   - **Unpack** `.metallib` → individual `.air` (custom MTLB binary format parser with diagnostic logging for unknown format versions)
   - **Decompile** `.air` → `.ll` via `xcrun metal-objdump --disassemble`
   - **Patch** LLVM IR using regex-based matching: downgrade any AIR version > 2.6 to 2.6, any Metal SDK > 3.1 to 3.1, simplify sampler state arrays of any size
   - **Recompile** `.ll` → `.air` via `xcrun metal -c -mmacos-version-min=<configurable>` (default 14.0)
   - **Repack** `.air` → `.metallib` via `xcrun metallib`

5. **Package Build** (`cli.py:build_pkg`): Uses `macos-pkg-builder` to create distribution PKG, optionally signs and notarizes via `mac_signing_buddy`.

### Supporting modules

- `network/` — `NetworkUtilities` (requests wrapper), `DownloadObject` (threaded download with progress/checksum)
- `utils/download.py` — `DownloadFile` high-level download with SHA1 verification
- `utils/mount.py` — `MountDMG` context manager (`hdiutil attach/detach`)
- `utils/patch_format.py` — Generates sys_patch_dict for OCLP integration
- `utils/ci_info.py` — Queries GitHub Releases API to skip already-published builds

## CI

GitHub Actions workflow (`.github/workflows/patch.yml`) runs every 3 hours on `macos-latest` with Python 3.11. Uses a matrix strategy to build for both macOS 15 (Sequoia) and macOS 26 in parallel. Runs the full pipeline, uploads PKG + sys_patch_dict.py + manifest.json as artifacts, creates GitHub releases on main, and deploys manifest to gh-pages.

## Key constraints

- Requires macOS with Xcode installed (for Metal compiler toolchain under `/usr/bin/xcrun`)
- macOS 26 support may require a newer Xcode version with macOS 26 SDK
- Some metallib files are known-broken and skipped in `metallib/fetch.py` (broad prefix matching) and `metallib/patch.py` (per-function skip list)
- The MTLB binary format parser and FAT Mach-O thinner are custom implementations — handle with care when modifying
- macOS 26 AIR/Metal SDK versions are discovered dynamically via regex; unknown MTLB format versions trigger warnings instead of crashes
