# Feature Landscape - AI Washing Detector

**Domain:** Financial signal detection for AI claim credibility (mid-cap US equities)
**Researched:** 2026-03-31
**Target User:** Hedge fund portfolio managers, quant researchers

---

## Table Stakes Features

Users expect these or the product feels incomplete. **MVP must deliver all of these.**

| Feature | Why Expected | Complexity | Phase | Notes |
|---------|--------------|------------|-------|-------|
| **Credibility score (0-100) per ticker** | Core value prop; enables ranking | LOW | 1 | Output: single float, updated daily |
| **SEC filing analysis (AI buzzword density)** | Primary data source; free legal access | LOW | 1 | Extract 10-K/10-Q, count AI mentions, normalize |
| **Form 4 insider trading ratio** | Strong fraud indicator (well-established) | LOW | 1 | Aggregate insider selling % per company |
| **Patent filing rate tracking** | Concrete R&D indicator; objective metric | LOW | 1 | Compare company's patent output to peers |
| **GitHub org activity aggregation** | Public code signal; technical credibility | LOW | 1 | Aggregate repo metrics (commits, stars, activity) |
| **Earnings call sentiment analysis** | Detect defensive language patterns | MEDIUM | 2 | FinBERT classification on transcript text |
| **Historical score trending (6+ months)** | Validate signal stability, detect inflection points | LOW | 2 | Time-series storage, trend visualization |
| **Industry peer benchmarking** | Contextualize scores; avoid false positives | MEDIUM | 2 | Group companies by industry; relative scoring |
| **Multi-signal weighting explanation** | Transparency; justify "why" this score | MEDIUM | 1 | Show contribution of each signal to final score |
| **Trade signal (SHORT/AVOID/NEUTRAL/LONG)** | Actionable recommendation for portfolio | LOW | 1 | Rule-based mapping: score 0-30 = SHORT, etc. |
| **Company profile & metadata** | Basic context (sector, market cap, CEO) | LOW | 1 | Fetch from Yahoo Finance / SEC filings |
| **Alert triggers** | Notify on material score changes | MEDIUM | 2 | Email/webhook on score drop >10 points |

---

## Differentiators

Features that set product apart; not expected but highly valued. **Phase 2-3 features.**

| Feature | Value Proposition | Complexity | Phase | Implementation |
|---------|-------------------|------------|-------|-----------------|
| **"Coming soon" feature tracking** | Detect when companies commit to features they never deliver | HIGH | 2 | Scrape product roadmaps, blogs, press releases; NLP for "coming soon/Q4 2024" patterns |
| **CEO/leadership health signals** | Detect when leadership changes (health, departures) correlate with washing | HIGH | 3 | Monitor news, LinkedIn, SEC filings for executive departures; objective metrics hard |
| **Customer concentration analysis** | Detect when revenue concentration masks growth claims | MEDIUM | 2 | Extract from 10-K (top customer list); calculate Herfindahl index |
| **Product latency benchmarking** | For companies with public APIs, measure actual performance | HIGH | 3 | Query product APIs; monitor uptime, response time, error rates |
| **Real-time earnings call alerts** | Alert during earnings call if CEO suddenly shifts tone on AI | HIGH | 3 | Integrate live transcript feed (expensive); real-time sentiment analysis |
| **Academic publication tracking** | Real AI companies publish; washing companies don't | MEDIUM | 2 | Track company researchers on arXiv, Google Scholar |
| **Employee public content analysis** | LinkedIn posts by employees: AI project mentions, technical depth | MEDIUM | 3 | Proxy for technical authenticity; avoid direct scraping (legal risk) |
| **Competitive win/loss intelligence** | Track sales team signals; real AI products win deals | HIGH | 3 | Requires proprietary sales data or third-party vendor (not available free) |
| **Cash burn rate vs. AI spend** | Companies burning cash faster than AI ROI delivers = red flag | MEDIUM | 2 | Extract from 10-K/10-Q financial statements |
| **Supply chain validation** | Check if company's claimed AI suppliers (chips, cloud) are plausible | MEDIUM | 3 | Cross-reference AWS bills, Nvidia purchase agreements (hard to find) |
| **Quantitative backtest results** | Show historical accuracy on known washing cases | MEDIUM | 1 | Run detector on Builder.ai, C3, Nate, Evolv; validate signal strength |
| **Peer comparison (relative scores)** | "Company X scores 45; peers score 75; relative credibility low" | LOW | 2 | Sort by industry; show industry percentile |
| **Custom weighting override** | Analyst can adjust signal weights based on domain expertise | MEDIUM | 3 | UI sliders for signal weights; recompute score |
| **Export/API access** | Integrate scores into fund's existing trading systems | LOW | 2 | REST API for score queries; bulk export (CSV) |

