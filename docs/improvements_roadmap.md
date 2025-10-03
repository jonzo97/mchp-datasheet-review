# Datasheet Review System - Improvements Roadmap

**Version:** 0.1.0 → 1.0.0
**Timeline:** 4-6 weeks to production
**Last Updated:** 2025-10-03

---

## Overview

This roadmap outlines the path from MVP (current state) to production-ready v1.0. Priorities are based on impact to quality, user trust, and business value.

---

## Priority 1: Critical Bug Fixes (Week 1)

### 🔴 Issue #1: Style Checker False Positives
**Status:** BLOCKER
**Impact:** Corrupts technical terminology
**Effort:** 2-4 hours

**Problem:**
```python
# Current regex in review_language.py line ~105
range_pattern = r'(\d+)\s+-\s+(\d+)'

# Matches: "25519\n- 512" and converts to "25519-512"
# This breaks: "Curve25519" into "Curve25519-512"
```

**Solution:**
```python
# Option A: Only match within same line
range_pattern = r'(\d+)\s+-\s+(\d+)(?!\n)'

# Option B: More restrictive - require space before digit
range_pattern = r'(\d+)\s+-\s+(\d+)(?=\s|$)'

# Option C: Context-aware (recommended)
# Don't match if preceded by word character
range_pattern = r'(?<!\w)(\d+)\s+-\s+(\d+)(?!\n)'
```

**Testing:**
- Add unit test with "Curve25519\n- 512" pattern
- Test against sample of 100 pages from datasheet
- Verify no false positives

**Acceptance Criteria:**
- ✅ "Curve25519" unchanged
- ✅ "1 - 5" still converts to "1-5"
- ✅ No new false positives introduced

---

### 🔴 Issue #2: Technical Term Whitelist
**Status:** HIGH PRIORITY
**Impact:** Prevents future false positives
**Effort:** 4-6 hours

**Solution:**
1. Create `config/technical_terms.txt`:
```
# Cryptographic algorithms
Curve25519
Ed25519
AES-256
SHA-256

# Electronics terms
U.FL
GPIO
SPI
I2C
UART

# Microcontroller-specific
PIC32MZ
WFI32E01
```

2. Update `review_language.py`:
```python
def _load_technical_terms(self):
    """Load technical terms that should never be modified."""
    terms = set()

    # Built-in terms
    terms.update(self.technical_terms)

    # Load from file if exists
    term_file = self.config.get('language_review', {}).get('technical_dictionary')
    if term_file and Path(term_file).exists():
        with open(term_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    terms.add(line)

    return terms
```

3. Skip changes that would modify whitelisted terms:
```python
def _should_skip_change(self, original, position, content):
    """Check if change would modify a technical term."""
    context = content[max(0, position-20):position+len(original)+20]

    for term in self.protected_terms:
        if term in context:
            return True

    return False
```

**Testing:**
- Create test suite with 50 technical terms
- Verify whitelist prevents modifications
- Test case-sensitivity

**Acceptance Criteria:**
- ✅ Whitelisted terms never modified
- ✅ Case-insensitive matching
- ✅ User-configurable dictionary

---

### ⚠️ Issue #3: Cross-Reference Validation Accuracy
**Status:** HIGH PRIORITY
**Impact:** 50% false positive rate erodes trust
**Effort:** 8-12 hours

**Problem:**
- All 183 section references marked as invalid (likely wrong)
- Pattern matching too strict
- Section header extraction incomplete

**Root Cause Analysis:**
```python
# Current section detection in extraction.py
section_pattern = re.compile(r'^(\d+\.)*\d+\s+[A-Z]')

# Problem: Misses these valid patterns:
# - "3.1  Wi-Fi Features"  (extra space)
# - "Section 3" (no subsection)
# - "3.1 Introduction" (lowercase)
```

**Solution:**

**Phase 1: Improve Section Detection** (4 hours)
```python
# More flexible patterns
section_patterns = [
    r'^(\d+(?:\.\d+)*)\s+[A-Z]',  # Standard: "3.1 TITLE"
    r'^(\d+(?:\.\d+)*)\s+[a-z]',  # Lowercase: "3.1 Introduction"
    r'SECTION\s+(\d+(?:\.\d+)*)', # Explicit: "SECTION 3.1"
    r'^Chapter\s+(\d+)',           # Alternative: "Chapter 3"
]
```

