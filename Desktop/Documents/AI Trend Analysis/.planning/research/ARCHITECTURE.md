# Architecture Patterns - AI Washing Detector

**Domain:** Financial signal detection system (batch + streaming, daily updates)
**Researched:** 2026-03-31
**Scale:** 500 companies, daily batch processing, <30 minute SLA

---

## Recommended Architecture

### High-Level System Diagram

```
External Data Sources
├─ SEC Edgar (10-K, 10-Q, Form 4)
├─ GitHub API (org metrics)
├─ USPTO Patents (patent database)
├─ Seeking Alpha (earnings transcripts)
└─ Yahoo Finance (stock prices)
        ↓
    [Extraction Layer]
    ├─ SEC Edgar Fetcher
    ├─ GitHub Aggregator
    ├─ Patent Query Engine
    ├─ Transcript Scraper
    └─ Stock Data Ingester
        ↓
    [Data Pipeline - Prefect DAG]
    ├─ Task 1: Download & store raw documents
    ├─ Task 2: Parse text (NLP preprocessing)
    ├─ Task 3: Extract features (buzzwords, sentiment, metrics)
    ├─ Task 4: Normalize & aggregate signals
    └─ Task 5: Compute ensemble score
        ↓
    [Feature Store]
    PostgreSQL + TimescaleDB
    ├─ company_profiles (metadata)
    ├─ signals_daily (time-series of signal scores)
    ├─ credibility_scores (historical scores)
    └─ scoring_metadata (weights, confidence)
        ↓
    [Scoring Engine]
    ├─ Load signal vectors
    ├─ Apply ensemble weights
    ├─ Compute credibility score (0-100)
    ├─ Derive trade signal (SHORT/AVOID/NEUTRAL/LONG)
    └─ Generate alerts
        ↓
    [Output Layer]
    ├─ REST API (FastAPI)
    ├─ Dashboard (Streamlit)
    ├─ Alerts (Email, Slack, Webhook)
    └─ Data Export (CSV, JSON, Database)
        ↓
    [End Users]
    Portfolio Managers, Quantitative Researchers, Analysts
```

---

## Component Boundaries

### Component 1: Data Ingestion Layer

**Responsibility:** Fetch raw data from external APIs; handle rate limiting and retries.

**Communicates with:**
- SEC Edgar API (10-K, Form 4, XBRL)
- GitHub API (organization repos, commits)
- USPTO/Google Patents API
- Seeking Alpha (web scraping)
- Yahoo Finance API

**Implementation pattern:**
```python
class SecEdgarFetcher:
    """Idempotent fetcher with rate limiting and caching."""

    def __init__(self, cache: Redis):
        self.cache = cache
        self.rate_limiter = RateLimiter(calls_per_sec=10)

    def fetch_10k(self, cik: str, year: int) -> Filing:
        # Check cache first
        cached = self.cache.get(f"10k:{cik}:{year}")
        if cached:
            return cached

        # Rate-limited fetch
        with self.rate_limiter:
            filing = self._fetch_from_sec(cik, year)

        # Store in cache (24h TTL)
        self.cache.set(f"10k:{cik}:{year}", filing, ex=86400)
        return filing
```

