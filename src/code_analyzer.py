"""
CodeAnalyzerAgent
Static analysis for Python (AST + pylint + radon) and SQL (sqlparse)
Returns structured findings with severity, location, and description
"""
import ast
import json
import subprocess
import tempfile
import os
from dataclasses import dataclass, field
from typing import List
import sqlparse
from sqlparse.sql import Statement
from src.repo_scanner import FileInventory


@dataclass
class Finding:
    file_path: str
    language: str
    severity: str        # CRITICAL / HIGH / MEDIUM / LOW
    category: str        # syntax_error / logic_error / style / security / performance
    line_number: int
    description: str
    code_snippet: str
    suggestion: str = ""


def analyze_python(file_inv: FileInventory) -> List[Finding]:
    findings = []
    content = file_inv.content
    lines = content.splitlines()

    # ── 1. Syntax errors via AST ──────────────────────────────────
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        findings.append(Finding(
            file_path=file_inv.path,
            language="python",
            severity="CRITICAL",
            category="syntax_error",
            line_number=e.lineno or 0,
            description=f"Syntax error: {e.msg}",
            code_snippet=lines[e.lineno - 1] if e.lineno and e.lineno <= len(lines) else "",
            suggestion="Fix syntax error before running further analysis.",
        ))
        return findings

    # ── 2. AST-based logic checks ─────────────────────────────────
    for node in ast.walk(tree):

        # Bare except
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            snippet = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            findings.append(Finding(
                file_path=file_inv.path,
                language="python",
                severity="HIGH",
                category="logic_error",
                line_number=node.lineno,
                description="Bare except clause catches all exceptions including KeyboardInterrupt and SystemExit.",
                code_snippet=snippet.strip(),
                suggestion="Catch specific exceptions: except (ValueError, TypeError) as e:",
            ))

        # Mutable default arguments
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    snippet = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                    findings.append(Finding(
                        file_path=file_inv.path,
                        language="python",
                        severity="HIGH",
                        category="logic_error",
                        line_number=node.lineno,
                        description=f"Mutable default argument in function '{node.name}'. Shared across all calls.",
                        code_snippet=snippet.strip(),
                        suggestion="Use None as default and initialize inside function: if arg is None: arg = []",
                    ))

        # == None instead of is None
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value is None:
                    line_no = node.lineno
                    snippet = lines[line_no - 1] if line_no <= len(lines) else ""
                    findings.append(Finding(
                        file_path=file_inv.path,
                        language="python",
                        severity="MEDIUM",
                        category="style",
                        line_number=line_no,
                        description="Use 'is None' or 'is not None' instead of == None / != None.",
                        code_snippet=snippet.strip(),
                        suggestion="Replace '== None' with 'is None' and '!= None' with 'is not None'.",
                    ))

        # print statements in non-test files
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                if "test" not in file_inv.path.lower():
                    snippet = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                    findings.append(Finding(
                        file_path=file_inv.path,
                        language="python",
                        severity="LOW",
                        category="style",
                        line_number=node.lineno,
                        description="print() statement found in production code.",
                        code_snippet=snippet.strip(),
                        suggestion="Replace with logging: import logging; logging.info(...)",
                    ))

        # Long functions (> 50 lines)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if hasattr(node, "end_lineno") and node.end_lineno:
                func_len = node.end_lineno - node.lineno
                if func_len > 50:
                    snippet = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                    findings.append(Finding(
                        file_path=file_inv.path,
                        language="python",
                        severity="MEDIUM",
                        category="style",
                        line_number=node.lineno,
                        description=f"Function '{node.name}' is {func_len} lines long. Consider splitting.",
                        code_snippet=snippet.strip(),
                        suggestion="Extract logical blocks into helper functions to improve readability.",
                    ))

    # ── 3. Pylint check ───────────────────────────────────────────
    try:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                         delete=False, encoding="utf-8") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = subprocess.run(
            ["python3", "-m", "pylint", tmp_path,
             "--output-format=json",
             "--disable=C,R,W0611",  # disable style, convention, unused import
             "--errors-only"],
            capture_output=True, text=True, timeout=30
        )
        os.unlink(tmp_path)

        if result.stdout.strip():
            pylint_issues = json.loads(result.stdout)
            for issue in pylint_issues[:10]:  # cap at 10 pylint findings
                findings.append(Finding(
                    file_path=file_inv.path,
                    language="python",
                    severity="HIGH" if issue.get("type") == "error" else "MEDIUM",
                    category="logic_error",
                    line_number=issue.get("line", 0),
                    description=f"[pylint {issue.get('message-id','')}] {issue.get('message','')}",
                    code_snippet=issue.get("obj", ""),
                    suggestion="Review pylint finding and apply appropriate fix.",
                ))
    except Exception:
        pass

    return findings


