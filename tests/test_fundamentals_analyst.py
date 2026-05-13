from tradingagents.agents.analysts.fundamentals_analyst import (
    _strip_portfolio_recommendations,
)


def test_strip_portfolio_recommendation_block():
    report = """# Fundamentals

## Liquidity
Current ratio is 1.35.

3. **Recommendation:**
   - **Short-Term:** Consider long positions.
   - **Long-Term:** Monitor debt.

## Summary
Net income is period-consistent.
"""

    cleaned = _strip_portfolio_recommendations(report)

    assert "Recommendation" not in cleaned
    assert "Consider long positions" not in cleaned
    assert "Monitor debt" not in cleaned
    assert "Current ratio is 1.35" in cleaned
    assert "Net income is period-consistent" in cleaned