**Phase 2: Add Fuzzy Matching** (4 hours)
```python
from difflib import get_close_matches

def find_closest_target(ref_number, available_targets):
    """Find closest matching target for a reference."""
    # Exact match first
    if ref_number in available_targets:
        return ref_number, 1.0

    # Fuzzy match (e.g., "3.1" matches "3.1.1")
    matches = get_close_matches(ref_number, available_targets, n=1, cutoff=0.8)
    if matches:
        return matches[0], 0.9

    # Parent match (e.g., "3.1.5" → try "3.1")
    parent = '.'.join(ref_number.split('.')[:-1])
    if parent in available_targets:
        return parent, 0.85

    return None, 0.0
```

**Phase 3: Better Reporting** (2 hours)
- Distinguish between "definitely broken" vs "unclear"
- Suggest closest matches for broken refs
- Confidence scoring for validation

**Testing:**
- Test on sections with known structure
- Validate against table of contents
- Cross-check with original PDF

**Acceptance Criteria:**
- ✅ Section ref validation > 80% accuracy
- ✅ Fuzzy matching reduces false positives by 30%+
- ✅ Helpful suggestions for truly broken refs

---

## Priority 2: Quality Improvements (Week 2)

### Table Extraction Enhancement
**Impact:** Reduces manual validation work
**Effort:** 12-16 hours

**Improvements:**
1. **Better table detection:**
   - Heuristics for image-based tables
   - OCR fallback for complex layouts
   - Validate extracted structure

2. **Caption matching:**
   - Improved regex patterns
   - Proximity-based caption search
   - Context awareness

3. **Empty table handling:**
   - Flag tables that failed extraction
   - Provide placeholder for manual review
   - Log extraction failures

**Implementation:**
```python
def _extract_table_robust(self, page, table_index):
    """Enhanced table extraction with fallback."""
    # Try pdfplumber first
    table = page.extract_table()

    if not table or len(table) < 2:
        # Fallback: Try different extraction settings
        table = page.extract_table(table_settings={
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines"
        })

    if not table or len(table) < 2:
        # Last resort: Mark as failed extraction
        return self._create_empty_table_placeholder(page, table_index)

    return self._table_to_markdown(table)
```

**Acceptance Criteria:**
- ✅ Empty table rate < 10%
- ✅ Caption detection rate > 70%
- ✅ Clear flagging of extraction failures

---

### Confidence Score Calibration
**Impact:** Better human review prioritization
**Effort:** 6-8 hours

**Current Issue:** Confidence scores not calibrated with actual accuracy

**Solution:**
1. **Collect ground truth data:**
   - Manual review of 100 chunks
   - Label changes as correct/incorrect
   - Calculate actual accuracy by confidence bin

2. **Calibrate scoring:**
```python
def _calibrate_confidence(self, raw_score, change_type, change_count):
    """Adjust confidence based on empirical accuracy."""

    # Penalize for many changes (likely overfitting)
    if change_count > 10:
        raw_score *= 0.9
    if change_count > 20:
        raw_score *= 0.8

    # Adjust by change type reliability
    type_modifiers = {
        'grammar': 1.0,    # High reliability (double spaces)
        'spelling': 0.95,  # Pretty good
        'style': 0.75,     # Lower reliability (bugs found)
    }

    adjusted = raw_score * type_modifiers.get(change_type, 0.8)

    return min(1.0, adjusted)
```

3. **Add calibration metrics to reports**

**Acceptance Criteria:**
- ✅ Confidence > 0.9 correlates with > 95% accuracy
- ✅ Low-confidence queue is actionable size
- ✅ Documented confidence interpretation

---

## Priority 3: LLM Integration (Weeks 3-4)

### Secure LLM API Connection
**Impact:** Enables semantic review for complex issues
**Effort:** 16-20 hours

**Implementation Plan:**

**Week 3: Infrastructure**
1. **API client hardening:**
   - Secure credential management (env vars, secrets manager)
   - Request/response validation
   - Comprehensive error handling
   - Rate limiting with token bucket algorithm

2. **Prompt engineering:**
```python
REVIEW_PROMPT_TEMPLATE = """
You are reviewing a technical datasheet section. Analyze for:
1. Technical accuracy
2. Clarity and readability
3. Consistency with domain conventions

Context:
- Document: {document_title}
- Section: {section_hierarchy}
- Page: {page_number}

Previous section (for context):
{previous_content}

Current section to review:
{current_content}

Next section (for context):
{next_content}

Provide suggestions in JSON format:
{{
  "issues": [
    {{"type": "technical", "description": "...", "suggested_fix": "..."}}
  ],
  "confidence": 0.95,
  "reasoning": "..."
}}
"""
```

