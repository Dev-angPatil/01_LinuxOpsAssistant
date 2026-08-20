"""
Download Operations — Streaming file downloader with progress tracking,
filename resolution, and archive extraction for the Linux Ops Assistant.
"""

from __future__ import annotations

import os
import re
import shutil
import tarfile
import zipfile
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


def _expand_path(raw_path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name)
    name = re.sub(r'[^\w\.\-\_]', '_', name)
    return name or 'downloaded_file'


def extract_archive(archive_path: str, extract_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract standard archive formats (.zip, .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz).
    """
    p = _expand_path(archive_path)
    if not p.exists() or not p.is_file():
        return {
            'success': False,
            'archive': str(p),
            'error': f'Archive file not found: {p}',
            'action': 'extract_archive'
        }

    if extract_dir:
        out_dir = _expand_path(extract_dir)
    else:
        out_dir = p.parent / p.stem

    out_dir.mkdir(parents=True, exist_ok=True)
    extracted_files = []

    try:
        if zipfile.is_zipfile(p):
            with zipfile.ZipFile(p, 'r') as zf:
                for member in zf.infolist():
                    target_path = (out_dir / member.filename).resolve()
                    if not str(target_path).startswith(str(out_dir.resolve())):
                        raise ValueError(f'Zip slip detected in path: {member.filename}')
                zf.extractall(out_dir)
                extracted_files = zf.namelist()
        elif tarfile.is_tarfile(p):
            with tarfile.open(p, 'r:*') as tf:
                for member in tf.getmembers():
                    target_path = (out_dir / member.name).resolve()
                    if not str(target_path).startswith(str(out_dir.resolve())):
                        raise ValueError(f'Tar slip detected in path: {member.name}')
                tf.extractall(out_dir)
                extracted_files = [m.name for m in tf.getmembers()]
        else:
            return {
                'success': False,
                'archive': str(p),
                'error': 'Unsupported archive format. Supported formats: .zip, .tar.gz, .tar.bz2, .tar.xz, .tgz',
                'action': 'extract_archive'
            }

        return {
            'success': True,
            'archive': str(p),
            'destination': str(out_dir),
            'extracted_count': len(extracted_files),
            'files': extracted_files[:50],
            'message': f'Successfully extracted {len(extracted_files)} files to {out_dir}',
            'action': 'extract_archive'
        }
    except Exception as e:
        return {
            'success': False,
            'archive': str(p),
            'destination': str(out_dir),
            'error': str(e),
            'action': 'extract_archive'
        }


def download_file(
    url: str,
    destination_dir: str = '~/Downloads',
    filename: Optional[str] = None,
    auto_extract: bool = False,
    progress_callback: Optional[Callable[[int, int, float], None]] = None
) -> Dict[str, Any]:
    """
    Download a file from an HTTP/HTTPS URL with streaming chunk transfer.
    """
    clean_url = url.strip()
    if not clean_url.startswith(('http://', 'https://')):
        clean_url = 'https://' + clean_url

    dest_dir = _expand_path(destination_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) OpsAssistant/3.0'
    }

    try:
        req = urllib.request.Request(clean_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            if not filename:
                cd = resp.headers.get('Content-Disposition', '')
                cd_match = re.search(r'filename\*?=(?:UTF-8'')?"?([^;"]+)"?', cd, re.I)
                if cd_match:
                    filename = _sanitize_filename(cd_match.group(1))
                else:
                    parsed_path = urllib.parse.urlparse(clean_url).path
                    base_name = os.path.basename(parsed_path)
                    filename = _sanitize_filename(base_name) if base_name else 'downloaded_file'
            else:
                filename = _sanitize_filename(filename)

            total_size = int(resp.headers.get('Content-Length', 0))
            dest_file = dest_dir / filename

            counter = 1
            stem = dest_file.stem
            suffix = dest_file.suffix
            while dest_file.exists():
                dest_file = dest_dir / f'{stem}_{counter}{suffix}'
                counter += 1

            bytes_downloaded = 0
            chunk_size = 64 * 1024

            with open(dest_file, 'wb') as f_out:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    bytes_downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        pct = (bytes_downloaded / total_size) * 100
                        progress_callback(bytes_downloaded, total_size, pct)

            result = {
                'success': True,
                'url': clean_url,
                'file_path': str(dest_file),
                'filename': dest_file.name,
                'size_bytes': bytes_downloaded,
                'size_human': f'{bytes_downloaded / (1024 * 1024):.2f} MB' if bytes_downloaded >= 1024*1024 else f'{bytes_downloaded / 1024:.2f} KB',
                'message': f'Downloaded {dest_file.name} to {dest_dir}',
                'action': 'download_file'
            }

            if auto_extract and (zipfile.is_zipfile(dest_file) or tarfile.is_tarfile(dest_file)):
                extract_res = extract_archive(str(dest_file))
                result['extraction'] = extract_res

            return result

    except urllib.error.HTTPError as e:
        return {
            'success': False,
            'url': clean_url,
            'error': f'HTTP {e.code}: {e.reason}',
            'action': 'download_file'
        }
    except urllib.error.URLError as e:
        return {
            'success': False,
            'url': clean_url,
            'error': f'Network URL Error: {e.reason}',
            'action': 'download_file'
        }
    except Exception as e:
        return {
            'success': False,
            'url': clean_url,
            'error': str(e),
            'action': 'download_file'
        }