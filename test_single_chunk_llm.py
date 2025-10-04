"""
Test LLM review on a single chunk with low confidence.
Allows rapid iteration without processing full documents.
"""

import asyncio
import sys
import yaml

sys.path.insert(0, 'src')

from llm_client import LLMClient


async def test_single_chunk():
    """Test LLM on a problematic chunk."""

    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Sample chunk that triggers LLM (low confidence from rule-based review)
    # This is typical technical content with minor formatting issues
    test_chunk = """The PIC32MZ W1 Family of devices are general purpose, low-
cost, 32-bit Microcontroller (MCU) with the Wi-Fi® and net­
work connectivity, hardware-based security accelerator, trans­
ceiver and Power Management Unit (PMU). It also supports
interface to an External Front-End Module."""

    print("=" * 70)
    print("Testing Single Chunk LLM Review")
    print("=" * 70)
    print()
    print("Test Chunk:")
    print("-" * 70)
    print(test_chunk)
    print("-" * 70)
    print()

    # Initialize LLM client
    async with LLMClient(config) as client:
        if not client.is_available():
            print("❌ ERROR: LLM client not available")
            print("   - Check API key is set")
            print("   - Ensure you're on office network or VPN")
            return False

        print("✓ LLM client initialized")
        print()

        # Send to LLM
        print("Sending to LLM API...")
        try:
            response = await client.review_text(
                test_chunk,
                context="Section: INTRODUCTION, PIC32MZ W1 datasheet"
            )

            print("✓ Response received!")
            print()
            print("=" * 70)
            print("LLM Response Details")
            print("=" * 70)
            print()
            print(f"Confidence: {response.confidence:.2f}")
            print()
            print("Corrected Text:")
            print("-" * 70)
            print(response.content)
            print("-" * 70)
            print()

            if response.reasoning:
                print("Reasoning:")
                print(response.reasoning)
                print()

            if response.metadata and 'changes' in response.metadata:
                changes = response.metadata['changes']
                print(f"Changes ({len(changes)} total):")
                print("-" * 70)
                for i, change in enumerate(changes, 1):
                    if isinstance(change, dict):
                        print(f"{i}. Original: \"{change.get('original', 'N/A')}\"")
                        print(f"   Corrected: \"{change.get('corrected', 'N/A')}\"")
                        print(f"   Reason: {change.get('reason', 'N/A')}")
                    elif isinstance(change, str):
                        print(f"{i}. {change}")
                    print()
            else:
                print("No changes metadata returned")

            print("=" * 70)
            print("✓ Test Complete!")
            print("=" * 70)

            return True

        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_single_chunk())
    sys.exit(0 if success else 1)
