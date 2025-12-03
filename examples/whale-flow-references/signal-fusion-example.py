"""
Signal Fusion Example
Purpose: Demonstrate the simple, weighted logic for combining the leading
         indicator (Whale Flow) with the confirmation indicator (UTXO Confidence)
         to produce a final, actionable trading signal.
"""

def fuse_signals(net_flow_btc: float, utxo_confidence: float) -> dict:
    """
    Combines whale flow and UTXO confidence into a single trading signal.

    Args:
        net_flow_btc: Net BTC flow to/from exchanges. Positive means inflow (bearish),
                      negative means outflow (bullish).
        utxo_confidence: Confidence score from UTXOracle (0-1).

    Returns:
        A dictionary containing the final action and a combined confidence score.
    """
    # --- 1. Define Thresholds ---
    WHALE_ACCUMULATION_THRESHOLD_BTC = -1000 # Net outflow > 1000 BTC is strong accumulation
    WHALE_DISTRIBUTION_THRESHOLD_BTC = 1000  # Net inflow > 1000 BTC is strong distribution
    UTXO_HEALTHY_THRESHOLD = 0.7
    UTXO_WEAK_THRESHOLD = 0.4

    # --- 2. Assign Votes (-1 for Bearish, 1 for Bullish, 0 for Neutral) ---
    whale_vote = 0
    if net_flow_btc < WHALE_ACCUMULATION_THRESHOLD_BTC:
        whale_vote = 1.0  # Strong Bullish: Whales are withdrawing from exchanges
    elif net_flow_btc > WHALE_DISTRIBUTION_THRESHOLD_BTC:
        whale_vote = -1.0 # Strong Bearish: Whales are sending to exchanges to sell

    utxo_vote = 0
    if utxo_confidence > UTXO_HEALTHY_THRESHOLD:
        utxo_vote = 0.5 # Mildly Bullish: On-chain activity is organic and healthy
    elif utxo_confidence < UTXO_WEAK_THRESHOLD:
        utxo_vote = -0.5 # Mildly Bearish: On-chain activity is uncertain or anomalous

    # --- 3. Combine Votes with Weighting ---
    # Whale flow is a stronger, leading indicator, so it gets more weight.
    WHALE_VOTE_WEIGHT = 0.7
    UTXO_VOTE_WEIGHT = 0.3
    
    combined_signal = (whale_vote * WHALE_VOTE_WEIGHT) + (utxo_vote * UTXO_VOTE_WEIGHT)

    # --- 4. Determine Final Action ---
    ACTION_THRESHOLD = 0.6
    
    action = "HOLD"
    if combined_signal > ACTION_THRESHOLD:
        action = "BUY"
    elif combined_signal < -ACTION_THRESHOLD:
        action = "SELL"
        
    return {
        "action": action,
        "combined_signal_score": round(combined_signal, 4),
        "whale_vote": whale_vote,
        "utxo_vote": utxo_vote
    }

if __name__ == "__main__":
    print("--- Testing Signal Fusion Logic ---")

    # Scenario 1: Strong Whale Accumulation + Healthy Market
    # Expected: Strong BUY signal
    signal_1 = fuse_signals(net_flow_btc=-1500, utxo_confidence=0.8)
    print(f"\nScenario 1: Whale Outflow > 1k BTC, UTXO Confidence > 0.7")
    print(f"  -> Result: {signal_1}")
    assert signal_1["action"] == "BUY"

    # Scenario 2: Strong Whale Distribution + Weak Market
    # Expected: Strong SELL signal
    signal_2 = fuse_signals(net_flow_btc=2000, utxo_confidence=0.3)
    print(f"\nScenario 2: Whale Inflow > 1k BTC, UTXO Confidence < 0.4")
    print(f"  -> Result: {signal_2}")
    assert signal_2["action"] == "SELL"

    # Scenario 3: No significant whale activity, but healthy market
    # Expected: HOLD (not enough conviction to BUY)
    signal_3 = fuse_signals(net_flow_btc=100, utxo_confidence=0.9)
    print(f"\nScenario 3: Neutral Whale Flow, Healthy UTXO Confidence")
    print(f"  -> Result: {signal_3}")
    assert signal_3["action"] == "HOLD"

    # Scenario 4: Whale accumulation, but very weak market confidence
    # The two signals cancel each other out.
    # Expected: HOLD
    signal_4 = fuse_signals(net_flow_btc=-1200, utxo_confidence=0.2)
    print(f"\nScenario 4: Whale Outflow > 1k BTC, but Weak UTXO Confidence")
    print(f"  -> Result: {signal_4}")
    assert signal_4["action"] == "HOLD"
    
    print("\n--- Example complete ---")
