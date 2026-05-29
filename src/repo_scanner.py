"""
RepoScannerAgent
Clones public GitHub repos, inventories Python and SQL files,
prioritizes by complexity for downstream analysis
"""
import os
import ast
import shutil
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
import sqlparse


@dataclass
class FileInventory:
    path: str
    language: str
    size_bytes: int
    line_count: int
    complexity_score: float
    content: str


@dataclass
class RepoInventory:
    repo_url: str
    repo_name: str
    clone_path: str
    python_files: List[FileInventory] = field(default_factory=list)
    sql_files: List[FileInventory] = field(default_factory=list)
    total_files: int = 0
    errors: List[str] = field(default_factory=list)


def _python_complexity(content: str) -> float:
    """Estimate complexity via AST node count"""
    try:
        tree = ast.parse(content)
        nodes = sum(1 for _ in ast.walk(tree))
        functions = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        return round((nodes * 0.1) + (functions * 2.0) + (classes * 3.0), 2)
    except Exception:
        return 0.0


def _sql_complexity(content: str) -> float:
    """Estimate SQL complexity via statement and keyword count"""
    try:
        statements = sqlparse.parse(content)
        score = 0.0
        keywords = ["JOIN", "SUBQUERY", "WITH", "UNION", "HAVING", "WINDOW", "OVER", "PARTITION"]
        upper = content.upper()
        for kw in keywords:
            score += upper.count(kw) * 1.5
        score += len(statements) * 0.5
        return round(score, 2)
    except Exception:
        return 0.0


def scan_repo(repo_url: str, max_files: int = 30, clone_dir: Optional[str] = None) -> RepoInventory:
    """
    Clone a public GitHub repo and inventory Python and SQL files.
    Returns RepoInventory sorted by complexity (highest first).
    """
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    clone_path = clone_dir or tempfile.mkdtemp(prefix=f"cra_{repo_name}_")

    print(f"[RepoScanner] Cloning {repo_url} → {clone_path}")

    inventory = RepoInventory(
        repo_url=repo_url,
        repo_name=repo_name,
        clone_path=clone_path,
    )

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, clone_path],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            inventory.errors.append(f"Clone failed: {result.stderr.strip()}")
            return inventory
    except Exception as e:
        inventory.errors.append(f"Clone error: {e}")
        return inventory

    print(f"[RepoScanner] Clone complete. Scanning files...")

    py_files = list(Path(clone_path).rglob("*.py"))
    sql_files = list(Path(clone_path).rglob("*.sql"))

    # Filter out test files and __init__ for Python (keep tests but deprioritize)
    py_files = [f for f in py_files if not any(
        skip in str(f) for skip in [".git", "__pycache__", "node_modules", ".tox"]
    )]
    sql_files = [f for f in sql_files if ".git" not in str(f)]

    for fpath in py_files[:max_files]:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            inv = FileInventory(
                path=str(fpath),
                language="python",
                size_bytes=fpath.stat().st_size,
                line_count=len(lines),
                complexity_score=_python_complexity(content),
                content=content,
            )
            inventory.python_files.append(inv)
        except Exception as e:
            inventory.errors.append(f"Read error {fpath}: {e}")

    for fpath in sql_files[:max_files]:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            inv = FileInventory(
                path=str(fpath),
                language="sql",
                size_bytes=fpath.stat().st_size,
                line_count=len(lines),
                complexity_score=_sql_complexity(content),
                content=content,
            )
            inventory.sql_files.append(inv)
        except Exception as e:
            inventory.errors.append(f"Read error {fpath}: {e}")

    # Sort by complexity descending — most complex files first
    inventory.python_files.sort(key=lambda x: x.complexity_score, reverse=True)
    inventory.sql_files.sort(key=lambda x: x.complexity_score, reverse=True)
    inventory.total_files = len(inventory.python_files) + len(inventory.sql_files)

    print(f"[RepoScanner] Found {len(inventory.python_files)} Python files, "
          f"{len(inventory.sql_files)} SQL files")

    return inventory


def cleanup_repo(clone_path: str):
    """Remove cloned repo from disk"""
    try:
        shutil.rmtree(clone_path, ignore_errors=True)
        print(f"[RepoScanner] Cleaned up {clone_path}")
    except Exception:
        pass


if __name__ == "__main__":
    inv = scan_repo("https://github.com/pallets/flask", max_files=10)
    print(f"\nTop 3 Python files by complexity:")
    for f in inv.python_files[:3]:
        print(f"  {f.path.split('/')[-1]}: complexity={f.complexity_score} lines={f.line_count}")
