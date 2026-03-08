"""Data models for Q&A agent swarm findings and satisfaction metrics."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    """A single validation finding from an agent."""
    company_symbol: str
    company_name: str
    fiscal_year: str
    rule_id: str
    severity: Severity
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    agent_name: str = ""


@dataclass
class AgentResult:
    """Aggregated result from a single agent run."""
    agent_name: str
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    findings: list = field(default_factory=list)

    @property
    def satisfaction(self) -> float:
        if self.total_checks == 0:
            return 100.0
        return (self.passed / self.total_checks) * 100.0

    def add_pass(self):
        self.total_checks += 1
        self.passed += 1

    def add_finding(self, finding: Finding):
        self.total_checks += 1
        self.failed += 1
        finding.agent_name = self.agent_name
        self.findings.append(finding)

    def summary_line(self) -> str:
        return (
            f"{self.agent_name}: {self.satisfaction:.1f}% satisfaction "
            f"({self.passed}/{self.total_checks} passed, "
            f"{self.failed} issues)"
        )


@dataclass
class HoldoutResult:
    """Result of comparing one holdout company against DB values."""
    nse_symbol: str
    total_fields: int = 0
    matched: int = 0
    mismatches: list = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if self.total_fields == 0:
            return 100.0
        return (self.matched / self.total_fields) * 100.0
