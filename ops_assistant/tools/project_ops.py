"""
Project Operations — Auto-detect project manifests, install dependencies,
and manage Python virtual environments.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _expand_dir(raw_path: Optional[str] = None) -> Path:
    if not raw_path or raw_path.strip() in (".", ""):
        return Path(os.getcwd()).resolve()
    return Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()


def detect_project_type(target_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Inspects directory to detect project language, manifest files, and recommended package managers.
    """
    base = _expand_dir(target_dir)
    if not base.exists() or not base.is_dir():
        return {
            "success": False,
            "error": f"Target directory does not exist: {base}",
            "ecosystems": []
        }

    ecosystems: List[Dict[str, Any]] = []

    # 1. Python
    py_manifests = []
    for mf in ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "poetry.lock"):
        if (base / mf).exists():
            py_manifests.append(mf)
    if py_manifests:
        if (base / "requirements.txt").exists():
            install_cmd = f"{sys.executable} -m pip install -r requirements.txt"
        elif (base / "poetry.lock").exists() or ((base / "pyproject.toml").exists() and shutil.which("poetry")):
            install_cmd = "poetry install"
        elif (base / "Pipfile").exists() and shutil.which("pipenv"):
            install_cmd = "pipenv install"
        else:
            install_cmd = f"{sys.executable} -m pip install -e ."
        ecosystems.append({
            "language": "Python",
            "manifests": py_manifests,
            "installer": "pip",
            "recommended_command": install_cmd
        })

    # 2. Node.js / JavaScript / TypeScript
    if (base / "package.json").exists():
        manifests = ["package.json"]
        if (base / "pnpm-lock.yaml").exists() and shutil.which("pnpm"):
            inst = "pnpm"
            cmd = "pnpm install"
            manifests.append("pnpm-lock.yaml")
        elif (base / "yarn.lock").exists() and shutil.which("yarn"):
            inst = "yarn"
            cmd = "yarn install"
            manifests.append("yarn.lock")
        elif (base / "bun.lockb").exists() and shutil.which("bun"):
            inst = "bun"
            cmd = "bun install"
            manifests.append("bun.lockb")
        else:
            inst = "npm"
            cmd = "npm install"
            if (base / "package-lock.json").exists():
                manifests.append("package-lock.json")

        ecosystems.append({
            "language": "Node.js / JavaScript",
            "manifests": manifests,
            "installer": inst,
            "recommended_command": cmd
        })

    # 3. Rust
    if (base / "Cargo.toml").exists():
        ecosystems.append({
            "language": "Rust",
            "manifests": ["Cargo.toml"],
            "installer": "cargo",
            "recommended_command": "cargo build"
        })

    # 4. Go
    if (base / "go.mod").exists():
        ecosystems.append({
            "language": "Go",
            "manifests": ["go.mod"],
            "installer": "go",
            "recommended_command": "go mod download"
        })

    # 5. Ruby
    if (base / "Gemfile").exists():
        ecosystems.append({
            "language": "Ruby",
            "manifests": ["Gemfile"],
            "installer": "bundle",
            "recommended_command": "bundle install"
        })

    # 6. PHP
    if (base / "composer.json").exists():
        ecosystems.append({
            "language": "PHP",
            "manifests": ["composer.json"],
            "installer": "composer",
            "recommended_command": "composer install"
        })

    return {
        "success": True,
        "has_project": len(ecosystems) > 0,
        "language": ecosystems[0]["language"].lower() if ecosystems else "unknown",
        "manifest": ecosystems[0]["manifests"][0] if ecosystems and ecosystems[0].get("manifests") else None,
        "path": str(base),
        "ecosystems": ecosystems,
        "primary_ecosystem": ecosystems[0] if ecosystems else None,
        "detected_count": len(ecosystems)
    }


def install_project_dependencies(target_dir: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """
    Auto-detects project manifests and executes the appropriate dependency installer.
    """
    base = _expand_dir(target_dir)
    detected = detect_project_type(str(base))
    if not detected["success"]:
        return detected

    ecosystems = detected.get("ecosystems", [])
    if not ecosystems:
        return {
            "success": False,
            "path": str(base),
            "error": "No standard project manifest (requirements.txt, package.json, Cargo.toml, go.mod, etc.) found in directory.",
            "command": None
        }

    primary = ecosystems[0]
    cmd = primary["recommended_command"]

    res: Dict[str, Any] = {
        "success": True,
        "path": str(base),
        "language": primary["language"],
        "manifests": primary["manifests"],
        "command": cmd,
        "dry_run": dry_run,
        "output": None
    }

    if not dry_run:
        try:
            p = subprocess.run(
                cmd,
                shell=True,
                cwd=str(base),
                capture_output=True,
                text=True,
                timeout=180
            )
            res["returncode"] = p.returncode
            res["stdout"] = p.stdout
            res["stderr"] = p.stderr
            res["success"] = (p.returncode == 0)
            res["output"] = (p.stdout + "\n" + p.stderr).strip()
            res["summary"] = f"Installed {primary['language']} dependencies in {base} (exit code {p.returncode})."
        except Exception as e:
            res["success"] = False
            res["error"] = str(e)
            res["summary"] = f"Failed to install dependencies: {e}"
    else:
        res["summary"] = f"Ready to install {primary['language']} dependencies using '{cmd}' in {base}."

    return res


def create_python_venv(
    target_dir: Optional[str] = None,
    venv_name: str = "venv",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Creates an isolated Python virtual environment and returns activation commands.
    """
    base = _expand_dir(target_dir)
    venv_path = base / venv_name
    activate_script = venv_path / "bin" / "activate"
    cmd = f"{sys.executable} -m venv '{venv_path}'"

    res: Dict[str, Any] = {
        "success": True,
        "path": str(base),
        "venv_path": str(venv_path),
        "activate_command": f"source '{activate_script}'",
        "command": cmd,
        "dry_run": dry_run,
        "rollback_command": f"rm -rf '{venv_path}'"
    }

    if venv_path.exists():
        res["message"] = f"Virtual environment already exists at {venv_path}."
        res["summary"] = f"Virtual environment exists: {venv_path}. Activate with: source {activate_script}"
        return res

    if not dry_run:
        try:
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            res["returncode"] = p.returncode
            res["success"] = (p.returncode == 0)
            if p.returncode == 0:
                res["summary"] = f"Created Python virtual environment at {venv_path}. Activate with: source {activate_script}"
            else:
                res["error"] = p.stderr
                res["summary"] = f"Failed to create virtual environment: {p.stderr}"
        except Exception as e:
            res["success"] = False
            res["error"] = str(e)
            res["summary"] = f"Error creating virtual environment: {e}"
    else:
        res["summary"] = f"Ready to create Python virtual environment at {venv_path}."

    return res
