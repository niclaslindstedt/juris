# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

**Please do not open public issues for security vulnerabilities.**

Instead, use [GitHub's private vulnerability reporting](https://github.com/niclaslindstedt/juris/security/advisories/new) to report security issues.

### What to expect

- **Acknowledgment** within 48 hours
- **Initial assessment** within 7 days
- **Fix and disclosure** coordinated with reporter

### Scope

Security-relevant areas of juris include:

- **HTTP requests** to government APIs and web sources (URL handling, SSRF)
- **PDF text extraction** via pymupdf (malicious PDF handling)
- **File path construction** from document IDs (path traversal)
- **HTML parsing** of scraped content (injection in stored output)

## Disclosure Policy

We follow responsible disclosure. Once a fix is available, we will:

1. Release a patched version
2. Publish a security advisory on GitHub
3. Credit the reporter (unless anonymity is requested)
