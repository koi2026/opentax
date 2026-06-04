<p align="center">
  <img src=".github/images/logo.svg" width="400" alt="OpenTax Logo">
</p>

<div align="center">
  <h3>A statute-grounded RAG multi-agent AI for Korean capital gains tax exemption, reduction, and surtax decisions.</h3>
</div>

<div align="center">
  <a href="https://github.com/Raw-Agent/opentax/actions/workflows/ci.yml" target="_blank"><img src="https://github.com/Raw-Agent/opentax/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Raw-Agent/opentax/releases/latest" target="_blank"><img src="https://img.shields.io/github/v/release/Raw-Agent/opentax?label=Release" alt="Release"></a>
  <a href="https://polyformproject.org/licenses/noncommercial/1.0.0" target="_blank"><img src="https://img.shields.io/badge/License-PolyForm%20Noncommercial-red" alt="PyPI - License"></a>
  <a href="README.md"><img src="https://img.shields.io/badge/README-Korean-blue" alt="README in Korean"></a>
</div>

## Quick Start

Docker Compose is the recommended way to run OpenTax locally.

```bash
git clone https://github.com/Raw-Agent/opentax.git
cd opentax
cp .env.example .env

# Fill .env with API keys and Pinecone settings.
# The fine-tuned BGE reranker model is not stored in Git.
# Download it separately and place it under data/models/bge-reranker-tax-rag/.

docker compose up --build
```

Services run on the following default ports.

| Service | URL |
|------|------|
| FastAPI | `http://localhost:8000` |
| MCP search server | `http://localhost:8001` |
| Streamlit UI | `http://localhost:8501` |

Use Docker for status checks and tests.

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose exec api pytest
```

To run directly in a local Python environment, start each service in a separate terminal.

```bash
pip install -r requirements.txt
python -m src.mcp.server --sse
uvicorn src.api.main:app
streamlit run src/ui/app.py
```

Example required environment variables:

```env
ANTHROPIC_API_KEY=
UPSTAGE_API_KEY=
OPENAI_API_KEY=
PINECONE_API_KEY=
PINECONE_INDEX_NAME=tax-rag
PINECONE_NAMESPACE=tax-law
BGE_RERANKER_MODEL=data/models/bge-reranker-tax-rag
```

## How It Works

OpenTax does not send user facts directly to an LLM. It first passes the case through confirmation and fact-checking gates, then reasons only from retrieved statute and ruling chunks.

```text
JSON fact_json or natural-language question
    ↓
L1.5 Confirmation Gate
    - household-wide home count
    - earlier of balance payment date and registration filing date
    - related-party transaction status
    - actual residence period
    - acquisition document availability
    ↓
L2 Fact Check
    - blocks LLM calls when critical facts are missing
    ↓
L3 Query Enrichment
    - injects tax-law risk flags and article keywords
    ↓
L4 Retrieval + Reasoning
    - Pinecone date filter
    - multi-source statute/ruling search
    - BGE reranking
    - Claude reasoning grounded in cited chunks
    ↓
L5 Output Validation
    - blocks phantom citations
    - adjusts confidence ceilings
    ↓
TaxAnswer
    - verdict
    - citations
    - chunk_ids
    - missing_facts
    - warnings
    - expert_review_signals
```

The verdict is one of `비과세` (exempt), `감면` (reduced), `중과` (heavy tax), `일반과세` (general taxation), `단기세율` (short-term rate), `고가주택` (high-value home), or `사실관계부족` (insufficient facts).

Core rules:

| Rule | Meaning |
|------|------|
| No RAG bypass | The system does not answer from LLM memory without retrieved legal text. |
| No phantom citations | Only retrieved chunks with real `chunk_id` values can be cited. |
| Defer when facts are missing | Missing or uncertain facts are returned as `missing_facts` instead of forcing a conclusion. |

## System Architecture

```text
+--------------------+
| Streamlit UI       |
| fact/question input|
+---------+----------+
          |
          v
+--------------------+       +--------------------+
| FastAPI Chat API   | ----> | MCP Search Server  |
| request/streaming  |       | retrieve context   |
+---------+----------+       +---------+----------+
          |                            |
          v                            v
+--------------------+       +--------------------+
| Domain Pipeline    | <---- | Retrieval Layer    |
| L1.5 ~ L5          |       | Pinecone + BGE     |
+---------+----------+       +--------------------+
          |
          v
+--------------------+       +--------------------+
| Claude Reasoning   | ----> | TaxAnswer          |
| cited chunks only  |       | verdict/citations  |
+--------------------+       +--------------------+
```

## Tech Stack

| Area | Technology |
|------|------|
| Language | Python |
| API | FastAPI, Uvicorn |
| UI | Streamlit |
| MCP | FastMCP |
| LLM | Claude Sonnet 4.6, Claude Opus 4.7 |
| Embeddings | Upstage Solar `solar-embedding-1-large-passage`, OpenAI fallback |
| Vector DB | Pinecone Serverless |
| Reranker | BGE CrossEncoder, fine-tuned for Korean tax law |
| Ingestion | law.go.kr DRF API, taxlaw.nts.go.kr, PDF parser |
| Evaluation | pytest, Red-Blue debate, golden set |

---

## Directory Structure

```text
src/
├── api/                    # FastAPI app, chat routes, request/response schema
├── application/            # API service orchestration and serializers
├── domain/                 # L1.5~L5 pipeline, dataclasses, tax rules
├── retrieval/              # Pinecone retriever, MCP retriever, LLM call wrapper
├── infra/                  # Embedding, Pinecone client, reranker adapter
├── ingestion/              # Statute, ruling, and PDF collection/embedding
├── calculator/             # Deterministic tax calculation
├── mcp/                    # FastMCP search tools
├── eval/                   # Debate, golden set, retrieval evaluation
├── services/               # Service-layer routing
├── agents/                 # Prompt registry
└── ui/                     # Streamlit UI and admin pages

data/
├── golden/                 # Evaluation QA/golden cases
├── rulings/                # Collected ruling source data
├── area_designations/      # Manual regulatory-area tables and source status
├── tax_tables/             # Rate tables and deterministic tax constants
└── models/                 # BGE model location, excluded from Git

scripts/
├── eval/                   # Baseline eval and golden refresh
├── ingestion/              # Operational collection/embedding scripts
├── ops/                    # Law-change detection and registry automation
└── training/               # Reranker pair extraction and fine-tuning

tests/                      # Unit and regression tests
```

## Contributing

For contribution guidelines, development setup, testing, and the PR workflow, see [CONTRIBUTING.md](CONTRIBUTING.md).

Domain contracts and AI-assisted PR rules are also documented in [AGENTS.md](AGENTS.md), [DEVELOPERS.md](DEVELOPERS.md), and [CLAUDE.md](CLAUDE.md).

## License

This project is distributed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0).

Commercial use, service provision, resale, and SaaS use are not permitted without separate permission.

## Legal Notice

OpenTax is provided for informational, research, and development purposes. Its outputs are not legal advice, tax representation, or a professional tax filing review.

For Korean capital gains tax filing, payment, appeals, tax audit response, or documents submitted to tax authorities, final decisions must be reviewed with a certified tax accountant, attorney, or relevant authority. The developers and contributors of OpenTax are not responsible for tax differences, penalties, filing errors, or administrative disadvantages resulting from use of this system.