**Error handling:**
- Rate limit (429): Exponential backoff, retry up to 5x
- Timeout: Retry with longer timeout
- API outage: Skip component, mark data stale, alert
- Invalid data: Log, skip, notify (don't fail whole pipeline)

**Data validation:**
- Check file size (10-K typically 1-50MB; >100MB = suspect)
- Verify parsing succeeds (XBRL, PDF text extraction)
- Validate data types (numbers are floats, dates are valid)

---

### Component 2: Text Processing & NLP Layer

**Responsibility:** Parse raw documents; extract features; apply NLP models.

**Communicates with:**
- Document Store (feature cache)
- NLP models (FinBERT, spaCy)
- Feature Store (write signal data)

**Implementation pattern:**
```python
class FinancialTextProcessor:
    """Extract features from SEC filings and transcripts."""

    def __init__(self):
        self.bert_model = load_finbert_model()
        self.nlp = spacy.load("en_core_web_sm")

    def extract_features(self, document: Document) -> FeatureVector:
        # Tokenization & cleaning
        text = self.clean_text(document.text)
        tokens = self.nlp(text)

        # Feature extraction
        features = {
            'ai_buzzword_density': self.count_ai_buzzwords(tokens),
            'vagueness_index': self.measure_vagueness(tokens),
            'passive_voice_ratio': self.measure_passive_voice(tokens),
            'sentiment_score': self.predict_sentiment(text),
            'topic_distribution': self.extract_topics(text),
        }

        return FeatureVector(**features)

    def count_ai_buzzwords(self, tokens) -> float:
        """Return 0-100 score: AI buzzword density."""
        ai_terms = {
            'ai', 'artificial intelligence', 'machine learning', 'ml',
            'neural', 'deep learning', 'algorithm', 'automation',
            'predictive', 'intelligent', 'optimization'
        }
        matches = sum(1 for token in tokens if token.text.lower() in ai_terms)
        return (matches / len(tokens)) * 100 if tokens else 0

    def measure_vagueness(self, tokens) -> float:
        """Return 0-100: frequency of indefinite language."""
        vague_terms = {'may', 'might', 'could', 'potentially', 'likely', 'possible'}
        matches = sum(1 for token in tokens if token.text.lower() in vague_terms)
        return (matches / len(tokens)) * 100 if tokens else 0
```

**Model choices:**
- FinBERT for sentiment (trained on financial text)
- spaCy for linguistic features (efficient, accurate)
- Custom regex for domain-specific terms (AI buzzwords)

**Caching strategy:**
- Cache document-level features (no-op if document unchanged)
- Invalidate if document hash changes
- Keep 90-day rolling cache (storage: ~10GB for 500 companies)

---

### Component 3: Signal Aggregation

**Responsibility:** Combine raw features into normalized signals (0-100 scale).

**Communicates with:**
- Feature Store (read features, compute signals)
- Scoring Engine (write normalized signals)
- Database (company metadata for peer comparison)

**Implementation pattern:**
```python
class SignalAggregator:
    """Convert raw features into normalized signals (0-100)."""

    def __init__(self, db: Database):
        self.db = db

    def compute_signals(self, company: Company) -> SignalVector:
        """Generate all signals for scoring."""

        # Signal 1: SEC Filing Buzzword Density
        sec_features = self.db.get_latest_features(company, 'sec_filing')
        sec_signal = 100 - sec_features['ai_buzzword_density']  # Invert: high density = red flag

        # Signal 2: Patent Filing Rate (normalized by peer)
        patent_count = self.db.count_patents(company, years=2)
        peer_avg = self.db.get_peer_avg_patents(company.industry)
        patent_signal = min(100, (patent_count / peer_avg) * 100)

        # Signal 3: Insider Selling Ratio
        form4_data = self.db.get_form4_summary(company)
        insider_signal = 100 - form4_data['selling_ratio']  # Invert

        # Signal 4: GitHub Activity
        github_data = self.db.get_github_metrics(company)
        github_signal = self.normalize_github_metrics(github_data)

        # Signal 5: Earnings Call Sentiment
        sentiment_data = self.db.get_latest_earnings_sentiment(company)
        sentiment_signal = 100 - sentiment_data['defensive_language_ratio']  # Invert

        return SignalVector(
            sec_filing=sec_signal,
            patent_rate=patent_signal,
            insider_trading=insider_signal,
            github_activity=github_signal,
            earnings_sentiment=sentiment_signal,
            # ... more signals
        )

    def normalize_github_metrics(self, metrics: GitHubMetrics) -> float:
        """Normalize GitHub metrics to 0-100 scale."""
        # Composite score from multiple indicators
        commit_activity = min(100, metrics.commits_per_month / 50 * 100)
        star_growth = min(100, metrics.stars_per_month / 10 * 100)
        contributor_count = min(100, metrics.num_contributors / 20 * 100)

        # Weighted average
        return (0.4 * commit_activity + 0.3 * star_growth + 0.3 * contributor_count)
```

**Peer normalization:**
- Group companies by industry (GICS classification)
- Calculate peer percentile for each company
- Compare to peer 50th percentile (median)
- Handle outliers: cap at 0-100 scale

---

### Component 4: Ensemble Scoring Engine

**Responsibility:** Combine signals into credibility score; apply weighting; generate trade signal.

**Communicates with:**
- Signal data (read normalized signals)
- Scoring metadata (weights, thresholds)
- Output layer (write scores, alerts)

**Implementation pattern:**
```python
class EnsembleScorer:
    """Multi-signal ensemble for credibility scoring."""

    def __init__(self, weights: Dict[str, float]):
        self.weights = weights
        # weights = {
        #     'sec_filing': 0.15,
        #     'patent_rate': 0.15,
        #     'insider_trading': 0.12,
        #     'github_activity': 0.12,
        #     'earnings_sentiment': 0.15,
        #     # ... etc, sum to 1.0
        # }

    def compute_score(self, signals: SignalVector) -> CredibilityScore:
        """Weighted ensemble of signals."""

        # Linear combination
        score = (
            self.weights['sec_filing'] * signals.sec_filing +
            self.weights['patent_rate'] * signals.patent_rate +
            self.weights['insider_trading'] * signals.insider_trading +
            self.weights['github_activity'] * signals.github_activity +
            self.weights['earnings_sentiment'] * signals.earnings_sentiment
            # ... etc
        )

        # Confidence adjustment (lower confidence if data sparse)
        data_coverage = self.measure_data_coverage(signals)
        confidence = self.compute_confidence(data_coverage, signals)

        # Trade signal derivation
        trade_signal = self.signal_to_trade(score)

        # Trend detection (compare to prior scores)
        trend = self.detect_trend(signals.company, prior_scores=3)

        # Key drivers (top signals affecting score)
        drivers = self.identify_key_drivers(signals, self.weights)

        # Red flags (specific concerns)
        red_flags = self.identify_red_flags(signals, score)

        return CredibilityScore(
            score=score,
            confidence=confidence,
            trade_signal=trade_signal,
            trend=trend,
            drivers=drivers,
            red_flags=red_flags,
        )

    def signal_to_trade(self, score: float) -> str:
        """Map credibility score to trade signal."""
        if score < 30:
            return 'SHORT'
        elif score < 50:
            return 'AVOID'
        elif score < 70:
            return 'NEUTRAL'
        else:
            return 'LONG'

    def compute_confidence(self, data_coverage: float, signals: SignalVector) -> str:
        """Assess confidence level based on data completeness and agreement."""
        if data_coverage < 0.6:
            return 'LOW'  # Missing too much data

        # Check signal agreement (ensemble convergence)
        signal_values = [
            signals.sec_filing,
            signals.patent_rate,
            signals.insider_trading,
            signals.github_activity,
        ]
        std_dev = np.std(signal_values)

        if std_dev > 30:  # High divergence
            return 'LOW'
        elif std_dev > 15:
            return 'MEDIUM'
        else:
            return 'HIGH'  # Signals agree
```

**Signal weighting optimization:**
- Initial weights: domain-driven (see RESEARCH.md Part 4.3)
- Refine via logistic regression on labeled data (known washing cases)
- Update quarterly as new data becomes available
- Monitor signal drift (if pattern changes, recalibrate)

---

### Component 5: Data Pipeline Orchestration (Prefect DAG)

**Responsibility:** Schedule and coordinate all tasks; handle dependencies; manage retries.

**Communicates with:**
- All components above (orchestrates their execution)
- Monitoring system (logs, metrics)
- Alert system (trigger on failure)

**Implementation pattern (Prefect Flow):**
```python
from prefect import flow, task
from prefect.task_runs import task_run

@task(name="Fetch SEC filings", retries=3, retry_delay_seconds=60)
def fetch_sec_filings(companies: List[str]) -> Dict[str, Filing]:
    """Fetch 10-K and Form 4 for all companies."""
    fetcher = SecEdgarFetcher(cache=redis_cache)
    results = {}
    for ticker in companies:
        try:
            results[ticker] = fetcher.fetch_10k(ticker, year=2024)
        except Exception as e:
            logger.error(f"Failed to fetch SEC for {ticker}: {e}")
    return results

@task(name="Extract NLP features", retries=2)
def extract_nlp_features(filings: Dict[str, Filing]) -> Dict[str, FeatureVector]:
    """Process documents and extract features."""
    processor = FinancialTextProcessor()
    results = {}
    for ticker, filing in filings.items():
        try:
            results[ticker] = processor.extract_features(filing)
        except Exception as e:
            logger.error(f"Failed NLP processing for {ticker}: {e}")
    return results

@task(name="Compute signals")
def compute_signals(features: Dict[str, FeatureVector]) -> Dict[str, SignalVector]:
    """Aggregate features into normalized signals."""
    aggregator = SignalAggregator(db=postgres_db)
    results = {}
    for ticker, feature_vec in features.items():
        try:
            results[ticker] = aggregator.compute_signals(feature_vec)
        except Exception as e:
            logger.error(f"Failed signal computation for {ticker}: {e}")
    return results

@task(name="Compute credibility scores")
def score_companies(signals: Dict[str, SignalVector]) -> Dict[str, CredibilityScore]:
    """Apply ensemble scoring."""
    scorer = EnsembleScorer(weights=get_current_weights())
    results = {}
    for ticker, signal_vec in signals.items():
        results[ticker] = scorer.compute_score(signal_vec)
    return results

@task(name="Generate alerts")
def generate_alerts(scores: Dict[str, CredibilityScore]) -> None:
    """Alert on significant score changes or red flags."""
    alert_manager = AlertManager(db=postgres_db, email=smtp)
    for ticker, score in scores.items():
        alert_manager.check_and_send(ticker, score)

@flow(name="Daily credibility scoring")
def daily_scoring_flow():
    """Main orchestration flow: daily batch scoring of 500 companies."""

    # Load company list
    companies = load_companies_from_db()  # 500 tickers

    # Stage 1: Data collection (parallel)
    filings = fetch_sec_filings(companies)
    github_data = fetch_github_metrics(companies)
    patent_data = fetch_patents(companies)
    form4_data = fetch_form4(companies)
    # ^ Run in parallel via Prefect's async task execution

    # Stage 2: Feature extraction (sequential, depends on Stage 1)
    nlp_features = extract_nlp_features(filings)

    # Stage 3: Signal aggregation
    signal_vectors = compute_signals(nlp_features)

    # Stage 4: Scoring
    credibility_scores = score_companies(signal_vectors)

    # Stage 5: Output & alerts
    store_scores(credibility_scores)  # Write to database
    generate_alerts(credibility_scores)
    export_results(credibility_scores)  # CSV, API

    return credibility_scores

# Schedule: Daily at 2 AM UTC
if __name__ == "__main__":
    daily_scoring_flow.serve(
        cron="0 2 * * *",  # Every day at 2 AM
    )
```

**Expected execution time:**
- Data fetching (parallel): 8-10 minutes (bottleneck is SEC Edgar rate limiting)
- NLP processing: 5-7 minutes (500 companies × 1 second per company)
- Signal aggregation: 2-3 minutes
- Scoring: <1 minute
- **Total: 15-21 minutes** (within 30-minute SLA)

**Error handling:**
- Task retry on failure (3x, exponential backoff)
- Partial completion allowed (skip failed company, continue)
- Alert on pipeline failure (email to ops team)
- Automatic rerun next day if previous run failed

---

### Component 6: REST API (FastAPI)

**Responsibility:** Serve scores to frontend, external systems, and analysts.

**Endpoints:**
```python
from fastapi import FastAPI, Query, Path

app = FastAPI(title="AI Washing Detector API")

@app.get("/score/{ticker}")
async def get_score(
    ticker: str = Path(..., description="Stock ticker (AAPL, MSFT, etc)"),
) -> CredibilityScore:
    """Get latest credibility score for a company."""
    score = db.get_latest_score(ticker)
    if not score:
        raise HTTPException(status_code=404, detail="Company not found")
    return score

@app.get("/scores")
async def get_scores(
    tickers: str = Query(..., description="Comma-separated tickers (AAPL,MSFT,NVDA)"),
    industry: str = Query(None, description="Filter by industry"),
    min_score: float = Query(None),
    max_score: float = Query(None),
) -> List[CredibilityScore]:
    """Get scores for multiple companies with optional filters."""
    # Parse tickers
    ticker_list = tickers.split(',')

    # Query database
    scores = db.get_scores(ticker_list, industry=industry)

    # Filter by score range
    if min_score is not None:
        scores = [s for s in scores if s.score >= min_score]
    if max_score is not None:
        scores = [s for s in scores if s.score <= max_score]

    return scores

@app.get("/portfolio/{tickers}")
async def analyze_portfolio(
    tickers: str = Path(..., description="Comma-separated portfolio tickers"),
) -> PortfolioAnalysis:
    """Analyze entire portfolio for AI washing risk."""
    ticker_list = tickers.split(',')
    scores = db.get_scores(ticker_list)

    # Portfolio-level metrics
    avg_score = np.mean([s.score for s in scores])
    num_shorts = len([s for s in scores if s.trade_signal == 'SHORT'])
    risk_concentration = analyze_risk_concentration(scores)

    return PortfolioAnalysis(
        num_companies=len(scores),
        avg_score=avg_score,
        short_signals=num_shorts,
        risk_concentration=risk_concentration,
        scores=scores,
    )

@app.get("/history/{ticker}")
async def get_history(
    ticker: str = Path(...),
    days: int = Query(180, description="Number of days of history"),
) -> List[CredibilityScore]:
    """Get historical scores (time-series) for trend analysis."""
    return db.get_scores_history(ticker, days=days)

@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "updated_at": datetime.now()}

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/score/{ticker}")
@limiter.limit("100/minute")  # 100 requests per minute per IP
async def get_score_limited(ticker: str):
    # ...
```

**Authentication (future):**
- API key based (hedge fund credentials)
- Rate limiting per API key
- Audit logging (who fetched what, when)

---

### Component 7: Dashboard & Frontend (Streamlit MVP)

**Responsibility:** Visualize scores, trends, signals for analysts.

**Implementation pattern:**
```python
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# Page 1: Portfolio Overview
st.title("AI Washing Detector - Portfolio Analysis")

# Input: portfolio tickers
portfolio = st.text_input("Enter tickers (comma-separated):", "AAPL,MSFT,NVDA,META")
tickers = portfolio.split(',')

# Fetch data
scores_df = fetch_scores(tickers)

# Summary metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Portfolio Avg Score", f"{scores_df['score'].mean():.1f}", "overall credibility")
with col2:
    short_count = len(scores_df[scores_df['trade_signal'] == 'SHORT'])
    st.metric("SHORT Signals", short_count, f"out of {len(scores_df)}")
with col3:
    avoid_count = len(scores_df[scores_df['trade_signal'] == 'AVOID'])
    st.metric("AVOID Signals", avoid_count, f"out of {len(scores_df)}")

# Scores table
st.subheader("Company Scores")
st.dataframe(
    scores_df[['ticker', 'score', 'trade_signal', 'confidence', 'trend']],
    use_container_width=True,
)

# Detailed view
st.subheader("Score Details")
selected_ticker = st.selectbox("Select company for details:", tickers)
score = fetch_score(selected_ticker)

# Score breakdown (show signal contributions)
fig = go.Figure(data=[
    go.Bar(
        x=['SEC Filing', 'Patent Rate', 'Insider Trading', 'GitHub', 'Earnings Sentiment'],
        y=[
            score.signals['sec_filing'],
            score.signals['patent_rate'],
            score.signals['insider_trading'],
            score.signals['github_activity'],
            score.signals['earnings_sentiment'],
        ],
        marker_color=['red' if v < 50 else 'green' for v in
                     [score.signals[k] for k in ['sec_filing', 'patent_rate', ...]]]
    )
])
st.plotly_chart(fig, use_container_width=True)

# Red flags
st.subheader("Red Flags")
for flag in score.red_flags:
    st.warning(flag)

# Historical trend
st.subheader("Score Trend (6 months)")
history = fetch_score_history(selected_ticker, days=180)
fig = go.Figure()
fig.add_trace(go.Scatter(x=history['date'], y=history['score'], mode='lines+markers'))
st.plotly_chart(fig, use_container_width=True)
```

---

## Data Flow

### Daily Batch Flow

```
[2:00 AM UTC] Prefect triggers daily_scoring_flow
    ↓
[2:00 - 2:10] Parallel data fetches (SEC, GitHub, USPTO, Form 4)
    ↓
[2:10 - 2:15] NLP feature extraction (FinBERT sentiment, buzzword counting)
    ↓
[2:15 - 2:18] Signal aggregation (normalization, peer comparison)
    ↓
[2:18 - 2:19] Ensemble scoring (apply weights, compute final scores)
    ↓
[2:19 - 2:20] Output: store in PostgreSQL, generate API responses
    ↓
[2:20 - 2:21] Alert generation (email on score changes >10 points)
    ↓
[2:21] Dashboard auto-updates (users see new scores)
```

### Example data transformation (Company TSLA)

```
Raw data:
  10-K text: 50,000 words, 200 AI mentions
  Form 4: 50 insider transactions, 30 sells, 20 buys
  Patents: 15 patents filed in past 2 years
  GitHub: 45 commits/month, 2000 stars

Feature extraction:
  ai_buzzword_density: 0.40% (200/50000)
  insider_selling_ratio: 60% (30/(30+20))
  patent_rate: 7.5 per year
  github_commits: 45/month

Normalization (peer comparison):
  sec_filing_signal: 25 (high AI density = red flag)
  patent_signal: 95 (peers avg 5/year, TSLA at 7.5 = above average)
  insider_signal: 40 (60% selling is high)
  github_signal: 85 (45 commits/month is healthy)

Ensemble score:
  score = 0.15*25 + 0.15*95 + 0.12*40 + 0.12*85 + ...
  score ≈ 55 (NEUTRAL)

Output:
  trade_signal: NEUTRAL
  confidence: MEDIUM
  red_flags: ["High AI mention density", "Insider selling 60%"]
```

---

## Scalability Considerations

| Concern | At 100 Users | At 10K Users | At 1M Users |
|---------|--------------|--------------|------------|
| **Data ingestion (500 cos)** | 20 min batch | 20 min batch (parallel APIs) | Distributed data collection across regions |
| **NLP processing** | 1 GPU or CPU | GPU cluster (4-8 GPUs) | Distributed transformer inference (Ray) |
| **Database** | Single Postgres instance (t3.medium) | Postgres replica + read replicas | Distributed databases (sharding by industry) |
| **API requests** | FastAPI single instance | Load balancer + 2-3 instances | Kubernetes cluster (auto-scaling) |
| **Storage** | 100GB (filings + features) | 1TB | 10TB+ (archival storage on S3) |
| **Cost** | $500-1000/month | $2000-5000/month | $20k-50k/month |

**Recommended approach:**
- MVP: Single instance, Postgres on t3.medium
- Phase 2: Add read replicas, cache layer (Redis)
- Phase 3: Kubernetes if user base grows beyond 1000

---

## Error Handling & Resilience

**Data pipeline failures:**
- Partial failure (1-2 companies fail): Log, continue, alert ops
- Major failure (API down): Use cached data from yesterday, warn analyst
- Stuck process (timeout): Auto-kill after 60 min, retry next cycle

**Data quality issues:**
- Malformed SEC filing: Skip, log, notify
- Missing data for company: Mark confidence as LOW
- Outlier signal values: Clip to 0-100, investigate
- API rate limiting: Exponential backoff, queue for retry

**Database failures:**
- Connection drop: Automatic reconnect with exponential backoff
- Transaction rollback: Log failure, skip batch, notify ops
- Disk full: Automated alerting; archive old data to S3

**Monitoring:**
- Health checks: `/health` endpoint returns database + API status
- Metrics: Prometheus scrapes pipeline latency, error rates, signal quality
- Alerting: PagerDuty if pipeline fails or SLA breached

---

## Deployment Architecture (AWS)

```
AWS Infrastructure:
├─ EC2 instance (t3.large) - Prefect orchestration + FastAPI server
├─ RDS PostgreSQL (db.t3.medium) - Feature store + metadata
├─ ElastiCache Redis (cache.t3.micro) - API response caching
├─ S3 bucket - Archive filings, transcripts, backups
├─ CloudWatch - Logs, metrics, dashboards
└─ SNS/SES - Alerts via email

CI/CD:
├─ GitHub Actions - Run tests, build Docker image
├─ ECR - Container registry
└─ Auto-deploy on main branch merge
```

**Cost estimate (running 24x7):**
- EC2 t3.large: $60/month
- RDS db.t3.medium: $35/month
- ElastiCache cache.t3.micro: $20/month
- S3 (1TB): $25/month
- Data transfer: $50/month
- **Total: ~$190/month** (development); scales to $500-1000 in production

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Real-time scoring (Trap)
**What goes wrong:** Overengineering for real-time updates when daily batch is sufficient
**Why it happens:** False urgency; "we need real-time" mentality
**Instead:** Daily batch (2 AM UTC); cache aggressively; API serve cached results

### Anti-Pattern 2: Single data source (Trap)
**What goes wrong:** Relying on one API (e.g., SEC Edgar only); if it fails, whole system fails
**Why it happens:** Simpler architecture
**Instead:** Multi-source architecture; graceful degradation if one source fails

### Anti-Pattern 3: Opaque ensemble (Trap)
**What goes wrong:** Black-box ML model; analyst can't understand why score is 45 vs 50
**Why it happens:** Temptation to use gradient-boosted trees or neural nets
**Instead:** Interpretable ensemble (weighted linear combo); show signal contributions

### Anti-Pattern 4: No backtesting (Trap)
**What goes wrong:** Deploy system, discover it has 30% false positive rate
**Why it happens:** Rushing to production
**Instead:** Validate on 50+ historical cases before launch

### Anti-Pattern 5: Ignoring data quality (Trap)
**What goes wrong:** Bad SEC filing parse → garbage scores
**Why it happens:** Assumes data is clean
**Instead:** Data validation pipeline; confidence flags; manual spot-checks

---

## Summary

Recommended architecture: **Batch + Cache + Ensemble**

- **Batch processing** (daily, 30-minute SLA) sufficient for portfolio analysis
- **Caching layer** (Redis) reduces API costs and latency
- **Interpretable ensemble** (weighted signals, not ML black box) enables trust
- **Multi-source data** (SEC, GitHub, USPTO, transcripts) reduces single points of failure
- **Scalable to 10K+ companies** with minimal infrastructure cost increase
