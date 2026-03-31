# Technology Stack - AI Washing Detector

**Project:** AI Washing Detector (Python-based hedge fund portfolio analysis tool)
**Researched:** 2026-03-31
**Confidence:** HIGH (Python/NLP ecosystem well-established; financial data access validated)

---

## Recommended Stack

### Core Language & Runtime

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Python** | 3.11+ | Primary development language | Industry standard for quant finance; rich NLP/ML ecosystem; fast enough for batch processing |
| **pip** | Latest | Dependency management | Standard; integrated with Python; vast package ecosystem |
| **Docker** | Latest | Containerization | Reproducible deployments; easy CI/CD; runs identically on dev/prod |

**Alternatives considered:**
- Rust: Faster, but development velocity 3-4x slower; overkill for daily batch processing (not real-time trading)
- Node.js: Not suitable for NLP/ML workloads; ecosystem less mature for financial data
- **Decision:** Python because development speed dominates; daily batch processing doesn't justify optimization burden

---

### NLP & ML Stack

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| **transformers** | 4.36+ | Pretrained models (FinBERT, BERT) | Industry standard; huggingface ecosystem; production-ready |
| **torch/tensorflow** | 2.13+ | Deep learning backend | Required by transformers; PyTorch preferred for flexibility |
| **spacy** | 3.7+ | Linguistic features, NER | Fast, accurate tokenization/NER; good for rule-based extraction |
| **textblob** | 0.17+ | Sentiment analysis fallback | Lightweight; good for quick sentiment scores |
| **nltk** | 3.8+ | Linguistic utilities | Mature; good for sentence splitting, POS tagging |
| **scikit-learn** | 1.3+ | ML (classification, ensemble) | Standard for logistic regression, gradient boosting, feature scaling |
| **pandas** | 2.0+ | Data manipulation | Essential for financial data; time-series handling |
| **numpy** | 1.24+ | Numerical computing | Dependency for pandas, sklearn, torch |

**Rationale:**
- **FinBERT** is pretrained on financial text (10-K, earnings calls); no training data needed
- **sklearn** used for ensemble voting/weighting of signals
- **spacy** for efficient text processing (tokenization, NER extraction of company names, tickers)
- Avoid GPT-based models (ChatGPT, Claude) due to cost per query ($0.0015+ per call × 500 companies × daily = $225+/day)

---

### Data Pipeline & Orchestration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Prefect** | 2.14+ | Workflow orchestration | Lighter than Airflow; native Python; better for data science workflows |
| **PostgreSQL** | 15+ | Primary database | Mature, ACID-compliant; perfect for structured financial data |
| **TimescaleDB** | 2.12+ (extension) | Time-series optimization | Built on Postgres; optimized for time-series (signals over time) |
| **Redis** | 7.2+ | Caching & session store | Fast in-memory cache for API responses, rate-limit tracking |
| **requests** | 2.31+ | HTTP client library | For SEC Edgar API, GitHub API, patent databases |

**Rationale:**
- **Prefect** over Airflow: Simpler Python code (no DAG XML), better error handling, ideal for ~10 daily tasks
- **PostgreSQL+TimescaleDB** over NoSQL: Financial data is relational; Postgres better for time-series analytics than MongoDB
- **Redis** for caching API responses (SEC filings, patent queries) to avoid rate limits

**Alternatives considered:**
- Apache Airflow: Overkill for this scale (~10 daily tasks); more operational burden
- ClickHouse: Purpose-built for analytics, but overkill; Postgres sufficient for 500 companies
- Snowflake: Expensive ($2-4k/month); Postgres meets needs at $500/month

---

### API Framework & Web Stack

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **FastAPI** | 0.104+ | REST API backend | Modern, fast (near async-Go speeds); automatic OpenAPI docs; great for async I/O |
| **pydantic** | 2.5+ | Data validation | Built into FastAPI; ensures clean API contracts |
| **uvicorn** | 0.24+ | ASGI application server | High-performance async Python server |
| **Streamlit** (MVP) | 1.28+ | Dashboard/visualization | Rapid prototyping; no frontend engineering needed |
| **React** (production) | 18+ | Frontend (production upgrade) | Professional dashboard; interactive filtering |

**Rationale:**
- **FastAPI** for portfolio analysis APIs (enables hedge fund platform integration)
- **Streamlit** for MVP dashboard (analyst view of scores, signals, alerts)
- Later upgrade to React for more sophisticated analytics UI

---

### Data Access APIs & Libraries

