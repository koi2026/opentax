## Summary

What changed?

## Verification

- [ ] Ran focused tests for the changed area
- [ ] Ran `pytest` or explained why not

## RAG Safety

- [ ] No retrieval bypass for tax-law conclusions
- [ ] No citations without real retrieved `chunk_id` values
- [ ] No hardcoded tax rates, thresholds, periods, or limits
- [ ] No secrets, `.env` values, or private taxpayer facts included

## AI Assistance

Was this PR largely written with AI assistance?

- [ ] No
- [ ] Yes: tool/model used:
