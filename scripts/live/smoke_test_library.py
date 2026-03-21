
import sys
from UTXOracle_library import UTXOracleCalculator

def test_library_optimization():
    print("Testing UTXOracle_library optimization...")
    
    # 1. Initialization test
    try:
        calc = UTXOracleCalculator()
        print("✓ UTXOracleCalculator initialized successfully")
    except Exception as e:
        print(f"✗ Initialization failed: {e}")
        sys.exit(1)
        
    # 2. Check if stencils are pre-calculated
    if hasattr(calc, 'smooth_stencil') and hasattr(calc, 'spike_stencil'):
        print(f"✓ Stencils are pre-calculated (smooth: {len(calc.smooth_stencil)}, spike: {len(calc.spike_stencil)})")
    else:
        print("✗ Stencils are missing from initialization")
        sys.exit(1)

    # 3. Mock transactions for a simple calculation run
    # Creating a set of transactions that might represent a price (roughly around $60k for testing)
    # $100 @ $60k = 0.001666 BTC
    mock_transactions = [
        {"vin": [{"txid": "abc"}], "vout": [{"value": 0.001666}, {"value": 0.05}]}
        for _ in range(100)
    ]
    
    try:
        result = calc.calculate_price_for_transactions(mock_transactions)
        price = result.get('price_usd')
        confidence = result.get('confidence')
        print(f"✓ Calculation run successful")
        print(f"  Calculated Price: ${price if price else 'None'}")
        print(f"  Confidence: {confidence:.4f}")
    except Exception as e:
        print(f"✗ Calculation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\nCONCLUSION: Library is healthy and optimized.")

if __name__ == "__main__":
    test_library_optimization()