| Library | Purpose | Why |
|---------|---------|-----|
| **sec-edgar** (PyPI) | SEC Edgar data access | Mature Python wrapper; handles CIK lookup, filing parsing |
| **PyGithub** (PyPI) | GitHub API client | Official Python library; rate-limited but reliable |
| **google-patents-client** or custom USPTO API | Patent search | Open-source patent query |
| **requests** + **BeautifulSoup4** | Web scraping (Seeking Alpha transcripts) | Lightweight; fine for daily batch scraping |
| **pdfplumber** | PDF text extraction (investor relations PDFs) | Accurate table/text extraction from PDFs |
| **yfinance** (PyPI) | Stock price data | Free fallback for baseline stock metrics |

**Cost breakdown:**
- All free libraries (no licensing cost)
- Earnings transcripts: Seeking Alpha free, or $200-500/month paid API if needed

---

### Testing & Quality Assurance

| Technology | Purpose | Why |
|------------|---------|-----|
| **pytest** | Unit testing | Standard Python testing framework |
| **pytest-cov** | Code coverage | Ensure critical paths tested |
| **mypy** | Static type checking | Catch type errors before runtime |
| **black** | Code formatting | Enforces consistent style |
| **ruff** | Linting | Fast linter; catches common errors |

**Rationale:**
- Financial data processing requires high reliability; automated testing is essential
- Type hints critical for multi-engineer team
- Code formatting/linting prevents technical debt

---

### Infrastructure & DevOps

| Technology | Purpose | Why |
|------------|---------|---------|
| **AWS EC2** | Compute (batch jobs) | Cost-effective for daily batch; spin down when not running |
| **AWS RDS** (PostgreSQL) | Managed database | Automated backups, failover, easy scaling |
| **AWS S3** | Data storage (archives) | Store 10-K PDFs, transcripts for audit trail |
| **AWS CloudWatch** | Monitoring & logging | Integrated with other AWS services |
| **GitHub Actions** | CI/CD pipeline | Free for public repos; works with private repos |
| **Docker Compose** (dev) or **Kubernetes** (prod) | Container orchestration | Docker for local dev; K8s if multi-instance needed |

**Cost estimate (AWS):**
- EC2 (batch, 1 hour/day): ~$30-50/month
- RDS (db.t3.micro): ~$30/month
- S3 (1TB storage): ~$20/month
- CloudWatch: ~$10-20/month
- **Total infrastructure: ~$100-150/month** (development); scales to $500-1000/month in production

**Alternatives:**
- GCP (similar cost; slightly different tooling)
- Self-hosted (lower cloud cost, higher operational burden)

---

### Monitoring, Logging, Alerting

| Technology | Purpose | Why |
|------------|---------|-----|
| **Python logging** (stdlib) | Application logging | Built-in; writes to CloudWatch |
| **Prometheus** | Metrics collection (optional) | Industry standard; scrapes application metrics |
| **Grafana** | Visualization (optional) | Dashboards for operational monitoring |
| **PagerDuty** | Alert routing (optional) | Notify on-call analyst if pipeline fails |

**MVP approach:** Use CloudWatch logging + email alerts; add Prometheus/Grafana in Phase 2 if needed.

---

## Installation & Setup

### Development Environment

```bash
# Clone repository
git clone https://github.com/your-org/ai-washing-detector.git
cd ai-washing-detector

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install

# Run tests
pytest tests/

# Run type checking
mypy src/

# Format code
black src/ tests/
ruff check src/ tests/
```

### Core Dependencies (requirements.txt)

```txt
# NLP & ML
transformers==4.36.2
torch==2.1.2
spacy==3.7.2
textblob==0.17.1
nltk==3.8.1
scikit-learn==1.3.2
pandas==2.1.4
numpy==1.26.3

# Data access
sec-edgar==0.3.5
PyGithub==2.1.1
requests==2.31.0
beautifulsoup4==4.12.2
pdfplumber==0.10.3
yfinance==0.2.32

# Pipeline & orchestration
prefect==2.14.6
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
redis==5.0.1

# API & web
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.3
streamlit==1.28.1

# Quality & testing
pytest==7.4.3
pytest-cov==4.1.0
mypy==1.7.1
black==23.12.0
ruff==0.1.11
pre-commit==3.5.0
```

### Development Dependencies (requirements-dev.txt)

```txt
# Testing
pytest-asyncio==0.21.1
pytest-mock==3.12.0

# Code quality
pylint==3.0.3
flake8==6.1.0
isort==5.13.2

# Documentation
sphinx==7.2.6
sphinx-rtd-theme==2.0.0

# Debugging
ipython==8.17.2
jupyter==1.0.0
```

### Docker Setup

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ src/
COPY config/ config/

# Run application
CMD ["python", "-m", "src.main"]
```

**docker-compose.yml (development):**
```yaml
version: '3.8'

