# Q&A Agent Swarm Design: Financial Data Validation

## Overview

A lightweight agent swarm that validates Indian equity financial data stored in SQLite against Indian Accounting Standards (IndAS/GAAP) principles. Each agent is a specialist that owns one domain of validation, runs independently, and reports findings to a coordinator.

Showboat is integrated to produce an executable demo document (`qa_report.md`) that proves every validation step, captures outputs, and can be re-verified.

---

## Architecture

```
                    ┌──────────────────────┐
                    │   QA Coordinator     │
                    │  (Orchestrator)      │
                    │                      │
                    │  - Spawns agents     │
                    │  - Collects results  │
                    │  - Builds Showboat   │
                    │    demo document     │
                    └──────┬───────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  Agent 1    │ │  Agent 2    │ │  Agent 3    │
    │  P&L Flow   │ │  Balance    │ │  Cash Flow  │
    │  Validator  │ │  Sheet      │ │  Integrity  │
    │             │ │  Validator  │ │  Validator  │
    └─────────────┘ └─────────────┘ └─────────────┘
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  Agent 4    │ │  Agent 5    │ │  Agent 6    │
    │  Cross-     │ │  Trend      │ │  Completeness│
    │  Statement  │ │  Anomaly    │ │  & Freshness │
    │  Reconciler │ │  Detector   │ │  Checker     │
    └─────────────┘ └─────────────┘ └─────────────┘
```

---

## StrongDM Software Factory Principles Applied

| StrongDM Principle | How We Apply It |
|---|---|
| **Scenario Testing / Satisfaction** | Each agent runs "scenarios" (validation rules) against real data. We measure "satisfaction" — what % of companies pass each check — not just pass/fail. |
| **Digital Twin Universe (DTU)** | Our SQLite database IS the DTU — a self-contained replica of financial filings. Agents validate against it without hitting live services. Tests use an in-memory SQLite twin. |
| **Pyramid Summaries** | The coordinator produces a 3-level summary: (1) one-line overall health score, (2) per-agent summary, (3) detailed per-company findings. |
| **Gene Transfusion** | We reuse patterns from the existing `src/validators.py` — same tolerance thresholds, same error severity model — and extend them. |

---

## Agent Specifications

### Agent 1: P&L Flow Validator

**Purpose**: Verify Profit & Loss statement follows the IndAS income statement flow.

**Rules** (Indian GAAP / IndAS):
```
Rule 1.1: Operating Profit ≈ Sales - Expenses                    (±5%)
Rule 1.2: PBT ≈ Operating Profit + Other Income - Interest - Depreciation  (±5%)
Rule 1.3: Net Profit ≈ PBT × (1 - Tax Rate/100)                  (±10%)
Rule 1.4: Tax Rate between 0% and 45%  (India corporate tax max ~34.94% + surcharge)
Rule 1.5: OPM% ≈ (Operating Profit / Sales) × 100                (±2pp)
Rule 1.6: If Sales > 0, Expenses should be > 0
Rule 1.7: EPS sign should match Net Profit sign
```

**Output**: List of `(company, fiscal_year, rule, expected, actual, severity)` tuples.

---

### Agent 2: Balance Sheet Validator

**Purpose**: Verify Balance Sheet follows the fundamental accounting equation and IndAS norms.

**Rules**:
```
Rule 2.1: Total Assets ≈ Total Liabilities                        (±1%)
Rule 2.2: Total Liabilities ≈ Equity Capital + Reserves + Borrowings + Other Liabilities (±1%)
Rule 2.3: Total Assets ≈ Fixed Assets + CWIP + Investments + Other Assets   (±1%)
Rule 2.4: Equity Capital > 0  (must have share capital)
Rule 2.5: Total Assets > 0
Rule 2.6: If Borrowings > 0, Interest expense in P&L should be > 0
```

**Output**: Same tuple format.

---

### Agent 3: Cash Flow Integrity Validator

**Purpose**: Verify Cash Flow statement internal consistency per IndAS 7.

**Rules**:
```
Rule 3.1: Net Cash Flow ≈ Operating CF + Investing CF + Financing CF  (±5%)
Rule 3.2: If company is profitable (Net Profit > 0), Operating CF should
          usually be positive (flag if negative for 2+ consecutive years)
Rule 3.3: Investing CF typically negative for growing companies (info only)
Rule 3.4: |Net Cash Flow| should not exceed Total Assets (sanity check)
```

---

### Agent 4: Cross-Statement Reconciler

**Purpose**: Validate relationships BETWEEN the three financial statements — the most critical check for data accuracy.

**Rules** (IndAS reconciliation):
```
Rule 4.1: If Borrowings > 0 in BS, Interest > 0 in P&L             (warning)
Rule 4.2: If Fixed Assets > 0, Depreciation > 0 in P&L             (warning)
Rule 4.3: Reserves change ≈ Net Profit - Dividends (approx)        (±20%, info)
Rule 4.4: Net Profit in P&L should be directionally consistent
          with Operating CF (both positive or explanation expected)
Rule 4.5: Debt-to-Equity ratio between 0 and 10 for non-financial companies
Rule 4.6: If Sales exist in P&L, Total Assets should exist in BS for same year
```

---

### Agent 5: Trend Anomaly Detector

**Purpose**: Detect suspicious year-over-year changes that likely indicate data errors rather than business changes.

