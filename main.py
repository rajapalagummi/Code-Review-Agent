"""
Autonomous Code Review & Bug Fix Agent Network
6-agent pipeline: RepoScanner → CodeAnalyzer → BugDiagnostic → FixWriter → TestWriter → ReviewAgent

Usage:
    python3 main.py --repo https://github.com/any-public-repo
    python3 main.py --local sample_code/sample_buggy.py
    python3 main.py --local sample_code/sample_buggy.sql
    python3 main.py --demo
"""
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.repo_scanner import scan_repo, cleanup_repo, FileInventory
from src.code_analyzer import analyze_file
from src.agents import (
    diagnose_finding, write_fix, write_tests,
    generate_review, PRReview
)

BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║     Autonomous Code Review & Bug Fix Agent Network               ║
║                                                                  ║
║  Agent 1: RepoScanner   — Clone & inventory files               ║
║  Agent 2: CodeAnalyzer  — Static analysis (AST + pylint)        ║
║  Agent 3: BugDiagnostic — Root cause analysis (Ollama)          ║
║  Agent 4: FixWriter     — Generate fixes (Ollama)               ║
║  Agent 5: TestWriter    — Write pytest/SQL tests (Ollama)       ║
║  Agent 6: ReviewAgent   — PR review report (Ollama)             ║
╚══════════════════════════════════════════════════════════════════╝
"""

OUTPUT_DIR = "outputs"


def run_pipeline_on_file(file_inv: FileInventory, output_dir: str) -> dict:
    """Run full 6-agent pipeline on a single file"""
    print(f"\n{'='*60}")
    print(f"  Analyzing: {file_inv.path.split('/')[-1]} ({file_inv.language})")
    print(f"  Lines: {file_inv.line_count} | Complexity: {file_inv.complexity_score}")
    print(f"{'='*60}")

    # Agent 2: Code Analyzer
    print(f"\n[Agent 2: CodeAnalyzer] Running static analysis...")
    findings = analyze_file(file_inv)
    print(f"  Found {len(findings)} issues: "
          f"{sum(1 for f in findings if f.severity=='CRITICAL')} CRITICAL, "
          f"{sum(1 for f in findings if f.severity=='HIGH')} HIGH, "
          f"{sum(1 for f in findings if f.severity=='MEDIUM')} MEDIUM, "
          f"{sum(1 for f in findings if f.severity=='LOW')} LOW")

    if not findings:
        print("  No issues found — file looks clean.")
        return {"file": file_inv.path, "findings": 0, "status": "clean"}

    # Agent 3: Bug Diagnostic (top 5 findings only for speed)
    print(f"\n[Agent 3: BugDiagnostic] Diagnosing root causes...")
    top_findings = sorted(
        findings,
        key=lambda f: {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}[f.severity],
        reverse=True
    )[:5]

    diagnoses = []
    for i, finding in enumerate(top_findings):
        print(f"  Diagnosing [{finding.severity}] {finding.description[:60]}...")
        diagnosis = diagnose_finding(finding)
        diagnoses.append(diagnosis)

    # Agent 4: Fix Writer
    print(f"\n[Agent 4: FixWriter] Generating fixes...")
    fixes = []
    for diagnosis in diagnoses:
        print(f"  Writing fix for: {diagnosis.finding.description[:60]}...")
        fix = write_fix(diagnosis)
        fixes.append(fix)

    # Agent 5: Test Writer
    print(f"\n[Agent 5: TestWriter] Writing tests...")
    tests = []
    for fix in fixes[:3]:  # top 3 fixes get tests
        print(f"  Writing tests for: {fix.finding.description[:60]}...")
        test_suite = write_tests(fix)
        tests.append(test_suite)
        print(f"  Generated {test_suite.test_count} test(s)")

    # Agent 6: Review Agent
    print(f"\n[Agent 6: ReviewAgent] Generating PR review...")
    review = generate_review(file_inv, findings, fixes, tests)
    print(f"  Recommendation: {review.recommendation}")

    # Save report
    os.makedirs(output_dir, exist_ok=True)
    fname = file_inv.path.split("/")[-1].replace(".", "_")
    report = _build_report(file_inv, findings, fixes, tests, review)
    report_path = os.path.join(output_dir, f"review_{fname}.json")
    md_path = os.path.join(output_dir, f"review_{fname}.md")

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    _write_markdown_report(review, fixes, tests, md_path)
    print(f"\n  Report saved → {md_path}")

    return report


def _build_report(file_inv, findings, fixes, tests, review: PRReview) -> dict:
    return {
        "generated_at": datetime.now().isoformat(),
        "file": file_inv.path.split("/")[-1],
        "language": file_inv.language,
        "metrics": {
            "lines": file_inv.line_count,
            "complexity": file_inv.complexity_score,
            "total_findings": len(findings),
            "critical": review.critical_count,
            "high": review.high_count,
            "medium": review.medium_count,
            "low": review.low_count,
        },
        "recommendation": review.recommendation,
        "summary": review.summary,
        "findings": [
            {
                "severity": f.severity,
                "category": f.category,
                "line": f.line_number,
                "description": f.description,
                "snippet": f.code_snippet,
                "suggestion": f.suggestion,
            }
            for f in findings
        ],
        "fixes": [
            {
                "issue": fx.finding.description,
                "original": fx.original_code,
                "fixed": fx.fixed_code,
                "explanation": fx.explanation,
            }
            for fx in fixes
        ],
        "tests_generated": sum(t.test_count for t in tests),
    }


def _write_markdown_report(review: PRReview, fixes, tests, path: str):
    lines = []
    lines.append(f"# Code Review Report")
    lines.append(f"**File:** `{review.file_path.split('/')[-1]}`")
    lines.append(f"**Language:** {review.language}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"\n## Recommendation: `{review.recommendation}`\n")
    lines.append(f"## Summary\n{review.summary}\n")
    lines.append(f"## Findings")
    lines.append(f"| Severity | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| 🔴 CRITICAL | {review.critical_count} |")
    lines.append(f"| 🟠 HIGH | {review.high_count} |")
    lines.append(f"| 🟡 MEDIUM | {review.medium_count} |")
    lines.append(f"| 🟢 LOW | {review.low_count} |")
    lines.append(f"| **Total** | **{review.total_findings}** |")

    lines.append(f"\n## Fixes Generated\n")
    for i, fix in enumerate(fixes, 1):
        lines.append(f"### Fix {i}: {fix.finding.description[:80]}")
        lines.append(f"**Severity:** {fix.finding.severity} | **Line:** {fix.finding.line_number}")
        lines.append(f"\n**Root Cause:** {fix.diagnosis.root_cause}")
        lines.append(f"\n**Original:**")
        lines.append(f"```{fix.finding.language}\n{fix.original_code}\n```")
        lines.append(f"\n**Fixed:**")
        lines.append(f"```{fix.finding.language}\n{fix.fixed_code}\n```")
        lines.append(f"\n**Explanation:** {fix.explanation}\n")

    lines.append(f"\n## Tests Generated\n")
    for i, test in enumerate(tests, 1):
        lines.append(f"### Test Suite {i}")
        lines.append(f"```{'python' if 'def test_' in test.test_code else 'sql'}")
        lines.append(test.test_code)
        lines.append("```\n")

    with open(path, "w") as f:
        f.write("\n".join(lines))


def run_on_local_file(file_path: str) -> dict:
    path = Path(file_path)
    if not path.exists():
        print(f"[Error] File not found: {file_path}")
        return {}

    content = path.read_text(encoding="utf-8", errors="ignore")
    language = "python" if path.suffix == ".py" else "sql" if path.suffix == ".sql" else None

    if not language:
        print(f"[Error] Unsupported file type: {path.suffix}. Use .py or .sql")
        return {}

    import ast as _ast, sqlparse as _sp
    if language == "python":
        try:
            tree = _ast.parse(content)
            nodes = sum(1 for _ in _ast.walk(tree))
            complexity = round(nodes * 0.1, 2)
        except Exception:
            complexity = 0.0
    else:
        complexity = round(content.upper().count("JOIN") * 1.5 + len(_sp.parse(content)) * 0.5, 2)

    file_inv = FileInventory(
        path=str(path.absolute()),
        language=language,
        size_bytes=path.stat().st_size,
        line_count=len(content.splitlines()),
        complexity_score=complexity,
        content=content,
    )

    return run_pipeline_on_file(file_inv, OUTPUT_DIR)


def run_on_repo(repo_url: str, max_files: int = 5) -> list:
    print(f"\n[Agent 1: RepoScanner] Cloning {repo_url}...")
    inventory = scan_repo(repo_url, max_files=max_files)

    if inventory.errors:
        for err in inventory.errors:
            print(f"[RepoScanner] Error: {err}")
        return []

    all_files = inventory.python_files[:3] + inventory.sql_files[:2]
    results = []

    print(f"\n[Pipeline] Analyzing top {len(all_files)} files by complexity...")
    for file_inv in all_files:
        result = run_pipeline_on_file(file_inv, OUTPUT_DIR)
        results.append(result)

    cleanup_repo(inventory.clone_path)
    return results


def run_demo():
    """Demo mode — runs on bundled sample files"""
    print("\n[Demo] Running on sample_code/sample_buggy.py...")
    run_on_local_file("sample_code/sample_buggy.py")

    print("\n[Demo] Running on sample_code/sample_buggy.sql...")
    run_on_local_file("sample_code/sample_buggy.sql")

    print(f"\n{'='*60}")
    print(f"  Demo complete. Reports in outputs/")
    print(f"{'='*60}")
    _print_output_summary()


def _print_output_summary():
    if not os.path.exists(OUTPUT_DIR):
        return
    print(f"\n📁 Generated outputs:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
        print(f"   • {f} ({size:,} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Autonomous Code Review & Bug Fix Agent Network"
    )
    parser.add_argument("--repo",  type=str, help="Public GitHub repo URL to analyze")
    parser.add_argument("--local", type=str, help="Local .py or .sql file to analyze")
    parser.add_argument("--demo",  action="store_true", help="Run on bundled sample files")
    parser.add_argument("--max-files", type=int, default=5,
                        help="Max files to analyze from repo (default: 5)")
    args = parser.parse_args()

    print(BANNER)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.repo:
        results = run_on_repo(args.repo, max_files=args.max_files)
        print(f"\n✓ Analyzed {len(results)} files from {args.repo}")
        _print_output_summary()
    elif args.local:
        run_on_local_file(args.local)
        _print_output_summary()
    elif args.demo:
        run_demo()
    else:
        print("Usage:")
        print("  python3 main.py --demo")
        print("  python3 main.py --local sample_code/sample_buggy.py")
        print("  python3 main.py --repo https://github.com/pallets/flask")
