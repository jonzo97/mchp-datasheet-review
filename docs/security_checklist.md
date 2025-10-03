# Security & Privacy Checklist

**Version:** 0.2.0
**Date:** 2025-10-03
**Purpose:** Security assessment and recommendations for safe deployment

---

## 🔒 Executive Summary

### Is This Tool Safe to Share?

**✅ YES** - The tool is safe to share with your colleague, with the following considerations:

- ✅ **Local Processing**: All document processing happens locally (no cloud services by default)
- ✅ **No Telemetry**: No phone-home, no data collection, no tracking
- ✅ **Transparent**: Open-source, inspectable code
- ⚠️ **PDF Metadata Warning**: Input PDFs may contain sensitive metadata (see recommendations below)
- ⚠️ **API Configuration Required**: When integrating with internal LLM API, security configuration is essential
- ⚠️ **Database Plain Text**: SQLite database stores content in plain text (encryption optional)

**Recommendation**: Share the tool with included warnings about PDF sanitization and API security configuration.

---

## 🔍 Current Security State Assessment

### ✅ Security Strengths

| Feature | Status | Notes |
|---------|--------|-------|
| **Local Processing** | ✅ Secure | No data leaves your machine by default |
| **No Cloud Dependencies** | ✅ Secure | Works entirely offline (except optional LLM API) |
| **No Telemetry** | ✅ Secure | Zero tracking or phone-home behavior |
| **Open Source** | ✅ Transparent | All code is inspectable |
| **SQLite Single-File DB** | ✅ Portable | Easy to backup, inspect, and control |
| **No Auto-Transmission** | ✅ Secure | User explicitly controls API integration |
| **Modular Architecture** | ✅ Auditable | Clear separation of concerns |

### ⚠️ Security Considerations

| Area | Risk Level | Notes |
|------|------------|-------|
| **PDF Metadata** | ⚠️ Medium | Input PDFs may contain sensitive metadata |
| **LLM API Integration** | ⚠️ High | Requires careful configuration (zero-retention, TLS, etc.) |
| **Database Encryption** | ⚠️ Low-Medium | SQLite stores data in plain text (encryption optional) |
| **Logging** | ⚠️ Medium | If LLM API logs prompts/responses, potential leakage |
| **ChromaDB (Future)** | ⚠️ Medium | Multi-tenant isolation required |

---

## 📄 PDF Security Risks

### The Hidden Data Problem

**Critical Finding**: Research analysis of 39,664 PDFs from 75 security agencies found:
- **Only 7 agencies** properly sanitized their PDFs before publishing
- **65% of "sanitized" PDFs** still contained sensitive information
- **76% leaked producer tool info**, 42% revealed OS, 4% included author names

### 11 Types of Hidden Data in PDFs (per NSA)

1. **Metadata** - Author, organization, creation date, software used
2. **Embedded Content** - Attached files, linked documents
3. **Scripts** - JavaScript or other executable code
4. **Hidden Layers** - Content on invisible layers
5. **Embedded Search Index** - Full-text search metadata
6. **Interactive Form Data** - Stored form submissions
7. **Comments & Annotations** - Review comments, markup
8. **Hidden Page Data** - Content outside visible area
9. **Obscured Text/Images** - Covered but not removed content
10. **PDF Comments** - Non-displayed metadata comments
11. **Unreferenced Data** - Old versions, deleted content still in file

### Our Tool's Current Behavior

**⚠️ No Sanitization**: The tool currently processes PDFs as-is without stripping metadata.

**Risks:**
- If you process a sensitive datasheet, the original PDF metadata remains embedded
- Output markdown contains extracted text but source PDF metadata is not modified
- SQLite database may store metadata extracted during processing

**Mitigations (Manual):**
- Use Adobe Acrobat Pro: Tools → Redact → Remove Hidden Information
- Use PDF sanitization tools before processing: `pdf-redact-tools`, `qpdf`, or `pdfsanitize`
- Check metadata: `pdfinfo filename.pdf` or `exiftool filename.pdf`

---

## 🔐 LLM API Security Requirements

### Critical Security Checklist

When integrating with your internal LLM API, **you MUST verify**:

#### 1. Zero-Retention Policy ✅
- [ ] API provider does **NOT** log prompts
- [ ] API provider does **NOT** log responses
- [ ] API provider does **NOT** use your data for training
- [ ] Written guarantee of zero data retention

