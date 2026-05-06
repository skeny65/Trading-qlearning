"""
Reward calculator for Q-Learning agent.

Reward formula (from plan):
    r  = pnl_pct
    r -= 0.05                      # commission + slippage
    r -= 0.1  if duration > 4h
    r -= 0.5  if account_drawdown < -10%
    r += 0.2  if pnl_pct > 0 and r_multiple >= 2
"""
import logging

logger = logging.getLogger("bot3.reward")


def compute_reward(trade_result: dict) -> float:
    """
    Compute reward from a closed trade result.

    Expected keys in trade_result:
        pnl_pct              (float) - gain/loss in percent
        duration_min         (float) - trade duration in minutes
        account_drawdown_pct (float) - account drawdown %  (negative = loss)
        r_multiple           (float, optional) - R multiple achieved
    """
    pnl_pct           = float(trade_result.get("pnl_pct",              0.0))
    duration_min      = float(trade_result.get("duration_min",          0.0))
    drawdown_global   = float(trade_result.get("account_drawdown_pct",  0.0))
    r_multiple        = float(trade_result.get("r_multiple",            0.0))

    r  = pnl_pct
    r -= 0.05                           # commission + slippage

    if duration_min > 240:              # > 4 hours
        r -= 0.1

    if drawdown_global < -10:           # account bleeding
        r -= 0.5

    if pnl_pct > 0 and r_multiple >= 2:
        r += 0.2                        # bonus for high R

    logger.debug(
        f"Reward: pnl={pnl_pct:.3f}% dur={duration_min:.0f}m "
        f"dd={drawdown_global:.1f}% r={r_multiple:.1f}x -> reward={r:.4f}"
    )
    return round(r, 6)
