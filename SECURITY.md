# Security

Please do not report security vulnerabilities through public issues.

If you discover a vulnerability, leaked credential, exposed taxpayer data, or a way to bypass the RAG safety rules, report it privately through GitHub Security Advisories if available, or contact the maintainers directly.

## What to include

- A short description of the issue
- Steps to reproduce, if safe to share
- Affected files, endpoints, or services
- Any logs or screenshots with secrets and taxpayer facts removed

## Sensitive data

Never include the following in issues, pull requests, commits, screenshots, logs, or test fixtures:

- API keys, OC codes, tokens, or credentials
- `.env` contents
- Pinecone index credentials or namespace secrets
- Private taxpayer facts, case materials, or personally identifiable information
- Retrieved legal chunks from private or restricted sources

## Security-sensitive behavior

The following are treated as security or safety issues in this project:

- Bypassing retrieval for tax-law conclusions
- Citing laws without real retrieved `chunk_id` values
- Skipping output validation or phantom citation checks
- Disabling L1.5 confirmation gates
- Exposing internal traces that contain secrets or taxpayer facts

Thank you for helping keep the project safe and auditable.
