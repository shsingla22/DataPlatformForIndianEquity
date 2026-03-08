# Q&A Agent Swarm Design: Financial Data Validation

## Overview

A lightweight agent swarm that validates Indian equity financial data stored in SQLite against Indian Accounting Standards (IndAS/GAAP) principles. Each agent is a specialist that owns one domain of validation, runs independently, and reports findings to a coordinator.

The system applies **StrongDM Software Factory principles** throughout — holdout sets for independent validation, scenario testing with satisfaction measurement, Digital Twin Universe for testing, and Pyramid Summaries for reporting. **Showboat** produces an executable proof-of-work document.

---

## Architecture

```
                         ┌──────────────────────┐
                         │   QA Coordinator      │
                         │  (Orchestrator)        │
                         │                        │
                         │  - Spawns agents       │
                         │  - Runs holdout check  │
                         │  - Measures satisfaction│
                         │  - Builds Showboat doc │
                         └──────┬─────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
 ┌──────▼──────┐         ┌──────▼──────┐         ┌──────▼──────┐
 │  Agent 1    │         │  Agent 2    │         │  Agent 3    │
 │  P&L Flow   │         │  Balance    │         │  Cash Flow  │
 │  Validator  │         │  Sheet      │         │  Integrity  │
 │             │         │  Validator  │         │  Validator  │
 └─────────────┘         └─────────────┘         └─────────────┘
        │                       │                       │
 ┌──────▼──────┐         ┌──────▼──────┐         ┌──────▼──────┐
 │  Agent 4    │         │  Agent 5    │         │  Agent 6    │
 │  Cross-     │         │  Trend      │         │  Completeness│
 │  Statement  │         │  Anomaly    │         │  & Freshness │
 │  Reconciler │         │  Detector   │         │  Checker     │
 └─────────────┘         └─────────────┘         └─────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Holdout Validator   │
                    │  (Independent Gate)   │
                    │                       │
                    │  - Compares DB values │
                    │    against known-good │
                    │    external data      │
                    │  - Measures agent     │
                    │    accuracy itself    │
                    └──────────────────────┘
```

---

## StrongDM Software Factory Principles — Deep Application

### 1. Holdout Sets (The Critical Missing Piece)

**The problem with self-referential validation**: If we only check internal consistency (does Total Assets = Total Liabilities?), we can't detect cases where Screener.in returned wrong numbers that happen to be internally consistent. A company could have ₹50,000 Cr revenue in our DB when the actual filing says ₹5,00,000 Cr — and all our arithmetic agents would say "looks fine."

**Holdout sets solve this** by providing ground-truth financial data sourced independently from actual company annual reports. These sets are:
- **External to the codebase** — stored as a separate JSON fixture, not derived from the DB
- **Hidden from the validation agents** — agents never see holdout data during validation; the holdout validator runs AFTER agents complete
- **Hand-verified** — curated from published annual reports of well-known companies

**How holdout sets work in our system**:

```
Phase 1: Agents validate the FULL database (500 companies)
         → Agents check internal consistency, completeness, trends
         → Agents produce findings + satisfaction scores

Phase 2: Holdout Validator runs SEPARATELY
         → Loads known-good data for ~10 benchmark companies
         → Compares DB values against holdout ground truth
         → If DB values deviate from holdout truth → the SCRAPING is wrong
         → If agents MISSED a deviation that holdout caught → the AGENTS are wrong
         → This validates both the data AND the validation engine itself
```

**Holdout set design** (10 companies spanning sectors):

```json
// qa_agents/holdouts/reliance_mar2025.json  (sourced from Reliance FY25 Annual Report)
{
  "source": "Reliance Industries Annual Report FY2024-25",
  "nse_symbol": "RELIANCE",
  "fiscal_year": "Mar 2025",
  "profit_loss": {
    "sales": 962820,
    "operating_profit": 165598,
    "net_profit": 81309,
    "eps": 51.47
  },
  "balance_sheet": {
    "total_assets": 1949713,
    "total_liabilities": 1949713,
    "equity_capital": 13532,
    "reserves": 829668,
    "borrowings": 374313
  },
  "cash_flow": {
    "cash_from_operating": 178703,
    "net_cash_flow": 9277
  }
}
```

