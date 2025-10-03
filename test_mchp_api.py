"""
Test script for Microchip LLM API integration.
Validates streaming API connection and response format.
"""

import asyncio
import os
import sys
import yaml
from datetime import datetime

# Add src to path
sys.path.insert(0, 'src')

# Try to import local config for API key fallback (not in git)
try:
    from local_config import MCHP_LLM_API_KEY as LOCAL_API_KEY
except ImportError:
    LOCAL_API_KEY = None

from llm_client import LLMClient


async def test_api_connection():
    """Test the Microchip LLM API connection with streaming."""

    print("=" * 70)
    print("Microchip LLM API Test Script")
    print("=" * 70)
    print()

    # Check environment variable or local config fallback
    api_key = os.getenv("MCHP_LLM_API_KEY") or LOCAL_API_KEY
    if not api_key:
        print("❌ ERROR: MCHP_LLM_API_KEY environment variable not set and no local_config.py found!")
        print()
        print("Please either:")
        print("  1. Set environment variable: export MCHP_LLM_API_KEY='your-api-key-here'")
        print("  2. Create local_config.py with: MCHP_LLM_API_KEY = 'your-api-key-here'")
        print()
        return False

    print(f"✓ API Key found: {api_key[:10]}...{api_key[-4:]}")
    print()

    # Load configuration
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"❌ ERROR: Failed to load config.yaml: {e}")
        return False

    # Enable LLM for testing
    config['llm']['enabled'] = True

    print("Configuration:")
    print(f"  API URL: {config['llm']['api_url']}")
    print(f"  Model: {config['llm']['model']}")
    print(f"  Streaming: {config['llm']['stream']}")
    print(f"  Timeout: {config['llm']['stream_timeout']}s")
    print()

    # Create LLM client
    print("Initializing LLM client...")
    async with LLMClient(config) as client:
        print("✓ Client initialized")
        print()

        # Test 1: Simple review
        print("-" * 70)
        print("Test 1: Simple Technical Text Review")
        print("-" * 70)

        test_text = """The PIC32MZ W1 Family of devices are general purpose, low-
cost, 32-bit Microcontroller (MCU) with the Wi-Fi and network
connectivity, hardware-based security accelerator, and Power
Management Unit (PMU)."""

        print("Input text:")
        print(f"  {test_text[:100]}...")
        print()

        try:
            start_time = datetime.now()
            print("Sending request to API...")
            print("(Streaming chunks will appear as they arrive)")
            print()

            # Call the API
            response = await client.review_text(test_text, context="Technical datasheet")

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            print()
            print("✓ Response received!")
            print(f"  Duration: {duration:.2f}s")
            print(f"  Confidence: {response.confidence:.2f}")
            print()
            print("Reviewed content:")
            print("-" * 70)
            print(response.content)
            print("-" * 70)
            print()

            if response.reasoning:
                print("Reasoning:")
                print(response.reasoning)
                print()

            if response.metadata and response.metadata.get('changes'):
                print(f"Changes found: {len(response.metadata['changes'])}")
                print()

        except Exception as e:
            print(f"❌ ERROR: {e}")
            print()
            import traceback
            traceback.print_exc()
            return False

        # Test 2: More complex text with potential issues
        print()
        print("-" * 70)
        print("Test 2: Text with Potential Issues")
        print("-" * 70)

        test_text2 = """The module supports  multiple antenna options. The WFI32E01
and WFI32E02 have different configurations for  power management.
Refer to Section  10.5 for more details on the power specifications."""

        print("Input text (with spacing and reference issues):")
        print(f"  {test_text2}")
        print()

        try:
            start_time = datetime.now()
            print("Sending request to API...")
            print()

            response2 = await client.review_text(test_text2, context="Technical datasheet section")

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            print()
            print("✓ Response received!")
            print(f"  Duration: {duration:.2f}s")
            print(f"  Confidence: {response2.confidence:.2f}")
            print()
            print("Reviewed content:")
            print("-" * 70)
            print(response2.content)
            print("-" * 70)
            print()

        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

        # Summary
        print()
        print("=" * 70)
        print("✓ API Test Complete - All Tests Passed!")
        print("=" * 70)
        print()
        print("Your Microchip LLM API is working correctly!")
        print()
        print("Next steps:")
        print("  1. Run on a small document:")
        print("     python src/main.py --with-llm small_document.pdf")
        print()
        print("  2. Run on the large document:")
        print("     python src/main.py --with-llm PIC32MZ-W1-and-WFI32E01-Family-Data-Sheet-DS70005425.pdf")
        print()

        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_api_connection())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