**Rules**:
```
Rule 5.1: Revenue YoY change > 200% or < -50%                     (warning)
Rule 5.2: Net Profit sign flip (positive ↔ negative) across years  (info)
Rule 5.3: Total Assets YoY change > 100% or < -30%                (warning)
Rule 5.4: Operating Margin swing > 20 percentage points YoY        (warning)
Rule 5.5: EPS and Net Profit should move in the same direction     (error)
```

---

### Agent 6: Completeness & Freshness Checker

**Purpose**: Ensure we have full data coverage and no missing fields.

**Rules**:
```
Rule 6.1: Each company should have P&L, BS, AND CF for each fiscal year
Rule 6.2: Key fields should not be NULL: sales, net_profit, total_assets,
          total_liabilities, net_cash_flow
Rule 6.3: Should have at least 2 fiscal years of data (for trend analysis)
Rule 6.4: Latest fiscal year should be Mar 2023 or newer
Rule 6.5: No duplicate (company_id, fiscal_year) entries
          (enforced by schema but validated)
Rule 6.6: Company should have nse_symbol and name populated
```

---

## Data Flow

```
1. Coordinator reads all companies from SQLite
2. For each company, loads P&L + BS + CF data
3. Passes data to all 6 agents (run sequentially — simple, debuggable)
4. Each agent returns a list of findings: {company, year, rule, message, severity}
5. Coordinator aggregates findings into 3-level Pyramid Summary:
   Level 1: "Data Health Score: 94.2% — 28 warnings, 3 errors across 500 companies"
   Level 2: Per-agent table (agent name, checks run, pass rate, issues found)
   Level 3: Per-company detail (every finding with severity)
6. Coordinator uses Showboat to build qa_report.md with executable proof
```

---

## Showboat Integration

The coordinator will use Showboat to create `qa_report.md`:

```bash
# Initialize the report
showboat init qa_report.md "Financial Data Q&A Validation Report"

# Add overview
showboat note qa_report.md "Validation of 500+ Indian equity companies..."

# Run each agent and capture output
showboat exec qa_report.md python "python -m qa_agents.coordinator --agent pnl_flow"
showboat exec qa_report.md python "python -m qa_agents.coordinator --agent balance_sheet"
showboat exec qa_report.md python "python -m qa_agents.coordinator --agent cash_flow"
showboat exec qa_report.md python "python -m qa_agents.coordinator --agent cross_statement"
showboat exec qa_report.md python "python -m qa_agents.coordinator --agent trend_anomaly"
showboat exec qa_report.md python "python -m qa_agents.coordinator --agent completeness"

# Add summary
showboat exec qa_report.md python "python -m qa_agents.coordinator --summary"

# Verify everything is reproducible
showboat verify qa_report.md
```

This means anyone can re-run `showboat verify qa_report.md` later and confirm the validation results haven't changed.

---

## File Structure

```
qa_agents/
├── __init__.py
├── coordinator.py          # Orchestrator + CLI + Showboat integration
├── base_agent.py           # Base class for all agents
├── pnl_flow_agent.py       # Agent 1: P&L flow validation
├── balance_sheet_agent.py  # Agent 2: Balance sheet validation
├── cash_flow_agent.py      # Agent 3: Cash flow validation
├── cross_statement_agent.py # Agent 4: Cross-statement reconciliation
├── trend_anomaly_agent.py  # Agent 5: Trend anomaly detection
├── completeness_agent.py   # Agent 6: Completeness & freshness
└── models.py               # Finding dataclass, severity enum
tests_qa/
├── __init__.py
└── test_qa_agents.py       # Tests for all 6 agents using in-memory SQLite (DTU)
qa_report.md                # Generated by Showboat (output artifact)
```

---

## Key Design Decisions

1. **Simple over clever**: Each agent is a single Python class with a `validate(company_data) -> List[Finding]` method. No async, no message queues, no frameworks.

2. **Sequential execution**: Agents run one after another, not in parallel. This keeps the code debuggable and the Showboat output readable. The entire swarm runs in seconds (it's just SQLite queries + arithmetic).

3. **Tolerances follow Indian accounting reality**:
   - 5% tolerance on P&L flow (line items include/exclude minor adjustments differently)
   - 1% on Balance Sheet equation (rounding in Crores)
   - 10% on net profit vs tax calculation (deferred tax, prior period adjustments)

4. **Three severity levels**: `error` (likely data corruption), `warning` (suspicious but possible), `info` (notable but expected).

5. **DTU principle**: Tests create an in-memory SQLite database with known good/bad data. No network calls. No external dependencies.

6. **Pyramid Summary**: Level 1 = single health score. Level 2 = per-agent table. Level 3 = per-company detail. Allows quick triage.

---

## Indian Accounting Principles Enforced

| Principle | IndAS Reference | Which Agent |
|---|---|---|
| Income Statement flow (Revenue → PBT → PAT) | IndAS 1 (Presentation) | Agent 1 |
| Balance Sheet equation (A = L + E) | IndAS 1 | Agent 2 |
| Cash Flow classification (Operating/Investing/Financing) | IndAS 7 | Agent 3 |
| Depreciation on Fixed Assets | IndAS 16 (PPE) | Agent 4 |
| Interest on Borrowings | IndAS 23 (Borrowing Costs) | Agent 4 |
| Reserves reconciliation | IndAS 1, Companies Act 2013 | Agent 4 |
| Corporate tax rate bounds | Income Tax Act, 1961 | Agent 1 |
| Fiscal year ending March 31 | Companies Act 2013, Sec 2(41) | Agent 6 |
| Consolidated reporting preference | IndAS 110 | Agent 6 |
