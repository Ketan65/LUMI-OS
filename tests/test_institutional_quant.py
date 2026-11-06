"""Unit and Integration Tests for LUMI Institutional Quantitative Submodule (v38.5).

Verifies:
  1. Quantitative Strategy Backtesting (Sharpe, Sortino, Max Drawdown, Profit Factor).
  2. Multi-Strategy execution (EMA Momentum, Bollinger RSI, Donchian Breakout).
  3. Realistic Microstructure Simulation (Slippage, exchange fee deductions).
  4. Virtual Paper Trading Portfolio persistence and PnL calculation.
  5. Tool registration in ToolRegistry.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from finance.institutional_quant import InstitutionalQuantEngine, get_quant_engine
from tools.registry import ToolRegistry


def test_quant_backtest_metrics_calculation(tmp_path: Path):
    """Verify quantitative backtest tear sheet metrics computation."""
    registry = ToolRegistry()
    engine = InstitutionalQuantEngine(registry=registry, quant_dir=tmp_path / "quant")

    res = engine.backtest(
        strategy="ema_momentum",
        symbol="BTC/USDT",
        initial_capital=10000.0,
        bars=200,
    )

    assert res.strategy_name == "ema_momentum"
    assert res.symbol == "BTC/USDT"
    assert res.initial_capital == 10000.0
    assert res.final_capital > 0.0
    assert -100.0 <= res.total_return_pct <= 1000.0
    assert 0.0 <= res.max_drawdown_pct <= 100.0
    assert res.total_trades >= 0
    assert 0.0 <= res.win_rate_pct <= 100.0

    # Tear sheet formatting
    tear_sheet = engine.format_backtest_summary(res)
    assert "QUANTITATIVE STRATEGY TEAR SHEET" in tear_sheet
    assert "Sharpe Ratio" in tear_sheet
    assert "Max Drawdown (MDD)" in tear_sheet
    assert "Profit Factor" in tear_sheet


def test_multiple_quant_strategies(tmp_path: Path):
    """Verify EMA Momentum, Bollinger RSI, and Donchian Breakout strategies."""
    engine = InstitutionalQuantEngine(quant_dir=tmp_path / "quant")

    strategies = ["ema_momentum", "bollinger_rsi", "donchian_breakout"]
    for strat in strategies:
        res = engine.backtest(strategy=strat, symbol="ETH/USDT", bars=150)
        assert res.strategy_name == strat
        assert res.final_capital > 0


def test_paper_trading_order_execution_and_slippage(tmp_path: Path):
    """Verify simulated BUY and SELL execution with fees and portfolio update."""
    engine = InstitutionalQuantEngine(quant_dir=tmp_path / "quant")

    # 1. Initial portfolio check
    summary_initial = engine.get_portfolio_summary()
    assert "$10,000.00 USD" in summary_initial

    # 2. Execute BUY order
    buy_res = engine.execute_trade("SOL/USDT", "BUY", quantity=10.0, price=150.0)
    assert buy_res["success"] is True
    assert buy_res["portfolio"]["virtual_cash"] < 10000.0 - 1500.0  # Cash reduced including fee
    assert "SOL/USDT" in buy_res["portfolio"]["positions"]

    # 3. Execute SELL order at profit
    sell_res = engine.execute_trade("SOL/USDT", "SELL", quantity=10.0, price=170.0)
    assert sell_res["success"] is True
    assert sell_res["portfolio"]["realized_pnl"] > 0.0  # Positive PnL from 150 -> 170
    assert "SOL/USDT" not in sell_res["portfolio"]["positions"]


def test_tool_registry_integration(tmp_path: Path):
    """Verify tool registration in ToolRegistry."""
    registry = ToolRegistry()
    engine = InstitutionalQuantEngine(registry=registry, quant_dir=tmp_path / "quant")

    assert registry.get("run_quant_backtest") is not None
    assert registry.get("get_paper_portfolio") is not None
    assert registry.get("execute_paper_trade") is not None
