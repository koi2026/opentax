# Contributing

Thank you for your interest in Korean Tax RAG. Any form of participation--using the project, asking questions, reporting issues, improving documentation, adding tests, or contributing code--is appreciated.

This project is a law-grounded RAG engine for Korean capital gains tax 판단. Accuracy, traceability, and auditability matter more than speed of change.

## Getting started

Start with:

- [README.md](README.md) for the project overview and quick start
- [AGENTS.md](AGENTS.md) for architecture, domain contracts, and AI-agent instructions
- [DEVELOPERS.md](DEVELOPERS.md) for current development notes and task context
- [CLAUDE.md](CLAUDE.md) for additional local workflow guidance

If you are new to the codebase, documentation fixes, tests, sample cases, and small pipeline guardrail improvements are good first contributions.

## Development setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- API keys for the services you plan to exercise:
  - law.go.kr DRF API
  - Anthropic Claude
  - Upstage Solar or OpenAI embeddings
  - Pinecone

### Setup

```bash
git clone https://github.com/Raw-Agent/korean-tax-rag.git
cd korean-tax-rag
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` locally. Never commit `.env` or API keys.

### Run with Docker

Docker Compose is the preferred local verification path.

```bash
docker compose up --build
```

Services start at:

- API: `http://localhost:8000`
- MCP search server: `http://localhost:8001`
- Streamlit UI: `http://localhost:8501`

Useful checks:

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 mcp
docker compose logs --tail=100 ui
```

### Run locally

Use separate terminals:

```bash
python -m src.mcp.server --sse
uvicorn src.api.main:app
streamlit run src/ui/app.py
```

### Data ingestion

Law and ruling ingestion depends on external services and credentials. Run only the pieces needed for your change.

```bash
python -m src.ingestion.collect
python -m src.ingestion.embed

python -m src.ingestion.collect_rulings_revision --tax transfer
python -m src.ingestion.collect_rulings_nts --tax 양도소득세
python -m src.ingestion.collect_rulings_decisions --type tax_tribunal --keyword 양도
python -m src.ingestion.collect_rulings_pdf

python -m src.ingestion.embed_rulings nts
python -m src.ingestion.embed_rulings decisions
python -m src.ingestion.embed_rulings pdf
```

## Test

Run the normal test suite before opening a PR:

```bash
pytest
```

Run integration tests only when the required external services and data are available:

```bash
pytest -m integration
```

For baseline evaluation:

```bash
python -m scripts.run_baseline_eval --workers 3
```

## Coding rules

- Use Python type hints for all public functions.
- Use dataclasses in `src/domain/` for domain models. Keep Pydantic in API schemas.
- Keep user-facing text in Korean. Use English for function names, variable names, and code comments.
- Manage prompts in `src/agents/prompts.py`. Do not add inline prompts.
- Do not add tax rates, thresholds, periods, or limits as hardcoded literals. Use `TaxConstantsRegistry` or `data/tax_tables/*.json`.
- Do not put 판단 logic in `src/ui/app.py` or UI helpers. The UI is for input, display, and feedback collection only.
- Preserve law hierarchy metadata: law / enforcement decree / enforcement rule, article, paragraph, item, subitem, supplementary provision, and attached table.

## RAG safety rules

These are non-negotiable:

- Do not answer tax-law questions from LLM memory.
- Do not bypass retrieval for legal conclusions.
- Do not cite articles unless they came from retrieved chunks with real `chunk_id` values.
- Do not skip BGE reranking before final article selection.
- Do not flatten legal hierarchy while chunking or indexing.
- If critical facts are missing, return `missing_facts` instead of forcing a conclusion.
- L1.5 confirmation failures must block the pipeline completely.

## PR workflow

Fork the repository on GitHub, then set up remotes:

```bash
git remote rename origin upstream
git remote add origin https://github.com/YOUR_USERNAME/korean-tax-rag.git
```

1. Create branch: `git checkout -b feature/your-feature`
2. Make changes
3. Run focused tests for the area you changed
4. Run `pytest`
5. Commit with a Korean message using `타입: 요약`
6. Push and create a PR

Commit examples:

```bash
git commit -m "feat: 확인서 차단 항목 추가"
git commit -m "fix: phantom citation 검증 강화"
git commit -m "docs: 기여 가이드 추가"
```

## AI-assisted pull requests

AI-assisted pull requests are welcome, provided that you:

- Note in the PR description if the changes were largely written by AI.
- Name the AI tool and model that produced them, such as Codex, Claude Code, Cursor, Gemini, or ChatGPT.
- Understand the changes and are ready to discuss any line.
- Write the PR description and reply to reviewers in your own voice.
- Read through the diff yourself before opening the PR.
- Run a review pass with your AI tool before submitting.
- Follow the project rules in [AGENTS.md](AGENTS.md), [DEVELOPERS.md](DEVELOPERS.md), and this file.

## How we collaborate

We collaborate through GitHub:

- Discussions: questions, ideas, and open-ended conversations
- Issues: bug reports, feature requests, and concrete improvements
- Pull Requests: code, tests, documentation, and data-pipeline changes

Pull requests are reviewed collaboratively and merged by maintainers.

## Security

Do not open a public issue for security vulnerabilities or leaked credentials. Use GitHub Security Advisories if available, or contact the maintainers privately.

Never include API keys, OC codes, Pinecone credentials, `.env` contents, private taxpayer facts, or confidential case materials in issues, pull requests, commits, test fixtures, screenshots, or logs.

## Community standards

All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
