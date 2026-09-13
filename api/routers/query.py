"""Natural language query endpoint."""

from fastapi import APIRouter

from api.query_engine import ask
from api.schemas import QueryRequest, QueryResponse

router = APIRouter(prefix="/query", tags=["Natural Language Query"])


@router.post("", response_model=QueryResponse)
def natural_language_query(req: QueryRequest):
    """Ask a natural language question about Indian equity financial data.

    This endpoint accepts free-text questions and returns structured answers
    with supporting data.  It is designed for both human users (via the UI)
    and AI agents (via the API).

    Examples
    --------
    - "What is the revenue of Reliance in 2024?"
    - "Compare net profit of TCS and Infosys"
    - "Top 5 companies by operating profit margin"
    - "Show me HDFC Bank balance sheet"
    - "What is the debt to equity ratio of Tata Motors?"
    """
    result = ask(req.question)
    return QueryResponse(**result)