We create holdout files for 10 companies:

| Company | Sector | Why selected |
|---|---|---|
| Reliance Industries | Conglomerate/Energy | Largest by market cap, complex conglomerate |
| TCS | IT Services | Clean financials, predictable margins |
| HDFC Bank | Banking | Tests bank-specific schema (NULL sales) |
| Infosys | IT Services | Cross-check against TCS patterns |
| SBI | PSU Banking | Public sector, different reporting style |
| Bharti Airtel | Telecom | High capex, high depreciation |
| ITC | FMCG | Stable, diversified revenue |
| HUL | FMCG | Asset-light model |
| L&T | Engineering | Project-based revenue recognition |
| Wipro | IT Services | Third IT cross-check |

**Holdout tolerance**: Values in DB must be within **±0.5%** of holdout truth (allows minor rounding in Crore conversions). Beyond that, the data is flagged as potentially corrupt.

**Why this matters**: Without holdout sets, we're doing the equivalent of grading our own homework. The agents could all say "100% pass" while the underlying data is wrong. Holdout sets are the independent examiner.

### 2. Scenario Testing with Satisfaction Measurement

Instead of boolean pass/fail, we measure **satisfaction** — what fraction of all company-year-rule trajectories produce acceptable results.

```
Satisfaction = (total checks passed) / (total checks run) × 100

Per-agent satisfaction:
  "P&L Flow Agent satisfaction: 96.3% (4,287 of 4,452 checks passed)"
  "Balance Sheet Agent satisfaction: 99.1% (4,412 of 4,452 checks passed)"

Per-rule satisfaction:
  "Rule 1.2 (PBT flow) satisfaction: 89.7% — 47 companies failed"
  "Rule 2.1 (BS equation) satisfaction: 99.8% — 1 company failed"

Holdout satisfaction:
  "Holdout accuracy: 100% (all 10 benchmark companies match ground truth)"
  "Agent detection rate: 95% (agents flagged 19 of 20 known issues)"
```

This probabilistic view tells us WHERE the data quality problems cluster, not just whether problems exist.

### 3. Digital Twin Universe (DTU)

Our system has TWO DTUs:

**Production DTU**: The SQLite database (`data/financial_profiles.db`) is itself a digital twin of the actual company filings at NSE/BSE/MCA. Agents validate against this twin without touching live services.

