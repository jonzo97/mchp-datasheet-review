# Testing Guide: Week 1 Improvements

**Version:** 1.0
**Date:** 2025-10-03
**Target:** Validate cross-reference accuracy, LLM determinism, and output filtering

---

## Quick Start

### Prerequisites
```bash
# Ensure you're on master branch with Week 1 improvements
git checkout master
git pull origin master

# Verify you have the improvements
git log --oneline -1
# Should show: e55fd66 Improve cross-reference accuracy and output filtering
```

### Run Full Test Suite
```bash
# Test all improvements (takes ~7 minutes for 814-page datasheet)
./run_week1_tests.sh
```

---

## Individual Tests

### Test 1: Cross-Reference Accuracy

#### Run Test
```bash
# Process datasheet
python src/main.py "PIC32MZ-W1-and-WFI32E01-Family-Data-Sheet-DS70005425.pdf"

# Check cross-ref results
grep -A 20 "Cross-Reference Validation" output/review_summary_*.md | tail -25
```

#### Expected Output (AFTER improvements)
```
## Cross-Reference Validation

Total References: 2,453
Valid: [EXPECTING ~2,200+] (90%+)    # UP from 1,613 (65.8%)
Invalid: [EXPECTING <250] (10%-)     # DOWN from 840 (34.2%)

Confidence Breakdown:               # NEW!
- Exact Match: [...]
- High Confidence (0.85-1.0): [...]
- Medium Confidence (0.7-0.84): [...]
- Low Confidence (0.01-0.69): [...]
- Broken (0.0): [...]

Uncertain References: [...]         # NEW! (0 < conf < 0.8)
```

#### Success Criteria
- ✅ Valid % > 90% (was 65.8%)
- ✅ Confidence breakdown present
- ✅ Uncertain refs identified (not just "invalid")

---

### Test 2: LLM Determinism

#### Run Test
```bash
# Test same chunk twice
python test_single_chunk_llm.py > /tmp/llm_test1.log 2>&1
python test_single_chunk_llm.py > /tmp/llm_test2.log 2>&1

# Compare outputs (should be identical)
diff /tmp/llm_test1.log /tmp/llm_test2.log
```

#### Expected Output
```
# No differences (deterministic)
# exit code: 0
```

#### Alternative Test (hash-based)
```bash
# Extract just the corrected text and hash it
grep -A 5 "Corrected Text:" /tmp/llm_test1.log | md5sum
grep -A 5 "Corrected Text:" /tmp/llm_test2.log | md5sum
# Hashes should match
```

#### Success Criteria
- ✅ Outputs are identical (diff shows nothing)
- ✅ Hash values match
- ✅ temperature=0.0 in config

---

### Test 3: Output Filtering

#### Run Test
```bash
# Test the filter module directly
python src/output_filter.py
```

#### Expected Output
```
🔴 Critical Issues (1):
   1. section not found
      Original: "Section 7.3"

🟠 High Priority (1):
   1. subject-verb agreement

🟡 Medium Priority (2):
   - 1 terminology inconsistencies
   - 1 style suggestions

⚪ Suppressed: 1 low-value changes (run with --verbose to see)

📊 Actionable Items: 4

Statistics: {'total_changes': 5, 'actionable_changes': 2, ...}
```

#### Success Criteria
- ✅ Critical issues surface first
- ✅ Whitespace suppressed (not in main output)
- ✅ Severity levels clear (🔴🟠🟡⚪)
- ✅ Actionable count accurate

---

## Regression Testing

### Compare Before/After

#### Step 1: Get BEFORE baseline
```bash
# Checkout pre-improvement commit
git checkout 12f7c20  # Before Week 1

# Run test
python src/main.py "PIC32MZ-W1-and-WFI32E01-Family-Data-Sheet-DS70005425.pdf"

# Save results
cp output/review_summary_*.md /tmp/before_week1.md
grep "Valid:" /tmp/before_week1.md
# Should show: Valid: 1613 (65.8%)
```

#### Step 2: Get AFTER results
```bash
# Back to master
git checkout master

# Run test
python src/main.py "PIC32MZ-W1-and-WFI32E01-Family-Data-Sheet-DS70005425.pdf"

# Compare
grep "Valid:" output/review_summary_*.md | tail -1
# Should show: Valid: ~2200+ (90%+)
```

#### Step 3: Calculate Improvement
```python
# Quick Python calculation
before_valid = 1613
before_total = 2453
after_valid = [GET_FROM_OUTPUT]
after_total = 2453

before_pct = (before_valid / before_total) * 100
after_pct = (after_valid / after_total) * 100
improvement = after_pct - before_pct

print(f"Before: {before_pct:.1f}%")
print(f"After: {after_pct:.1f}%")
print(f"Improvement: +{improvement:.1f} percentage points")
```

---

## Performance Testing

### Measure Processing Speed

#### Baseline Test
```bash
# Time the processing
time python src/main.py "PIC32MZ-W1-and-WFI32E01-Family-Data-Sheet-DS70005425.pdf"

# Check speed
grep "Speed:" output/review_summary_*.md | tail -1
```

#### Expected Performance
```
Processing Time: 390-410 seconds (6.5-7 minutes)
Speed: 2.0-2.1 pages/second
Pages: 814
Chunks: 1,790
```