**Why Critical**: Logging prompts = your sensitive datasheet content stored on provider's servers

#### 2. Encryption & Compliance ✅
- [ ] **TLS 1.2+** required for all API calls
- [ ] **SOC 2 Type II** certification (or equivalent)
- [ ] **GDPR/HIPAA** compliance if handling regulated data
- [ ] **ISO 27001** certification (bonus)

#### 3. Authentication & Authorization ✅
- [ ] Strong authentication (API keys, OAuth 2.0, or mTLS)
- [ ] Token rotation policy
- [ ] Rate limiting to prevent abuse
- [ ] Access logging and monitoring

#### 4. Data Minimization ✅
- [ ] Only send **necessary chunks** to API (not entire documents)
- [ ] Strip sensitive metadata before API calls
- [ ] Implement content filtering for PII/sensitive terms
- [ ] Use rule-based triage to minimize API calls (already implemented ✅)

#### 5. Output Filtering ✅
- [ ] Scan API responses for leaked sensitive information
- [ ] Validate API output format (prevent injection attacks)
- [ ] Log anomalies (unexpected response patterns)

### Our Implementation (`smart_queue.py`)

**✅ Built-In Security Features:**
- **Data Minimization**: Only sends chunks that fail rule-based validation (not entire document)
- **Intelligent Triage**: Auto-approves high-confidence chunks (>0.95), reducing API surface
- **Batch Processing**: Reduces API call overhead
- **Fallback**: If API fails, falls back to rule-based results (no data lost)

**⚠️ Required Configuration:**
```python
# In smart_queue.py, you MUST implement:
class InternalAPIClient:
    def __init__(self, endpoint: str, auth_token: str):
        self.endpoint = endpoint  # Verify TLS endpoint
        self.auth_token = auth_token  # Secure token management

        # TODO: Add your security measures:
        # - Certificate pinning
        # - Request timeout
        # - Content filtering
        # - Output validation
```

### OWASP Top 10 for LLM Applications

Follow the **OWASP Top 10 for LLM Applications** framework:
1. Prompt Injection
2. Insecure Output Handling
3. Training Data Poisoning
4. Model Denial of Service
5. Supply Chain Vulnerabilities
6. Sensitive Information Disclosure ⚠️ **Most relevant**
7. Insecure Plugin Design
8. Excessive Agency
9. Overreliance
10. Model Theft

**Most Critical for Document Review**: #6 Sensitive Information Disclosure

---

## 🗄️ Database Security

### Current State: SQLite (Plain Text)

**Storage Location**: `review_state.db` in project root

**Contents:**
- Document metadata (filename, page count, etc.)
- Extracted chunks (full text content)
- Review results (original + corrected text)
- Changes and confidence scores
- Cross-reference validation results

**Risk**: Anyone with file system access can read the database.

### Encryption Options

#### Option 1: SQLCipher (Recommended)
```bash
# Install SQLCipher
pip install pysqlcipher3

# Modify database.py to use encryption
PRAGMA key = 'your-encryption-key';
```

**Pros:**
- Transparent encryption at rest
- AES-256 encryption
- Minimal code changes

**Cons:**
- Requires additional dependency
- Key management responsibility

#### Option 2: File System Encryption
- Use LUKS (Linux), FileVault (Mac), or BitLocker (Windows)
- Encrypts entire disk/partition
- No code changes needed

#### Option 3: Encrypted Container
- Use VeraCrypt or similar
- Store database in encrypted volume
- Mount/unmount as needed

### Database Access Controls

**File Permissions** (Linux/Mac):
```bash
chmod 600 review_state.db  # Owner read/write only
```

**Recommendations:**
- Store database in user-only directory
- Implement access logging
- Regular backups to secure location
- Consider encryption at rest for sensitive documents

---

## 🧩 ChromaDB Security (Future Feature)

### Multi-Tenancy Risks

**Problem**: Naive metadata filtering can leak data across users/documents.

**Bad Example** (Leaky):
```python
# DON'T DO THIS - Metadata filtering is error-prone
collection.query(
    query="sensitive text",
    where={"user_id": "alice"}  # Bug: Filter can be bypassed
)
```

**Good Example** (Isolated):
```python
# DO THIS - User-per-database isolation
alice_db = client.create_database("alice_db")
alice_collection = alice_db.create_collection("docs")
# Physically separate databases = no leakage risk
```