---

## Anti-Features

Explicitly NOT building these. Say "no" clearly.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **"This company is committing fraud" accusation** | Legal liability; defamation risk | Frame as "credibility score" based on public signals; let analyst decide |
| **Publish short thesis reports** | Short-seller model is different; we're risk scoring, not making calls | Provide score + data; analyst writes their own thesis |
| **Proprietary ML model (black box)** | Financial institutions require explainability; regulators demand it | Use interpretable signals (buzzword counts, patent rate); show contribution of each |
| **Real-time intraday trading signals** | Requires market-making capabilities; conflicts with hedge fund fiduciary duty | Daily batch updates are sufficient for portfolio decisions |
| **Support all securities (crypto, forex)** | Crypto is different problem (no SEC filings); scope creep | Start with US mid-cap equities; extend later if needed |
| **Predict stock price movements** | That's a different product (stock forecasting); conflates credibility with price | Focus on credibility signals, not price prediction |
| **Replace human analyst research** | Our signals are weak individually; ensemble is medium strength | Position as analyst tool, not replacement |
| **Support early-stage private companies** | No SEC data, patents sparse, GitHub activity varies wildly | Require public companies with SEC filing history |
| **International AI washing detection** | Regulatory filings differ (UK, EU, Asia); different data sources | Start with US-listed; extend geographically in Phase 3 |

---

## Feature Dependencies

```
Core dependencies for MVP:

SEC filing analysis ← CIK lookup ← Company database
      ↓
Buzzword density score
      ↓
Multi-signal ensemble ← Patent rate ← USPTO API
                     ← Insider selling ← Form 4 parsing ← SEC Edgar
                     ← GitHub activity ← GitHub API
                     ↓
             Credibility score (0-100)
                     ↓
             Trade signal (SHORT/AVOID/NEUTRAL/LONG)

Phase 2 dependencies:

Earnings call sentiment ← Transcript sourcing (Seeking Alpha)
                      ← FinBERT classification
                      ↓
   Industry benchmarking ← Peer group classification
   Customer concentration ← 10-K parsing (top customers)
                      ↓
         Score trend analysis ← Historical data store
                      ↓
                  Alerts/dashboard

Phase 3 extensions:

CEO tracking ← News feeds
Leadership changes ← SEC filings (executive changes)
Product latency ← API availability (if company has public API)
Academic publications ← arXiv/Scholar tracking
```

---

## Feature Specification: Credibility Score

### Input Data Model

```python
class CredibilitySignals:
    # Tier 1 (MVP)
    sec_filing_ai_density: float          # 0-100 (% AI mentions)
    insider_selling_ratio: float           # 0-100 (% insiders selling)
    patent_rate_percentile: float          # 0-100 (vs. industry peers)
    github_activity_score: float           # 0-100 (commits, stars, activity)

    # Tier 2 (Phase 2)
    earnings_call_sentiment: float         # 0-100 (defensive language ratio)
    industry_peer_relative: float          # 0-100 (vs. cohort average)
    customer_concentration: float          # 0-100 (Herfindahl index)

    # Tier 3 (Phase 3)
    academic_publication_rate: float       # 0-100 (researcher presence)
    product_api_health: float              # 0-100 (latency, uptime)
    leadership_stability: float            # 0-100 (turnover rate)

    # Metadata
    data_freshness_days: int               # How old is the newest signal
    coverage_completeness: float           # % of signals available (0-100)
    confidence_level: str                  # HIGH/MEDIUM/LOW
```

### Output Data Model

```python
class CredibilityScore:
    ticker: str
    company_name: str
    score: float                           # 0-100
    trade_signal: str                      # SHORT / AVOID / NEUTRAL / LONG
    signal_breakdown: Dict[str, float]     # Contribution of each signal
    trend: str                             # IMPROVING / STABLE / DECLINING
    confidence: str                        # HIGH / MEDIUM / LOW
    updated_at: datetime
    next_update_at: datetime
    key_drivers: List[str]                 # Top 3 signals affecting score
    red_flags: List[str]                   # Specific concerns
```