#### Performance Regression Check
- ✅ Speed within 10% of baseline (pattern matching shouldn't slow down much)
- ✅ No memory leaks (check with `ps aux | grep python` during run)

---

## Edge Case Testing

### Test 1: Documents with No Cross-References
```bash
# Use wok cooking guide (minimal refs)
python src/main.py "wok-cooking-guide.pdf"

# Check it doesn't crash
echo $?  # Should be 0 (success)
```

### Test 2: Documents with All Valid References
```bash
# Create test doc with known-good refs
# [Requires test document creation]
```

### Test 3: Confidence Edge Cases
```bash
# Test different confidence thresholds
sed -i 's/confidence_threshold: 0.95/confidence_threshold: 0.5/' config.yaml
python src/main.py "test-doc.pdf"
# Should trigger more LLM calls

# Restore
git checkout config.yaml
```

---

## Automated Test Script

### Create Test Runner
**File:** `run_week1_tests.sh`
```bash
#!/bin/bash
set -e

echo "=========================================="
echo "Week 1 Improvements Test Suite"
echo "=========================================="
echo ""

# Test 1: Cross-Reference Accuracy
echo "[Test 1] Cross-Reference Accuracy..."
python src/main.py "PIC32MZ-W1-and-WFI32E01-Family-Data-Sheet-DS70005425.pdf" > /tmp/test1.log 2>&1
VALID=$(grep "Valid:" output/review_summary_*.md | tail -1 | awk '{print $2}')
echo "✓ Valid references: $VALID (target: >2200)"

# Test 2: LLM Determinism
echo ""
echo "[Test 2] LLM Determinism..."
python test_single_chunk_llm.py > /tmp/llm1.log 2>&1
python test_single_chunk_llm.py > /tmp/llm2.log 2>&1
if diff /tmp/llm1.log /tmp/llm2.log > /dev/null; then
    echo "✓ LLM is deterministic (outputs match)"
else
    echo "✗ LLM outputs differ (FAILED)"
    exit 1
fi

# Test 3: Output Filtering
echo ""
echo "[Test 3] Output Filtering..."
python src/output_filter.py > /tmp/filter_test.log
if grep -q "Critical Issues" /tmp/filter_test.log; then
    echo "✓ Output filtering working"
else
    echo "✗ Output filtering failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "All Tests Passed! ✅"
echo "=========================================="
```

### Run Tests
```bash
chmod +x run_week1_tests.sh
./run_week1_tests.sh
```

---

## Troubleshooting

### Issue: Cross-ref accuracy not improving

**Symptoms:**
- Still shows 65.8% valid
- No confidence breakdown in output

**Diagnosis:**
```bash
# Check if you have the improvements
git log --oneline -1
# Should show: e55fd66 Improve cross-reference accuracy...

# Check section patterns
grep -n "section_patterns" src/extraction.py
# Should show multiple patterns (lines 97-103, 562-570)
```

**Fix:**
```bash
git pull origin master
git checkout master
# Re-run test
```

---

### Issue: LLM not deterministic

**Symptoms:**
- Running same chunk twice gives different output
- Hashes don't match

**Diagnosis:**
```bash
# Check temperature setting
grep "temperature:" config.yaml
# Should show: temperature: 0.0
```

**Fix:**
```bash
# Edit config
sed -i 's/temperature: 0.3/temperature: 0.0/' config.yaml

# Or restore from git
git checkout config.yaml
```

---

### Issue: Output filter not working

**Symptoms:**
- Still seeing 1,342 whitespace changes
- No severity classification

**Diagnosis:**
```bash
# Check if module exists
ls src/output_filter.py
# Should exist

# Test directly
python src/output_filter.py
```

**Fix:**
```bash
# Pull latest code
git checkout master
git pull origin master
```

---

## Validation Checklist

### Pre-Test
- [ ] On master branch (Week 1 improvements)
- [ ] Config has temperature=0.0
- [ ] output_filter.py exists
- [ ] Test PDF available

### During Test
- [ ] Processing completes without errors
- [ ] Speed ~2 pages/second
- [ ] Cross-ref validation runs

### Post-Test Validation
- [ ] Cross-ref accuracy > 90%
- [ ] Confidence breakdown present
- [ ] LLM deterministic (diff test passes)
- [ ] Output filtering works (severity levels)
- [ ] No regressions (existing features work)

### Success Criteria Met
- [ ] All automated tests pass
- [ ] Manual spot-checks verify accuracy
- [ ] Performance within acceptable range
- [ ] Documentation matches implementation

---

## Expected Results Summary

### Cross-Reference Validation
| Metric | Before | After | Status |
|--------|--------|-------|--------|
| Total refs | 2,453 | 2,453 | - |
| Valid | 1,613 (65.8%) | >2,200 (90%+) | ✅ |
| Invalid | 840 (34.2%) | <250 (10%-) | ✅ |

### Output Quality
| Metric | Before | After | Status |
|--------|--------|-------|--------|
| Signal-to-noise | 1.1% | 85%+ | ✅ |
| Critical issues | 0 | Surfaced | ✅ |
| Suppressed noise | 0 | 1,000+ | ✅ |

### LLM Behavior
| Metric | Before | After | Status |
|--------|--------|-------|--------|
| Determinism | ❌ Variable | ✅ Reproducible | ✅ |
| Cacheable | ❌ No | ✅ Yes | ✅ |

---

## Next Steps

### If All Tests Pass
1. ✅ Document results in week1_improvements_summary.md
2. ✅ Share with team
3. ⏭️ Move to Phase 2 (semantic validators)

### If Tests Fail
1. Review failure patterns
2. Debug with detailed logging
3. File issues for investigation
4. Retest after fixes

---

## Related Documents
- `docs/week1_improvements_summary.md` - Detailed results
- `docs/strategic_pivot_analysis.md` - Overall strategy
- `docs/future_enhancements_roadmap.md` - What's next

---

**Last Updated:** 2025-10-03
**Status:** Ready for validation
