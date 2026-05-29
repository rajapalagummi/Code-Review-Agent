"""
BugDiagnosticAgent — root causes findings using Ollama
FixWriterAgent — generates code fixes
TestWriterAgent — writes pytest unit tests
ReviewAgent — produces structured PR review report
"""
import json
import urllib.request
from dataclasses import dataclass, field
from typing import List
from src.code_analyzer import Finding


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral"


def call_ollama(prompt: str, max_tokens: int = 512) -> str:
    try:
        data = json.dumps({
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.1}
        }).encode()
        req = urllib.request.Request(
            OLLAMA_URL, data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read().decode())
            return result.get("response", "").strip()
    except Exception as e:
        return f"[Ollama unavailable: {e}]"


@dataclass
class Diagnosis:
    finding: Finding
    root_cause: str
    impact: str
    priority: str  # P0 / P1 / P2 / P3


@dataclass
class Fix:
    finding: Finding
    diagnosis: Diagnosis
    original_code: str
    fixed_code: str
    explanation: str


@dataclass
class TestSuite:
    fix: Fix
    test_code: str
    test_count: int


@dataclass
class PRReview:
    file_path: str
    language: str
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    fixes: List[Fix]
    tests: List[TestSuite]
    summary: str
    recommendation: str  # APPROVE / REQUEST_CHANGES / NEEDS_MAJOR_REWORK


# ── BugDiagnosticAgent ────────────────────────────────────────────────────────

def diagnose_finding(finding: Finding) -> Diagnosis:
    priority_map = {"CRITICAL": "P0", "HIGH": "P1", "MEDIUM": "P2", "LOW": "P3"}

    prompt = f"""You are a senior software engineer doing code review.

Issue found:
- Language: {finding.language}
- Category: {finding.category}
- Severity: {finding.severity}
- Description: {finding.description}
- Code: {finding.code_snippet}

In 2 sentences maximum:
1. Root cause (why this happens)
2. Business impact (what can go wrong)

Be direct and technical. No preamble."""

    response = call_ollama(prompt, max_tokens=150)
    lines = [l.strip() for l in response.split("\n") if l.strip()]
    root_cause = lines[0] if lines else finding.description
    impact = lines[1] if len(lines) > 1 else "May cause runtime errors or incorrect behavior."

    return Diagnosis(
        finding=finding,
        root_cause=root_cause,
        impact=impact,
        priority=priority_map.get(finding.severity, "P2"),
    )


# ── FixWriterAgent ────────────────────────────────────────────────────────────

def write_fix(diagnosis: Diagnosis) -> Fix:
    finding = diagnosis.finding

    prompt = f"""You are a senior software engineer. Write a fix for this issue.

Language: {finding.language}
Issue: {finding.description}
Code with bug:
{finding.code_snippet}

Suggestion: {finding.suggestion}

Return ONLY the fixed code snippet. No explanation. No markdown. Just the corrected code."""

    fixed_code = call_ollama(prompt, max_tokens=200)
    fixed_code = fixed_code.replace("```python", "").replace("```sql", "").replace("```", "").strip()

    explanation_prompt = f"""In one sentence, explain what you changed and why:
Original: {finding.code_snippet}
Fixed: {fixed_code}"""

    explanation = call_ollama(explanation_prompt, max_tokens=80)

    return Fix(
        finding=finding,
        diagnosis=diagnosis,
        original_code=finding.code_snippet,
        fixed_code=fixed_code,
        explanation=explanation,
    )


# ── TestWriterAgent ───────────────────────────────────────────────────────────

def write_tests(fix: Fix) -> TestSuite:
    finding = fix.finding

    if finding.language == "sql":
        test_code = f"""-- SQL validation test for: {finding.description}
-- Original issue: {finding.category}

-- Test 1: Verify fix does not affect all rows unintentionally
-- Run in staging environment only
-- Expected: Only targeted rows modified

-- Test 2: Verify query plan uses index (no full table scan)
EXPLAIN {fix.fixed_code};

-- Test 3: Verify result set is non-empty and correct
SELECT COUNT(*) FROM (
    {fix.fixed_code}
) AS validation_result;
"""
        return TestSuite(fix=fix, test_code=test_code, test_count=3)

    # Python test
    prompt = f"""Write a pytest unit test for this Python fix.

Issue fixed: {finding.description}
Fixed code:
{fix.fixed_code}

Write 2-3 pytest test functions that verify:
1. The fix works correctly for normal input
2. The fix handles edge cases

Return ONLY pytest code starting with 'import pytest'. No markdown."""

    test_code = call_ollama(prompt, max_tokens=300)
    test_code = test_code.replace("```python", "").replace("```", "").strip()
    if not test_code.startswith("import"):
        test_code = f"import pytest\n\n{test_code}"

    test_count = test_code.count("def test_")

    return TestSuite(fix=fix, test_code=test_code, test_count=max(test_count, 1))


# ── ReviewAgent ───────────────────────────────────────────────────────────────

def generate_review(
    file_inv,
    findings: List[Finding],
    fixes: List[Fix],
    tests: List[TestSuite],
) -> PRReview:
    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

    # Recommendation logic
    if severity_counts["CRITICAL"] > 0:
        recommendation = "NEEDS_MAJOR_REWORK"
    elif severity_counts["HIGH"] > 2:
        recommendation = "REQUEST_CHANGES"
    elif severity_counts["HIGH"] > 0 or severity_counts["MEDIUM"] > 3:
        recommendation = "REQUEST_CHANGES"
    else:
        recommendation = "APPROVE"

    findings_summary = "\n".join([
        f"- [{f.severity}] {f.description} (line {f.line_number})"
        for f in findings[:8]
    ])

    prompt = f"""You are a senior engineer writing a code review summary.

File: {file_inv.path.split('/')[-1]}
Language: {file_inv.language}
Lines: {file_inv.line_count}
Complexity: {file_inv.complexity_score}

Findings:
{findings_summary}

Write a 3-sentence code review summary:
1. Overall code quality assessment
2. Most important issues to fix
3. What the developer did well (if anything)

Be direct and constructive."""

    summary = call_ollama(prompt, max_tokens=200)

    return PRReview(
        file_path=file_inv.path,
        language=file_inv.language,
        total_findings=len(findings),
        critical_count=severity_counts["CRITICAL"],
        high_count=severity_counts["HIGH"],
        medium_count=severity_counts["MEDIUM"],
        low_count=severity_counts["LOW"],
        fixes=fixes,
        tests=tests,
        summary=summary,
        recommendation=recommendation,
    )
