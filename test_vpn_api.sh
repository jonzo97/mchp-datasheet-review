#!/bin/bash
# Test Microchip API from VPN and save results
# Run this while ON VPN, then disconnect and check test_vpn_results.txt

OUTPUT_FILE="test_vpn_results.txt"

echo "======================================================================" > "$OUTPUT_FILE"
echo "Microchip API VPN Test - $(date)" >> "$OUTPUT_FILE"
echo "======================================================================" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Test 1: DNS resolution
echo "Test 1: DNS Resolution" >> "$OUTPUT_FILE"
echo "---" >> "$OUTPUT_FILE"
nslookup ai-apps.microchip.com >> "$OUTPUT_FILE" 2>&1
echo "" >> "$OUTPUT_FILE"

# Test 2: Simple curl test (with timeout)
echo "Test 2: Curl Connection Test (15s timeout)" >> "$OUTPUT_FILE"
echo "---" >> "$OUTPUT_FILE"
curl -X POST https://ai-apps.microchip.com/chatbotAPI-test/api/chat/chatcompletions \
  -H "Content-Type: application/json" \
  -H "api-key: ${MCHP_LLM_API_KEY}" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}], "temperature": 0.3, "stream": true}' \
  --max-time 15 \
  --no-buffer \
  >> "$OUTPUT_FILE" 2>&1

echo "" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Test 3: Reference implementation (colleague's code)
echo "Test 3: Reference LLM Implementation (colleague's llm.py)" >> "$OUTPUT_FILE"
echo "---" >> "$OUTPUT_FILE"
timeout 45 python test_reference_llm.py >> "$OUTPUT_FILE" 2>&1

echo "" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Test 4: Our implementation
echo "Test 4: Our LLM Implementation (src/llm_client.py)" >> "$OUTPUT_FILE"
echo "---" >> "$OUTPUT_FILE"
timeout 45 python test_mchp_api.py >> "$OUTPUT_FILE" 2>&1

echo "" >> "$OUTPUT_FILE"
echo "======================================================================" >> "$OUTPUT_FILE"
echo "Test complete. Disconnect from VPN and check: $OUTPUT_FILE" >> "$OUTPUT_FILE"
echo "======================================================================" >> "$OUTPUT_FILE"

# Print to console too
echo ""
echo "✓ Tests complete! Results saved to: $OUTPUT_FILE"
echo ""
echo "Next steps:"
echo "  1. Disconnect from VPN"
echo "  2. Run: cat $OUTPUT_FILE"
echo "  3. Share results with Claude Code"
echo ""