### Score Interpretation

```
Score 0-20:    CRITICAL - Likely AI washing; high short conviction
Score 20-40:   HIGH RISK - Multiple red flags; avoid or short
Score 40-60:   MODERATE RISK - Mixed signals; require deeper analysis
Score 60-80:   MODERATE CREDIBLE - Generally aligned signals; acceptable
Score 80-100:  CREDIBLE - Strong evidence of legitimate AI integration

Trade Signal Mapping:
0-30:   SHORT (high conviction)
30-50:  AVOID (too risky to hold)
50-70:  NEUTRAL (hold existing positions; don't add)
70-100: LONG (credible; can increase position)
```

---

## MVP Feature Set (Weeks 1-8)

**Must deliver for portfolio managers:**

1. Daily automated scoring of 500 companies
2. Credibility score (0-100) per ticker
3. Trade signal (SHORT/AVOID/NEUTRAL/LONG)
4. Signal breakdown (show contribution of each: SEC, Form 4, patents, GitHub)
5. Historical trending (6+ months)
6. Industry peer benchmarking
7. Email alerts on score changes >10 points
8. Dashboard: sortable company list, score details, red flags
9. API access: `GET /api/score/{ticker}`, `GET /api/portfolio/{tickers}`
10. Backtest validation on 10+ known washing cases

**Success criteria:**
- Correctly identifies 80%+ of known washing cases (true positive rate)
- False positive rate <20% (legitimate companies mis-scored as washing)
- Daily update completes in <30 minutes (500 companies)
- API response time <200ms (95th percentile)
- Dashboard loads in <2 seconds

---

## Phase 2 Features (Weeks 9-14)

1. Earnings call sentiment integration
2. Customer concentration alerts
3. Leadership change tracking
4. Academic publication tracking
5. Advanced trend analysis (inflection point detection)
6. Customizable alert thresholds per analyst
7. Bulk portfolio analysis (10K+ companies if needed)
8. Export to Excel/CSV

---

## Phase 3 Features (Weeks 15-21)

1. Real-time earnings call sentiment (live transcript integration)
2. Product API monitoring (latency, uptime tracking)
3. CEO/leadership health signals (news feed analysis)
4. Custom signal weighting override
5. Analyst collaboration (shared notes, tags)
6. Integration with Bloomberg Terminal (if licenses available)
7. International stock support (UK, EU, Asia)

---

## Success Metrics for Each Feature

| Feature | Success Metric |
|---------|----------------|
| **Credibility score** | Correlates with 6-month stock returns (r > 0.5); scores <40 precede negative returns |
| **Trade signal** | SHORT signal precedes -10% to -30% returns within 6 months (50%+ accuracy) |
| **SEC filing analysis** | Buzzword density correlates with patent filing gap (r > 0.4) |
| **Form 4 tracking** | Insider selling ratio >60% correlates with negative returns |
| **GitHub activity** | Companies with high activity have better product quality signals (validated via reviews) |
| **Earnings call sentiment** | Defensive tone correlates with earnings surprises (r > 0.3) |
| **Alerts** | Analyst acts on 20%+ of alerts (alert signal/noise ratio >1) |
| **Dashboard** | Used daily by analysts; >80% dashboard sessions lead to analysis (not bounces) |

---

## Known Constraints

**Data availability:**
- LinkedIn scraping prohibited; must use job postings + GitHub as proxy
- Earnings transcripts: free from Seeking Alpha (may require scraping), paid from professional services
- CEO/leadership data sparse; news feeds have gaps

**Accuracy limitations:**
- Individual signals only 55-65% accurate; ensemble achieves ~70-75%
- Legitimate R&D-heavy companies may score similarly to washing companies
- Time lag: most signals lag actual events by 1-4 months

**Regulatory constraints:**
- Cannot publish accusatory theses ("Company X is defrauding investors")
- Must document methodology and assumptions
- May trigger securities lawyers' review if trading on this internally

---

## Feature Roadmap Summary

```
Phase 1 (MVP): Core scoring → Trade signals → Backtest validation
Phase 2: Advanced signals → Trend analysis → Broader portfolio coverage
Phase 3: Real-time features → International scope → Analyst tools
```

**Recommended approach:** Build Phase 1 features tight; validate signals; then expand.