**Test DTU**: An in-memory SQLite database populated with synthetic companies that have **known issues injected**:
- Company A: Perfect data (all checks should pass)
- Company B: Balance sheet doesn't balance (Agent 2 must catch)
- Company C: P&L flow is broken (Agent 1 must catch)
- Company D: Missing cash flow data (Agent 6 must catch)
- Company E: Revenue dropped 90% YoY (Agent 5 must catch)
- Company F: Bank with NULL sales (should NOT be flagged — it's normal)
- Company G: Cross-statement mismatch (Agent 4 must catch)

This lets us test the agents themselves against known scenarios, at any volume, without external dependencies — exactly as StrongDM tests their Okta/Jira/Slack clones.

### 4. Pyramid Summaries

Three levels of detail, each agent and the coordinator produce all three:

```
LEVEL 1 — Executive (one line)
  "Data Health: 96.8% satisfaction | 500 companies | 28 warnings, 3 errors | Holdout: 10/10 match"

LEVEL 2 — Agent Summary (table)
  ┌─────────────────────┬───────┬────────┬────────┬──────────────┐
  │ Agent               │ Checks│ Passed │ Failed │ Satisfaction │
  ├─────────────────────┼───────┼────────┼────────┼──────────────┤
  │ P&L Flow            │ 4,452 │ 4,287  │ 165    │ 96.3%        │
  │ Balance Sheet       │ 4,452 │ 4,412  │ 40     │ 99.1%        │
  │ Cash Flow           │ 2,964 │ 2,900  │ 64     │ 97.8%        │
  │ Cross-Statement     │ 4,452 │ 4,350  │ 102    │ 97.7%        │
  │ Trend Anomaly       │ 2,000 │ 1,920  │ 80     │ 96.0%        │
  │ Completeness        │ 3,000 │ 2,970  │ 30     │ 99.0%        │
  │ HOLDOUT             │   80  │    80  │   0    │ 100.0%       │
  └─────────────────────┴───────┴────────┴────────┴──────────────┘

LEVEL 3 — Per-company detail (only for failures)
  RELIANCE | Mar 2025 | Rule 4.3 | warning | Reserves change (₹48,234 Cr)
           | differs from Net Profit - Dividends (₹72,368 Cr) by 33.3%
           | Likely explanation: other comprehensive income, buybacks
```

### 5. Gene Transfusion

We reuse patterns from the existing `src/validators.py`:
- Same `ValidationError` structure (company, check_name, message, severity)
- Same tolerance thresholds where applicable (1% BS, 5% P&L)
- Same severity model (error/warning)
- Extended with `info` severity and satisfaction metrics

---

## Agent Specifications

### Agent 1: P&L Flow Validator

**Purpose**: Verify Profit & Loss statement follows the IndAS income statement flow.

**Rules** (Indian GAAP / IndAS):
```
Rule 1.1: Operating Profit ≈ Sales - Expenses                              (±5%)
Rule 1.2: PBT ≈ Operating Profit + Other Income - Interest - Depreciation  (±5%)
Rule 1.3: Net Profit ≈ PBT × (1 - Tax Rate/100)                           (±10%)
Rule 1.4: Tax Rate between 0% and 45%  (India corporate tax ~25.17% base + surcharge)
Rule 1.5: OPM% ≈ (Operating Profit / Sales) × 100                         (±2pp)
Rule 1.6: If Sales > 0, Expenses should be > 0
Rule 1.7: EPS sign should match Net Profit sign
```

**Sector handling**: Banks have NULL sales/operating_profit — Rules 1.1, 1.5, 1.6 are skipped for financial companies (detected via NULL sales).

**Output**: List of `Finding(company, fiscal_year, rule_id, expected, actual, severity, message)`.

---

### Agent 2: Balance Sheet Validator

**Purpose**: Verify Balance Sheet follows the fundamental accounting equation and IndAS norms.

**Rules**:
```
Rule 2.1: Total Assets ≈ Total Liabilities                                         (±1%)
Rule 2.2: Total Liabilities ≈ Equity Capital + Reserves + Borrowings + Other Liabilities (±1%)
Rule 2.3: Total Assets ≈ Fixed Assets + CWIP + Investments + Other Assets           (±1%)
Rule 2.4: Equity Capital > 0  (must have share capital)
Rule 2.5: Total Assets > 0
Rule 2.6: If Borrowings > 0, Interest expense in P&L should be > 0
```

**Sector handling**: Banks have NULL borrowings (deposits are in other_liabilities) — Rule 2.2 and 2.6 treat NULL borrowings as 0.

---

### Agent 3: Cash Flow Integrity Validator

**Purpose**: Verify Cash Flow statement internal consistency per IndAS 7.

**Rules**:
```
Rule 3.1: Net Cash Flow ≈ Operating CF + Investing CF + Financing CF        (±5%)
Rule 3.2: If company profitable (Net Profit > 0), Operating CF should
          usually be positive (flag if negative 2+ consecutive years)
Rule 3.3: Investing CF typically negative for growing companies             (info only)
Rule 3.4: |Net Cash Flow| should not exceed Total Assets                    (sanity check)
```

---

### Agent 4: Cross-Statement Reconciler

**Purpose**: Validate relationships BETWEEN the three financial statements.

**Rules** (IndAS reconciliation):
```
Rule 4.1: If Borrowings > 0 in BS, Interest > 0 in P&L                     (warning)
Rule 4.2: If Fixed Assets > 0, Depreciation > 0 in P&L                     (warning)
Rule 4.3: Reserves change ≈ Net Profit - Dividends (approx)                (±20%, info)
Rule 4.4: Net Profit direction should be consistent with Operating CF
          direction (both positive or both negative)                        (info)
Rule 4.5: D/E ratio between 0 and 10 for non-financial companies           (warning)
Rule 4.6: If P&L data exists for a fiscal year, BS and CF should too        (error)
```

---

### Agent 5: Trend Anomaly Detector

**Purpose**: Detect suspicious year-over-year changes that likely indicate data errors.

**Rules**:
```
Rule 5.1: Revenue YoY change > 200% or < -50%                              (warning)
Rule 5.2: Net Profit sign flip (positive → negative or vice versa)          (info)
Rule 5.3: Total Assets YoY change > 100% or < -30%                         (warning)
Rule 5.4: Operating Margin swing > 20 percentage points YoY                (warning)
Rule 5.5: EPS and Net Profit should move in the same direction              (error)
```

---

### Agent 6: Completeness & Freshness Checker

**Purpose**: Ensure we have full data coverage and no missing fields.

**Rules**:
```
Rule 6.1: Each company should have P&L, BS, AND CF for each fiscal year
Rule 6.2: Key fields should not be NULL (unless sector-appropriate):
          - Non-banks: sales, net_profit, total_assets, total_liabilities, net_cash_flow
          - Banks: net_profit, total_assets, total_liabilities, net_cash_flow
Rule 6.3: Should have at least 2 fiscal years of data (for trend analysis)
Rule 6.4: Latest fiscal year should be Mar 2024 or newer
Rule 6.5: No duplicate (company_id, fiscal_year) entries
Rule 6.6: Company should have nse_symbol and name populated
```

---

## Data Flow with Holdout Validation

```
┌──────────────────────────────────────────────────────────────────┐
│                     PHASE 1: AGENT VALIDATION                    │
│                                                                  │
│  1. Coordinator loads all 500 companies from SQLite              │
│  2. For each company, loads P&L + BS + CF data                   │
│  3. Runs all 6 agents sequentially                               │
│  4. Each agent returns findings + per-rule pass/fail counts      │
│  5. Coordinator computes per-agent satisfaction scores            │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│                   PHASE 2: HOLDOUT VALIDATION                    │
│                                                                  │
│  1. Load holdout JSON files (10 benchmark companies)             │
│  2. For each holdout company:                                    │
│     a. Read corresponding DB values                              │
│     b. Compare each field: |DB - holdout| / holdout < 0.5%      │
│     c. If mismatch → DATA is wrong (scraping error)              │
│     d. Check if agents flagged this company for ANY issue        │
│        If agents missed a real issue → AGENTS are incomplete     │
│  3. Compute holdout satisfaction:                                │
│     - Data accuracy: X/Y holdout fields match                    │
│     - Agent detection rate: X/Y known issues were caught         │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│                   PHASE 3: PYRAMID SUMMARY                       │
│                                                                  │
│  Level 1: One-line health score + holdout status                 │
│  Level 2: Per-agent satisfaction table                           │
│  Level 3: Per-company findings (only failures)                   │
│                                                                  │
│  Output via Showboat → qa_report.md                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## Showboat Integration

The coordinator uses Showboat to build `qa_report.md` as executable proof-of-work:

```bash
# Initialize the report
showboat init qa_report.md "Financial Data Q&A Validation Report"

# Overview note
showboat note qa_report.md "Validating 500 Indian equity companies (3 years, IndAS)..."

# Phase 1: Run each agent and capture output
showboat exec qa_report.md bash "python -m qa_agents.coordinator --agent pnl_flow"
showboat exec qa_report.md bash "python -m qa_agents.coordinator --agent balance_sheet"
showboat exec qa_report.md bash "python -m qa_agents.coordinator --agent cash_flow"
showboat exec qa_report.md bash "python -m qa_agents.coordinator --agent cross_statement"
showboat exec qa_report.md bash "python -m qa_agents.coordinator --agent trend_anomaly"
showboat exec qa_report.md bash "python -m qa_agents.coordinator --agent completeness"

# Phase 2: Holdout validation
showboat note qa_report.md "## Holdout Validation (Independent Ground Truth)"
showboat exec qa_report.md bash "python -m qa_agents.coordinator --holdout"

# Phase 3: Full summary
showboat note qa_report.md "## Overall Data Health"
showboat exec qa_report.md bash "python -m qa_agents.coordinator --summary"

# Verify reproducibility
showboat verify qa_report.md
```

Anyone can later run `showboat verify qa_report.md` to confirm results are reproducible.

---

## File Structure

```
qa_agents/
├── __init__.py
├── coordinator.py            # Orchestrator + CLI + Showboat + Pyramid Summary
├── base_agent.py             # Base class: validate() → List[Finding], satisfaction()
├── pnl_flow_agent.py         # Agent 1: P&L flow validation
├── balance_sheet_agent.py    # Agent 2: Balance sheet validation
├── cash_flow_agent.py        # Agent 3: Cash flow validation
├── cross_statement_agent.py  # Agent 4: Cross-statement reconciliation
├── trend_anomaly_agent.py    # Agent 5: Trend anomaly detection
├── completeness_agent.py     # Agent 6: Completeness & freshness
├── holdout_validator.py      # Holdout set comparator (Phase 2)
├── models.py                 # Finding dataclass, Severity enum, Satisfaction
└── holdouts/                 # Ground-truth data (EXTERNAL to validation logic)
    ├── README.md             # Documents data sources for each holdout
    ├── RELIANCE_Mar2025.json
    ├── TCS_Mar2025.json
    ├── HDFCBANK_Mar2025.json
    ├── INFY_Mar2025.json
    ├── SBIN_Mar2025.json
    ├── BHARTIARTL_Mar2025.json
    ├── ITC_Mar2025.json
    ├── HINDUNILVR_Mar2025.json
    ├── LT_Mar2025.json
    └── WIPRO_Mar2025.json
tests_qa/
├── __init__.py
└── test_qa_agents.py         # Tests using in-memory SQLite DTU with injected scenarios
qa_report.md                  # Generated by Showboat (output artifact)
```

---

## Holdout Set Details

Each holdout JSON contains fields verified against the company's published annual report:

```json
{
  "source": "Reliance Industries Ltd Annual Report FY2024-25, pg 218-224",
  "verification_date": "2025-06-15",
  "nse_symbol": "RELIANCE",
  "fiscal_year": "Mar 2025",
  "sector": "Conglomerate",
  "is_bank": false,
  "profit_loss": {
    "sales": 962820,
    "expenses": 797222,
    "operating_profit": 165598,
    "opm_percent": 17.0,
    "other_income": 17824,
    "interest": 24269,
    "depreciation": 53136,
    "profit_before_tax": 106017,
    "tax_percent": 24.0,
    "net_profit": 81309,
    "eps": 51.47
  },
  "balance_sheet": {
    "equity_capital": 13532,
    "reserves": 829668,
    "borrowings": 374313,
    "total_liabilities": 1949713,
    "fixed_assets": 999393,
    "total_assets": 1949713
  },
  "cash_flow": {
    "cash_from_operating": 178703,
    "cash_from_investing": -137535,
    "cash_from_financing": -31891,
    "net_cash_flow": 9277
  }
}
```

The holdout validator checks:
1. **Data accuracy**: Each DB value must be within ±0.5% of holdout value
2. **NULL detection**: If holdout has a non-null value but DB has NULL → data gap
3. **Agent cross-check**: If holdout reveals a discrepancy, did any agent flag it?

---

## Test DTU (Digital Twin Universe) Design

The test suite creates an in-memory SQLite with **7 synthetic scenario companies**:

| Scenario Company | What's Wrong | Which Agent Must Catch It |
|---|---|---|
| SCENARIO_CLEAN | Nothing — perfectly valid data | None (all agents should pass) |
| SCENARIO_BS_BROKEN | Total Assets ≠ Total Liabilities (off by 15%) | Agent 2 (Balance Sheet) |
| SCENARIO_PNL_BROKEN | PBT ≠ OpProfit + OtherIncome - Interest - Depreciation | Agent 1 (P&L Flow) |
| SCENARIO_CF_MISSING | Has P&L and BS but no Cash Flow record | Agent 6 (Completeness) |
| SCENARIO_REVENUE_CRASH | Revenue drops 95% YoY | Agent 5 (Trend Anomaly) |
| SCENARIO_BANK | Bank with NULL sales/opm (should NOT be flagged) | None (sector-appropriate nulls) |
| SCENARIO_CROSS_MISMATCH | Has borrowings but zero interest expense | Agent 4 (Cross-Statement) |

Each test asserts:
- The correct agent flags the issue
- Other agents don't produce false positives on this scenario
- The SCENARIO_CLEAN company passes all agents
- The SCENARIO_BANK company is not falsely flagged

This is the DTU principle — we test our validation system against known scenarios before trusting it on real data.

---

## Key Design Decisions

1. **Holdout-first**: The holdout validator is not an afterthought — it's the gate that determines whether we trust the entire system. If holdouts fail, nothing else matters.

2. **Two-phase validation**: Phase 1 (agents) checks internal consistency. Phase 2 (holdouts) checks external accuracy. Both must pass for the data to be trusted.

3. **Satisfaction over pass/fail**: A 96% satisfaction score with 20 warnings is more useful than "FAILED" — it tells you exactly where to look.

4. **Sector-aware**: Banks (HDFC Bank, SBI, ICICI) have structurally different financials. NULL sales is normal for banks. The system must know this and not produce false positives.

5. **Simple over clever**: Each agent is a single Python class with `validate(company_data) -> List[Finding]`. No async, no message queues, no ML. Just arithmetic and comparisons.

6. **Tolerances follow Indian accounting reality**:
   - 0.5% on holdout comparison (Crore rounding)
   - 1% on Balance Sheet equation
   - 5% on P&L flow (minor line item differences)
   - 10% on Net Profit vs tax (deferred tax, prior period items)

7. **DTU for testing agents**: We don't test agents against real data (circular). We test them against synthetic scenarios with known injected issues.

---

## Indian Accounting Principles Enforced

| Principle | IndAS Reference | Which Agent |
|---|---|---|
| Income Statement flow (Revenue → PBT → PAT) | IndAS 1 (Presentation of Financial Statements) | Agent 1 |
| Balance Sheet equation (A = L + E) | IndAS 1 | Agent 2 |
| Cash Flow classification (Operating/Investing/Financing) | IndAS 7 (Statement of Cash Flows) | Agent 3 |
| Depreciation on PP&E | IndAS 16 (Property, Plant & Equipment) | Agent 4 |
| Interest on Borrowings | IndAS 23 (Borrowing Costs) | Agent 4 |
| Reserves reconciliation | IndAS 1, Companies Act 2013 Sch. III | Agent 4 |
| Corporate tax rate bounds | Income Tax Act 1961 (25.17% base + surcharge) | Agent 1 |
| Fiscal year ending March 31 | Companies Act 2013, Section 2(41) | Agent 6 |
| Consolidated reporting preference | IndAS 110 (Consolidated Financial Statements) | Agent 6 |
| Bank P&L structure (no "Sales" line) | RBI Master Directions, IndAS for banks | All agents |