services:
  postgres:
    image: timescaledb/timescaledb:latest-pg15
    environment:
      POSTGRES_USER: detector_user
      POSTGRES_PASSWORD: detector_password
      POSTGRES_DB: ai_washing_detector
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    build: .
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql://detector_user:detector_password@postgres:5432/ai_washing_detector
      REDIS_URL: redis://redis:6379/0
      SEC_API_KEY: ${SEC_API_KEY}
      GITHUB_TOKEN: ${GITHUB_TOKEN}
    volumes:
      - ./src:/app/src
      - ./config:/app/config
    ports:
      - "8000:8000"

volumes:
  postgres_data:
```

---

## Configuration Management

### Environment Variables

Create `.env.example`:
```bash
# API Keys (required for data access)
SEC_API_KEY=                    # SEC Edgar API key (optional, increases rate limit)
GITHUB_TOKEN=your_github_token  # Required for GitHub API
SEEKING_ALPHA_KEY=              # If using paid transcript API

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/ai_washing_detector
REDIS_URL=redis://localhost:6379/0

# Prefect configuration
PREFECT_API_URL=https://api.prefect.cloud/api/accounts/...
PREFECT_API_KEY=...

# Portfolio configuration
TARGET_TICKERS=AAPL,MSFT,NVDA,META,TSLA,CRM,...  # Comma-separated list
DATA_FRESHNESS_DAYS=7  # Recompute scores every N days

# Monitoring
ALERT_EMAIL=portfolio-manager@hedgefund.com
ALERT_THRESHOLD=35  # Alert on scores < 35 (HIGH washing risk)
```

---

## Deployment Checklist

### Pre-Production

- [ ] All tests passing (`pytest -v`)
- [ ] Type checking clean (`mypy src/`)
- [ ] Code formatted (`black . && ruff check .`)
- [ ] Environment variables configured
- [ ] Database migrations run
- [ ] API documentation generated
- [ ] Monitoring/alerting configured

### Production Deployment (AWS)

```bash
# Build Docker image
docker build -t ai-washing-detector:latest .
docker tag ai-washing-detector:latest \
  {aws_account_id}.dkr.ecr.{region}.amazonaws.com/ai-washing-detector:latest

# Push to ECR
aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin \
  {aws_account_id}.dkr.ecr.{region}.amazonaws.com
docker push {aws_account_id}.dkr.ecr.{region}.amazonaws.com/ai-washing-detector:latest

# Deploy to ECS/EKS (or EC2 with docker-compose)
# ... deployment orchestration script ...
```

---

## Technology Decision Rationale

### Why Python Over Alternatives

| Factor | Python | Rust | Java | Node.js |
|--------|--------|------|------|---------|
| **NLP ecosystem** | Excellent | Good | Good | Limited |
| **ML/data science** | Dominant | Growing | Mature | Weak |
| **Quant finance community** | Huge | Small | Established | Small |
| **Development speed** | 3-5x faster | Slower | Slower | Not suitable |
| **Execution speed** | ~1000 ops/sec | ~100k ops/sec | ~50k ops/sec | ~10k ops/sec |
| **Daily batch feasible?** | Yes (10 sec) | Yes (<1 sec) | Yes (5 sec) | No (not suitable) |

**Decision:** Python wins on development velocity + ecosystem richness. Daily batch processing doesn't require Rust-level speed.

### Why Prefect Over Airflow

| Factor | Prefect | Airflow |
|--------|---------|---------|
| **Setup complexity** | 15 min | 1-2 hours |
| **Python-first design** | Yes | No (XML DAGs) |
| **Async support** | Native | Basic |
| **Small task scale** | Optimal | Overkill |
| **Large enterprise** | Growing | Better |

**Decision:** Prefect for MVP (simpler setup). Can migrate to Airflow if task complexity grows 5-10x.

### Why FinBERT Over ChatGPT

| Factor | FinBERT | ChatGPT |
|--------|---------|---------|
| **Cost per call** | $0 (local) | $0.0015 |
| **Daily cost (500 cos)** | $0 | $225+ |
| **Latency** | 100ms | 500ms+ |
| **Requires internet** | No | Yes |
| **Fine-tuning needed** | No (pretrained) | Yes (expensive) |
| **Task suitability** | Optimal (financial) | Overkill (classification) |

**Decision:** FinBERT + local inference. GPT models better for exploratory analysis; FinBERT better for production scoring.

---

## Sources & References

- Transformers library: https://huggingface.co/docs/transformers
- FinBERT paper: https://arxiv.org/abs/1908.08033
- SEC Edgar API: https://data.sec.gov
- GitHub API: https://docs.github.com/en/rest
- Prefect documentation: https://docs.prefect.io
- FastAPI: https://fastapi.tiangolo.com