3. **Testing:**
   - Mock LLM responses for unit tests
   - Integration test with real API
   - Load testing for rate limits

**Week 4: Integration & Optimization**
1. **Semi-agentic workflow:**
```
For each chunk:
  Rule-based review → confidence score

  If confidence < 0.85:
    Send to LLM for semantic review
    Merge suggestions
    Recalculate confidence

  If combined confidence > 0.95:
    Auto-approve (with audit trail)
  Else:
    Queue for human review
```

2. **Batch processing:**
   - Group low-confidence chunks
   - Send batches to LLM (cost optimization)
   - Async processing with concurrency limits

3. **Cost tracking:**
   - Token usage monitoring
   - Cost per document calculation
   - Budget alerts

**Acceptance Criteria:**
- ✅ LLM integration functional with secure API
- ✅ Hybrid workflow (rules + LLM) improves accuracy by 15%+
- ✅ Cost per document < $5 (configurable)
- ✅ Processing time < 5 minutes for 800-page doc

---

## Priority 4: Human-in-the-Loop Workflow (Week 5)

### Review Queue Management
**Impact:** Enables human oversight for quality
**Effort:** 20-24 hours

**Features:**

1. **Web UI for Review Queue:**
   - List of chunks needing human review
   - Sort by confidence (lowest first)
   - Filter by issue type
   - Side-by-side diff view

2. **Review Actions:**
   - Approve suggestion
   - Reject suggestion
   - Edit and approve
   - Skip for now
   - Flag for escalation

3. **Learning from Feedback:**
```python
def learn_from_review(self, chunk_id, action, user_edit=None):
    """Update system based on human feedback."""

    review = self.db.get_review(chunk_id)

    if action == 'approve':
        # This pattern is good, increase confidence for similar
        self.pattern_store.add_positive_example(review.changes)

    elif action == 'reject':
        # This pattern is bad, decrease confidence
        self.pattern_store.add_negative_example(review.changes)

        # If repeatedly rejected, disable this rule
        if self.pattern_store.rejection_count(rule_id) > 10:
            self.config.disable_rule(rule_id)

    elif action == 'edit':
        # User provided better suggestion
        self.pattern_store.add_correction(
            original=review.original_content,
            system_suggestion=review.reviewed_content,
            human_correction=user_edit
        )
```

4. **Progress Tracking:**
   - Chunks reviewed / total
   - Approval rate by reviewer
   - Time spent on review
   - Quality metrics

**Tech Stack:**
- Backend: Flask or FastAPI
- Frontend: Simple HTML + HTMX (no heavy JS framework needed)
- Database: Extend existing SQLite

**Acceptance Criteria:**
- ✅ Reviewers can process 50+ chunks/hour
- ✅ System learns from feedback
- ✅ Clear audit trail of all decisions

---

## Priority 5: Production Readiness (Week 6)

### Deployment & Operations
**Impact:** Makes system deployable at scale
**Effort:** 16-20 hours

**Infrastructure:**

1. **Containerization:**
```dockerfile
FROM python:3.11-slim

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ /app/src/
COPY config.yaml /app/

WORKDIR /app

CMD ["python", "src/main.py"]
```

2. **Configuration management:**
   - Environment-specific configs
   - Secrets management (AWS Secrets Manager, HashiCorp Vault)
   - Feature flags for gradual rollout

3. **Monitoring & Logging:**
   - Structured logging (JSON format)
   - Metrics: processing time, error rate, confidence distribution
   - Alerting: failures, anomalies, budget overruns

4. **CI/CD Pipeline:**
```yaml
# .github/workflows/test.yml
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: |
          pip install -r requirements.txt
          pytest tests/

  quality:
    runs-on: ubuntu-latest
    steps:
      - name: Code quality
        run: |
          black --check src/
          pylint src/
```

**Acceptance Criteria:**
- ✅ Dockerized and deployable
- ✅ Automated tests with > 80% coverage
- ✅ Monitoring dashboard
- ✅ Deployment runbook documented

---

## Future Enhancements (Post-v1.0)

### Advanced Features (Months 2-3)

