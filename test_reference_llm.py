"""
Test script using colleague's reference/llm.py implementation.
This will help determine if the issue is our code or network/environment.
"""

import sys
import os

# Add reference folder to path
sys.path.insert(0, 'reference')

# Mock the logger since we don't have it
class MockLogger:
    def log(self, msg, console=True, file=False):
        print(msg)

sys.modules['logger'] = type('module', (), {'logger': MockLogger()})()

from llm import LLM

def test_reference_implementation():
    """Test the colleague's working LLM implementation."""

    print("=" * 70)
    print("Testing Colleague's Reference LLM Implementation")
    print("=" * 70)
    print()

    # Check API key
    api_key = os.getenv("MCHP_LLM_API_KEY")
    if not api_key:
        # Try loading from local_config
        try:
            from local_config import MCHP_LLM_API_KEY
            api_key = MCHP_LLM_API_KEY
            os.environ["MCHP_LLM_API_KEY"] = api_key  # Set for reference code
        except ImportError:
            pass

    if not api_key:
        print("❌ ERROR: No API key found!")
        return False

    print(f"✓ API Key found: {api_key[:10]}...{api_key[-4:]}")
    print()

    # Initialize LLM
    print("Initializing LLM client...")
    llm = LLM()
    llm.setup(
        temperature=0.3,
        max_tokens=500
    )
    print("✓ Client initialized")
    print()

    # Test simple chat
    print("-" * 70)
    print("Test: Simple Chat Request")
    print("-" * 70)

    test_prompt = """Review this technical text for errors:

The PIC32MZ W1 Family of devices are general purpose, low-cost, 32-bit
Microcontroller (MCU) with integrated Wi-Fi."""

    print(f"Prompt:\n  {test_prompt[:100]}...")
    print()
    print("Sending request to API...")
    print("(This may take 10-30 seconds)")
    print()

    try:
        response = llm.chat(test_prompt)

        print("✓ SUCCESS! Received response:")
        print("-" * 70)
        print(response[:500])
        if len(response) > 500:
            print(f"\n... (truncated, total {len(response)} chars)")
        print("-" * 70)
        print()

        # Token counting test
        token_count = llm.token_count(test_prompt)
        print(f"✓ Token count working: {token_count} tokens")
        print()

        return True

    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        print()
        print("Full traceback:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_reference_implementation()

    print()
    print("=" * 70)
    if success:
        print("✓ Reference implementation works!")
        print()
        print("This confirms:")
        print("  - Network/VPN connection is OK")
        print("  - API key is valid")
        print("  - Microchip API is accessible")
        print()
        print("Next: Compare with our implementation to find differences")
    else:
        print("❌ Reference implementation failed")
        print()
        print("This suggests:")
        print("  - Network/VPN issue (not connected or wrong network)")
        print("  - API key invalid")
        print("  - Microchip API not accessible from current location")
    print("=" * 70)

    sys.exit(0 if success else 1)
