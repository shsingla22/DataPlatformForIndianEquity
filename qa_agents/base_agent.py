"""Base class for all Q&A validation agents."""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from qa_agents.models import Finding, AgentResult, Severity


class BaseAgent(ABC):
    """Base validation agent. Subclasses implement validate_company()."""

    name: str = "BaseAgent"

    def __init__(self):
        self.result = AgentResult(agent_name=self.name)

    def run(self, companies_data: List[Dict[str, Any]]) -> AgentResult:
        """Run validation across all companies. Returns AgentResult."""
        self.result = AgentResult(agent_name=self.name)
        for company_data in companies_data:
            self.validate_company(company_data)
        return self.result

    @abstractmethod
    def validate_company(self, company_data: Dict[str, Any]):
        """Validate a single company's data. Must call self._pass() or self._finding()."""
        pass

    def _pass(self):
        """Record a passed check."""
        self.result.add_pass()

    def _finding(self, company_data: Dict[str, Any], fiscal_year: str,
                 rule_id: str, severity: Severity, message: str,
                 expected: Optional[str] = None, actual: Optional[str] = None):
        """Record a failed check."""
        self.result.add_finding(Finding(
            company_symbol=company_data.get("nse_symbol", "UNKNOWN"),
            company_name=company_data.get("name", "Unknown"),
            fiscal_year=fiscal_year,
            rule_id=rule_id,
            severity=severity,
            message=message,
            expected=expected,
            actual=actual,
        ))

    @staticmethod
    def is_bank(company_data: Dict[str, Any]) -> bool:
        """Detect if company is a bank/financial institution.

        Banks on Screener.in have NULL sales and operating_profit because
        their income statement follows RBI format (interest income, not sales).
        """
        for pl in company_data.get("profit_loss", []):
            if pl.get("sales") is None:
                return True
        return False

    @staticmethod
    def safe_pct_diff(actual: float, expected: float) -> float:
        """Calculate percentage difference safely. Returns abs % diff."""
        if expected == 0:
            return 0.0 if actual == 0 else 100.0
        return abs((actual - expected) / abs(expected)) * 100.0

    @staticmethod
    def val(v) -> Optional[float]:
        """Convert a value to float, returning None if not a number."""
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None