### Our Implementation Plan

**✅ Security-First Approach:**
1. **User-Per-Database Isolation**: Each user/project gets separate ChromaDB database
2. **No Shared Collections**: Never mix sensitive documents in same collection
3. **Authentication Required**: Multi-user basic auth or OpenFGA
4. **Access Logging**: Track all queries and access patterns

### ChromaDB Configuration

```yaml
# Secure ChromaDB settings
chromadb:
  # Multi-tenancy
  isolation_mode: "user-per-database"  # Strongest isolation

  # Authentication
  auth_provider: "basic"  # or "openidconnect" for enterprise

  # Network
  allow_reset: false  # Prevent database wipes
  cors_allow_origins: []  # No cross-origin requests
```

---

## 🛡️ Safe Sharing Guidelines

### Sharing Tool with Colleague: Checklist

#### ✅ What to Share
- [ ] Complete codebase (all `src/` files)
- [ ] Documentation (`docs/` directory)
- [ ] Configuration template (`config.yaml`)
- [ ] Requirements (`requirements.txt`)
- [ ] This security checklist ✅
- [ ] Setup instructions (README.md)

#### ⚠️ What NOT to Share
- [ ] ❌ **Actual SQLite databases** (may contain processed documents)
- [ ] ❌ **API keys or tokens** (if you've added any)
- [ ] ❌ **Processed PDFs or output files** (if they contain sensitive data)
- [ ] ❌ **Logs** (may contain sensitive information)

#### 📋 Information to Include

**1. Security Warnings:**
```markdown
⚠️ SECURITY NOTICE:
- This tool processes documents LOCALLY (no cloud by default)
- PDF files may contain hidden metadata - sanitize before processing sensitive documents
- If integrating with LLM API, ensure zero-retention policy and TLS encryption
- SQLite database stores data in plain text - consider encryption for sensitive use
```

**2. Setup Instructions:**
- Python environment setup
- Dependencies installation
- Configuration template
- Testing with public/non-sensitive documents first

**3. API Integration Guide:**
- Security requirements checklist (see above)
- Example secure implementation
- Testing procedures

#### 🔒 Pre-Sharing Cleanup

Before sharing the project directory:
```bash
# Remove any generated outputs
rm -rf output/*

# Remove any databases
rm -f *.db

# Remove any sensitive test files
rm -rf test_data/*

# Check for API keys in config
grep -r "api" config.yaml

# Check git history (if using git)
git log --all --full-history --source -- config.yaml
```

---

## 🎯 Security Best Practices

### For Development

1. **Never Commit Secrets**
   - Use environment variables for API keys
   - Add `.env` to `.gitignore`
   - Use `python-dotenv` for local config

2. **Validate All Inputs**
   - Check file paths (prevent directory traversal)
   - Validate PDF files (prevent malicious PDFs)
   - Sanitize user inputs

3. **Principle of Least Privilege**
   - Run tool with minimal permissions
   - Don't run as root/administrator
   - Limit file system access

4. **Regular Updates**
   - Keep dependencies updated (`pip list --outdated`)
   - Monitor security advisories
   - Update Python version

### For Production Deployment

1. **API Security Hardening**
   ```python
   # In smart_queue.py
   import os
   from dotenv import load_dotenv

   load_dotenv()

   api_client = InternalAPIClient(
       endpoint=os.getenv("LLM_API_ENDPOINT"),  # Not hardcoded
       auth_token=os.getenv("LLM_API_TOKEN"),   # From environment
       verify_ssl=True,                          # Always verify
       timeout=30                                # Prevent hanging
   )
   ```

2. **Monitoring & Logging**
   - Log all API calls (without logging content)
   - Monitor for anomalies
   - Alert on errors or unusual patterns

3. **Access Controls**
   - Implement RBAC (role-based access control)
   - Separate dev/test/prod environments
   - Audit trail for all processing

4. **Disaster Recovery**
   - Regular backups
   - Tested restore procedures
   - Incident response plan

---

## 📊 Security Metrics to Track

### Operational Security Metrics

| Metric | Target | How to Monitor |
|--------|--------|----------------|
| **API Call Encryption** | 100% TLS | Check API client logs |
| **Failed Auth Attempts** | <5 per day | API access logs |
| **Database Access** | Authorized only | File system audit logs |
| **PDF Sanitization Rate** | 100% sensitive docs | Manual tracking |
| **API Zero-Retention Compliance** | 100% | Vendor audits |

### Security Incidents to Track

- Unauthorized database access attempts
- API authentication failures
- Unexpected data patterns in LLM responses
- PDF processing errors (potential malicious PDFs)
- Unusual API usage patterns

---

## 🚨 Incident Response Plan

### If You Suspect a Security Breach:

1. **Immediate Actions**
   - Stop processing immediately
   - Disconnect from network if API-connected
   - Preserve logs and evidence

2. **Assessment**
   - Determine what data may have been exposed
   - Identify attack vector
   - Document timeline

3. **Containment**
   - Revoke API credentials
   - Change encryption keys
   - Isolate affected systems

4. **Recovery**
   - Restore from clean backup
   - Apply security patches
   - Update access controls

5. **Prevention**
   - Conduct root cause analysis
   - Implement additional controls
   - Update security checklist

---

## ✅ Pre-Deployment Security Checklist

### Before Using with Sensitive Documents:

- [ ] Review this entire security checklist
- [ ] Sanitize PDFs (remove metadata)
- [ ] Configure database encryption (if needed)
- [ ] Verify LLM API security (zero-retention, TLS, SOC 2)
- [ ] Implement API authentication
- [ ] Set up monitoring and logging
- [ ] Test with non-sensitive documents first
- [ ] Document security configuration
- [ ] Train users on security best practices
- [ ] Establish incident response procedures

### Before Sharing with Colleague:

- [ ] Clean up output directories
- [ ] Remove any databases with sensitive data
- [ ] Check for hardcoded API keys or secrets
- [ ] Include security warnings in README
- [ ] Provide this security checklist
- [ ] Document API security requirements
- [ ] Test setup on clean machine

---

## 📚 Security Resources

### Standards & Frameworks
- **OWASP Top 10 for LLM Applications**: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- **NIST Cybersecurity Framework**: https://www.nist.gov/cyberframework
- **NSA PDF Redaction Guide**: Guidelines for hidden data in PDFs

### Tools
- **PDF Sanitization**: Adobe Acrobat Pro, pdf-redact-tools, qpdf
- **Metadata Inspection**: `exiftool`, `pdfinfo`
- **Database Encryption**: SQLCipher, pysqlcipher3
- **Secret Management**: HashiCorp Vault, AWS Secrets Manager
- **Security Scanning**: Bandit (Python security linter), Safety (dependency checker)

### Best Practices
- **Data Minimization**: Only collect/process what's necessary
- **Encryption**: At rest, in transit, in use
- **Zero Trust**: Never trust, always verify
- **Defense in Depth**: Multiple layers of security

---

## 🎓 Security Training Recommendations

### For Development Team
1. Secure coding practices for Python
2. OWASP Top 10 training
3. LLM security fundamentals
4. Data privacy regulations (GDPR, HIPAA, etc.)

### For Users
1. PDF metadata awareness
2. API security basics
3. Data classification (what's sensitive?)
4. Incident reporting procedures

---

## ✅ Conclusion

### Summary: Is This Tool Secure?

**For Local Use**: ✅ **YES** - Very secure (no cloud, no telemetry, local processing)

**For API Integration**: ⚠️ **CONDITIONAL** - Secure if you:
- Verify LLM API has zero-retention policy
- Ensure TLS + SOC 2 compliance
- Implement proper authentication
- Follow all security best practices in this checklist

**For Sharing**: ✅ **YES** - Safe to share with warnings:
- Include this security checklist
- Warn about PDF metadata
- Document API security requirements
- Clean up sensitive outputs before sharing

### Risk Assessment

| Scenario | Risk Level | Mitigation |
|----------|------------|------------|
| **Processing public datasheets locally** | 🟢 Low | None needed |
| **Processing sensitive datasheets locally** | 🟡 Medium | Sanitize PDFs, encrypt database |
| **Integrating with internal LLM API** | 🟡 Medium-High | Verify zero-retention, TLS, SOC 2 |
| **Integrating with external LLM API** | 🔴 High | ❌ Not recommended for sensitive data |
| **Sharing tool with colleague** | 🟢 Low | Clean outputs, include warnings |

---

**Final Verdict**: ✅ **Safe to share with your colleague** - Just include this security checklist and relevant warnings.

---

**Version:** 0.2.0
**Last Updated:** 2025-10-03
**Status:** ✅ Ready for Safe Deployment
