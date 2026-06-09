# Autonomous Code Review & Bug Fix Agent Network
## 6-Agent Pipeline | Python AST + SQL Static Analysis | Ollama LLM Fixes | Public GitHub Repo Scanning

---

## Overview

Code review is time-consuming and inconsistent. The same engineer who catches every mutable default argument on Monday misses it on Friday at 5pm. This project automates the structural and logic-level portion of code review using a 6-agent pipeline where each agent has a specific role, passes its output to the next, and the final agent produces a structured PR review report.

The system works on any public GitHub repository URL or any local Python or SQL file. It requires no API keys, no cloud services, and no paid tools. All LLM inference runs locally via Ollama.

---

## Architecture — 6 Agents

```
Agent 1: RepoScannerAgent
  ↓ Clones public GitHub repo, inventories .py and .sql files
  ↓ Scores each file by complexity (AST node count / SQL keyword density)
  ↓ Prioritizes highest-complexity files for downstream analysis

Agent 2: CodeAnalyzerAgent
  ↓ Python: AST analysis (bare except, mutable defaults, None comparisons, long functions)
  ↓ Python: pylint errors-only pass for additional logic issues
  ↓ SQL: sqlparse analysis (SELECT *, missing WHERE, non-SARGable, N+1, CROSS JOIN)
  ↓ Returns structured Finding objects with severity, line number, snippet

Agent 3: BugDiagnosticAgent
  ↓ Sends each finding to Ollama (Mistral) with targeted prompt
  ↓ Returns root cause (why this happens) + business impact (what breaks)
  ↓ Assigns priority: P0 (CRITICAL) through P3 (LOW)

Agent 4: FixWriterAgent
  ↓ Sends finding + diagnosis to Ollama
  ↓ Returns corrected code snippet
  ↓ Generates one-sentence explanation of what changed and why

Agent 5: TestWriterAgent
  ↓ Python: generates pytest test functions verifying the fix works
  ↓ SQL: generates EXPLAIN + validation query test suite
  ↓ Returns TestSuite with test count

Agent 6: ReviewAgent
  ↓ Aggregates all findings, fixes, and tests
  ↓ Generates 3-sentence review summary via Ollama
  ↓ Issues recommendation: APPROVE / REQUEST_CHANGES / NEEDS_MAJOR_REWORK
  ↓ Writes Markdown PR report + JSON report to outputs/
```

---

## What It Finds

### Python
- Bare except clauses (catches KeyboardInterrupt, SystemExit)
- Mutable default arguments (shared state across all function calls)
- `== None` instead of `is None`
- print() statements in production code
- Functions over 50 lines
- pylint error-level findings

### SQL
- SELECT * queries (unnecessary I/O)
- UPDATE / DELETE without WHERE clause (affects all rows)
- Non-SARGable WHERE clauses (YEAR(), MONTH(), UPPER() on indexed columns)
- Deeply nested subqueries (N+1 pattern indicator)
- CROSS JOIN (Cartesian product)
- Type mismatch in WHERE comparisons

---

## Demo Results on Sample Files

**Python file (83 lines):**
- 15 issues found: 9 HIGH, 2 MEDIUM, 4 LOW
- 5 fixes generated with corrected code
- 3 pytest test suites generated
- Recommendation: REQUEST_CHANGES

**SQL file (42 lines, 7 statements):**
- 11 issues found: 2 HIGH, 6 MEDIUM, 3 LOW
- 5 fixes generated with corrected SQL
- 3 SQL validation test suites generated
- Recommendation: REQUEST_CHANGES

---

## How to Run

```bash
# 1. Setup
cd ~/Desktop/Projects/code-review-agent
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Start Ollama (required for fix generation)
ollama serve        # in a separate terminal
ollama pull mistral # first time only

# 3. Demo mode — runs on bundled sample files
python3 main.py --demo

# 4. Analyze a local file
python3 main.py --local path/to/your_file.py
python3 main.py --local path/to/your_queries.sql

# 5. Analyze a public GitHub repo
python3 main.py --repo https://github.com/pallets/flask
python3 main.py --repo https://github.com/any-public-repo --max-files 10

# 6. View reports
open outputs/review_sample_buggy_py.md
```

---

## Output Files

```
outputs/
├── review_<filename>.md    ← Markdown PR report (human readable)
└── review_<filename>.json  ← Structured JSON report (machine readable)
```

Each report contains:
- Finding count by severity
- Per-finding: description, line number, code snippet, root cause, business impact
- Per-finding: original code, fixed code, explanation
- Generated tests for top 3 findings
- Overall recommendation with justification

---


## Without Ollama

The system works without Ollama — Agents 2 (static analysis) and 6 (recommendation) run fully without LLM. Agents 3, 4, and 5 fall back gracefully with a note that Ollama is unavailable. The structural findings from the AST and SQL analysis are still generated and reported.

---

*Built by Raja Palagummi | rajapalagummi.com | github.com/rajapalagummi*