1. **Multi-document comparison:**
   - Compare revisions (v1.0 vs v1.1)
   - Generate changelogs automatically
   - Track terminology evolution

2. **Custom rule builder:**
   - UI for defining custom review rules
   - Regex pattern tester
   - A/B testing for new rules

3. **Domain-specific training:**
   - Fine-tune LLM on electronics datasheets
   - Build custom terminology database
   - Industry-specific style guides

4. **Batch processing:**
   - Queue multiple documents
   - Prioritization logic
   - Resource scheduling

5. **API for integration:**
   - REST API for document submission
   - Webhook notifications for completion
   - Embed in document management system

---

## Success Metrics

### v1.0 Release Goals:

| Metric | Current (MVP) | Target (v1.0) | Stretch |
|--------|---------------|---------------|---------|
| **Accuracy (Changes)** | ~85% | > 95% | > 98% |
| **Cross-ref Validation** | ~50% | > 85% | > 90% |
| **Processing Speed** | 6.7 pg/s | 8 pg/s | 10 pg/s |
| **Human Review Time** | N/A | < 20 hrs/doc | < 10 hrs/doc |
| **False Positive Rate** | ~15% | < 5% | < 2% |
| **User Satisfaction** | N/A | 4.0/5.0 | 4.5/5.0 |

### Business Impact:

- **Time Savings:** 85% reduction in review time
- **Cost Savings:** $15K/year in labor (assuming 10 docs/month)
- **Quality Improvement:** 30% more issues caught
- **Scalability:** 10x document volume with same resources

---

## Risk Assessment & Mitigation

### Technical Risks:

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| LLM API costs exceed budget | Medium | High | Token limits, caching, local fallback |
| False positives erode trust | High | High | **Fix immediately (Priority 1)** |
| PDF extraction fails on new layouts | Medium | Medium | Multiple extraction strategies, OCR |
| Performance degrades at scale | Low | Medium | Profiling, optimization, parallel processing |

### Business Risks:

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Users don't trust automated suggestions | Medium | High | Human-in-the-loop, transparency, learning |
| Competitors build similar tool | Low | Medium | Fast iteration, domain expertise |
| Regulatory concerns (data privacy) | Low | High | Secure deployment, audit trails |

---

## Resource Requirements

### Week 1-2 (Critical Fixes & Quality):
- 1 Senior Engineer: 40 hours
- 1 QA Engineer: 16 hours
- Total: **56 hours**

### Week 3-4 (LLM Integration):
- 1 Senior Engineer: 40 hours
- 1 ML Engineer: 24 hours
- Total: **64 hours**

### Week 5 (Human-in-the-Loop):
- 1 Full-stack Engineer: 40 hours
- 1 UX Designer: 8 hours
- Total: **48 hours**

### Week 6 (Production):
- 1 DevOps Engineer: 24 hours
- 1 Senior Engineer: 16 hours
- Total: **40 hours**

**Grand Total:** ~208 hours (~5.2 engineer-weeks)

---

## Timeline Summary

```
Week 1: ████████░░ Bug Fixes (Critical)
Week 2: ████████░░ Quality Improvements
Week 3: ██████░░░░ LLM Integration (Infrastructure)
Week 4: ██████░░░░ LLM Integration (Workflow)
Week 5: ████████░░ Human Review UI
Week 6: ██████░░░░ Production Deployment
```

**Key Milestones:**
- ✅ **End of Week 1:** No critical bugs, can demo confidently
- ✅ **End of Week 2:** Quality suitable for beta testing
- ✅ **End of Week 4:** LLM-powered review functional
- ✅ **End of Week 5:** Human oversight workflow complete
- ✅ **End of Week 6:** v1.0 deployed to production

---

## Conclusion

This roadmap prioritizes **trust and quality** (fixing bugs) before **capabilities** (adding LLM). By Week 6, we'll have a production-ready system that:

1. ✅ **Accurately** reviews technical documents (> 95% accuracy)
2. ✅ **Efficiently** processes at scale (< 5 min for 800 pages)
3. ✅ **Transparently** explains its decisions (human trust)
4. ✅ **Adaptively** learns from human feedback
5. ✅ **Securely** handles sensitive documents

**Next Action:** Get stakeholder approval, then start Week 1 fixes immediately!

---

**Roadmap Version:** 1.0
**Last Updated:** 2025-10-03
**Status:** Approved for execution ✅