def analyze_sql(file_inv: FileInventory) -> List[Finding]:
    findings = []
    content = file_inv.content
    lines = content.splitlines()
    upper = content.upper()

    statements = sqlparse.parse(content)

    for stmt in statements:
        stmt_str = str(stmt).strip()
        stmt_upper = stmt_str.upper()

        # SELECT * usage
        if "SELECT *" in stmt_upper or "SELECT\n*" in stmt_upper:
            line_no = content[:content.upper().find("SELECT *")].count("\n") + 1 if "SELECT *" in upper else 1
            findings.append(Finding(
                file_path=file_inv.path,
                language="sql",
                severity="MEDIUM",
                category="performance",
                line_number=line_no,
                description="SELECT * retrieves all columns including unnecessary ones, increasing I/O and network load.",
                code_snippet="SELECT *",
                suggestion="Specify only required columns explicitly: SELECT col1, col2 FROM ...",
            ))

        # Missing WHERE on UPDATE/DELETE
        if stmt_upper.startswith(("UPDATE", "DELETE")) and "WHERE" not in stmt_upper:
            findings.append(Finding(
                file_path=file_inv.path,
                language="sql",
                severity="CRITICAL",
                category="logic_error",
                line_number=1,
                description=f"{'UPDATE' if stmt_upper.startswith('UPDATE') else 'DELETE'} statement without WHERE clause — affects all rows.",
                code_snippet=stmt_str[:100],
                suggestion="Add WHERE clause to limit scope of operation.",
            ))

        # Implicit type conversion (comparing string to integer pattern)
        if "WHERE" in stmt_upper and ("= '" in stmt_str or "= \"" in stmt_str):
            findings.append(Finding(
                file_path=file_inv.path,
                language="sql",
                severity="LOW",
                category="performance",
                line_number=1,
                description="String literal in WHERE clause may cause implicit type conversion and index scan bypass.",
                code_snippet=stmt_str[:100],
                suggestion="Ensure column and comparison value types match to enable index usage.",
            ))

        # Non-SARGable patterns
        if any(pattern in stmt_upper for pattern in ["WHERE YEAR(", "WHERE MONTH(", "WHERE UPPER(", "WHERE LOWER("]):
            findings.append(Finding(
                file_path=file_inv.path,
                language="sql",
                severity="MEDIUM",
                category="performance",
                line_number=1,
                description="Function applied to indexed column in WHERE clause prevents index usage (non-SARGable).",
                code_snippet=stmt_str[:100],
                suggestion="Rewrite to avoid functions on indexed columns: use date ranges instead of YEAR().",
            ))

        # N+1 pattern hint (nested SELECT in loop context)
        subquery_count = stmt_upper.count("SELECT")
        if subquery_count > 3:
            findings.append(Finding(
                file_path=file_inv.path,
                language="sql",
                severity="HIGH",
                category="performance",
                line_number=1,
                description=f"Query contains {subquery_count} nested SELECT statements — potential N+1 query pattern.",
                code_snippet=stmt_str[:100],
                suggestion="Refactor to use JOINs or CTEs instead of deeply nested subqueries.",
            ))

    # Missing indexes hint (large table scans)
    if "CROSS JOIN" in upper:
        findings.append(Finding(
            file_path=file_inv.path,
            language="sql",
            severity="HIGH",
            category="performance",
            line_number=1,
            description="CROSS JOIN produces Cartesian product — exponential row count growth.",
            code_snippet="CROSS JOIN",
            suggestion="Verify CROSS JOIN is intentional. Consider INNER JOIN with ON condition.",
        ))

    return findings


def analyze_file(file_inv: FileInventory) -> List[Finding]:
    if file_inv.language == "python":
        return analyze_python(file_inv)
    elif file_inv.language == "sql":
        return analyze_sql(file_inv)
    return []


if __name__ == "__main__":
    # Quick test on a sample Python file
    from src.repo_scanner import FileInventory
    sample = FileInventory(
        path="test.py", language="python",
        size_bytes=100, line_count=10,
        complexity_score=5.0,
        content="""
def bad_func(items=[]):
    try:
        result = items[0]
    except:
        print("error")
    if result == None:
        return []
"""
    )
    findings = analyze_file(sample)
    for f in findings:
        print(f"[{f.severity}] Line {f.line_number}: {f.description}")
