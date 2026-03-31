# Domain Pitfalls - AI Washing Detector

**Domain:** Financial signal detection, AI credibility scoring
**Researched:** 2026-03-31
**Target audience:** Hedge fund portfolio managers, quant researchers

---

## Critical Pitfalls

Mistakes that cause rewrites, regulatory issues, or major signal failures.

### Pitfall 1: False Positives Erode Trust (Critical)

**What goes wrong:**
- System scores legitimate, high-R&D companies as "washing" (e.g., Tesla, OpenAI, Anthropic)
- Portfolio manager sells position based on low score; company's AI narrative turns out accurate
- Manager stops using system after 1-2 false positives

**Why it happens:**
- High AI buzzword density is NOT correlated with fraud; legitimate R&D-heavy companies talk about AI constantly
- Insider selling can be tax-driven or diversification, not fraud signals
- GitHub activity sparse for companies using private repos (stealth development)
- Patent lag (18 months) means recent breakthroughs not yet visible

**Consequences:**
- System loses credibility immediately (even if 70% accuracy overall)
- High false positive rate → analyst ignores alerts
- Reputational damage if analyst acts on false signal

**Prevention:**
1. **Peer-relative scoring, not absolute:** Score company vs. industry cohort
   - Tesla vs. auto manufacturers (not vs. fintech companies)
   - Normalize signals by industry average, not global average
2. **High confidence threshold before alerting:** Only alert if multiple signals agree (ensemble convergence)
   - Threshold: confidence > 70% before sending alert
   - Flag high-divergence scores as unreliable
3. **Extensive backtesting on known cases:** Test on 50+ cases (both washing + legitimate) before launch
   - Validate false positive rate <15%
4. **Analyst override capability:** Let analyst manually mark "legitimate AI company" to suppress alerts
5. **Signal diversity:** Don't rely on single signal (e.g., AI buzzword density alone)
   - Use ensemble: if 5/7 signals agree, confidence high; if 3/7 agree, confidence low

**Detection:**
- Monitor alert accuracy: What % of SHORT signals precede negative returns?
- Analyst feedback: "How many false positives did you see this month?"
- Compare score trends to actual company performance

---

### Pitfall 2: Regulatory & Legal Exposure (Critical)

**What goes wrong:**
- System publicly rates company as "washing"; company sues for defamation
- Analyst uses system to make short recommendation; SEC investigates for market manipulation
- Internal trading decisions based on this research; compliance issues arise

**Why it happens:**
- Financial fraud accusations are legally actionable (high stakes)
- Short-seller reports (Hindenburg, Citron) get sued regularly
- Securities laws restrict what statements can be made

**Consequences:**
- Legal liability: $1M+ in legal costs, damages
- Regulatory investigation: SEC subpoenas, trading bans
- Reputational damage: "Hedge fund accused of manipulation"

**Prevention:**
1. **Never publish accusations:** Frame as "credibility score," not "fraud detection"
   - Output: "Score 35/100 based on public signals"
   - NOT: "Company is committing fraud"
2. **Base claims only on public data:**
   - Use SEC filings, patents, GitHub, public news
   - Don't use non-public intel or insider interviews
3. **Extensive legal review before publishing:**
   - Have securities lawyer review any analyst reports using system
   - Flag language that could be interpreted as accusations
4. **Use system internally only (MVP):**
   - Don't publish scores publicly until legal framework clear
   - Hedge funds use for internal portfolio decisions (less exposure)
5. **Document methodology:**
   - Maintain audit trail showing how score was computed
   - Defend methodology in event of legal challenge

**Detection:**
- Legal review checklist before any external communication
- Audit log of who accessed scores and how they used them
- External counsel approval before any public reports

---

### Pitfall 3: Data Pipeline Brittleness (Critical for Operations)

**What goes wrong:**
- SEC API changes format → pipeline breaks; no scores for 3 days
- Seeking Alpha stops exposing earnings transcripts → sentiment signal disappears
- GitHub org is deleted or made private → GitHub signal drops to zero
- ETL job gets stuck (infinite loop); entire batch processing delayed by 6+ hours

**Why it happens:**
- External APIs are not stable; they change format/endpoints without warning
- Web scraping breaks when DOM structure changes
- No monitoring or alerting on data freshness
- Single points of failure (one API going down blocks entire pipeline)

**Consequences:**
- No updated scores for days → analyst making decisions on stale data
- False confidence: analyst thinks score is 1 day old; it's actually 7 days old
- Wasted debugging time (nobody alerts; pipeline silently fails)
- Portfolio decisions based on bad/missing data

**Prevention:**
1. **Build redundancy:**
   - Multiple data sources per signal (if Seeking Alpha fails, fall back to official investor relations PDFs)
   - Graceful degradation: missing one signal → compute score without it, lower confidence
2. **Data freshness monitoring:**
   - Flag any signal older than 7 days as "stale"
   - Alert if pipeline doesn't complete within 30 minutes
   - Dashboard shows "as of [timestamp]" prominently
3. **Version API contracts:**
   - Lock versions of data format (SEC Edgar XBRL schema version)
   - Test on multiple versions before upgrading
4. **Error handling in pipeline:**
   - Catch exceptions per company (don't fail entire batch)
   - Log failures; skip failed companies; continue processing others
   - Retry failed companies with exponential backoff
5. **Monitoring + alerting:**
   - Prometheus: track pipeline latency, error rates
   - PagerDuty: alert if pipeline incomplete by 3 AM UTC
   - CloudWatch: log all API failures, rate limiting events

**Detection:**
- Dashboard shows data freshness for each signal
- Alert: "Form 4 data is 14 days old; consider confidence LOW"
- Weekly data quality report: "X% of companies missing Y signal"

---

### Pitfall 4: Misaligned Signal Weights (High Impact)

**What goes wrong:**
- Optimize weights on historical data; weights overfit
- Weight insider trading too high (60%); system becomes noisy (false positives from tax sales)
- Weight SEC filing AI density too high; legitimate companies with high R&D overpenalized
- Weights become stale; market changes but weights stay fixed

**Why it happens:**
- Weights initially chosen via domain expertise, not data
- Limited training data (50-100 labeled washing cases)
- Temptation to maximize historical accuracy (overfitting)
- No automatic reweighting process

**Consequences:**
- System optimized for past fraud cases; doesn't work on new washing patterns
- False positive rate increases over time
- System becomes increasingly unreliable

**Prevention:**
1. **Conservative initial weights:** Domain-driven, not data-driven
   - All signals equal weight (0.2 each for 5 signals) initially
   - Adjust only after sufficient data
2. **Quarterly weight review:**
   - Measure historical accuracy of each signal
   - Adjust weights based on signal reliability
   - Compare predictions to actual outcomes (6-month forward returns)
3. **Regularization to prevent overfitting:**
   - Constraint: no weight >0.25 (prevent single signal dominance)
   - Use cross-validation (train on 80% of cases, test on 20%)
4. **Gradual weight changes:**
   - Never change weights by >5% in single quarter
   - Prevent sudden systematic changes to scores
5. **Analyst feedback loop:**
   - Solicit analyst feedback on score changes
   - "Why did Tesla score drop 20 points?" → investigate

**Detection:**
- Compare actual outcome (6-month returns) to score
- Calculate hit rate per signal (% of SHORT signals precede negative returns)
- Monitor for signal drift (is signal still predictive?)

---

### Pitfall 5: Temporal Misalignment (Data Stale Before Use)

**What goes wrong:**
- 10-K filed on March 31; analyst sees score on April 15
- By April 15, new information already public (earnings call, guidance cut)
- Score is 2 weeks stale, analyst acts on old information

**Why it happens:**
- SEC filings have 60+ day publication windows
- Patents published 18 months after filing
- Company announcements happen; then 10-K arrives later with stale info
- No timeline awareness in system

**Consequences:**
- Analyst acts on scores that incorporate old information
- Misses material recent developments
- Score seeming "predictive" is actually lagging (data artifact)

**Prevention:**
1. **Combine recent + historical data:**
   - Use latest earnings call (most recent signal)
   - Use 10-K (comprehensive but lagged)
   - Use insider trading form 4 (real-time)
   - Use news feed (very recent)
2. **Weight recent data higher:**
   - Form 4 (4-day lag) weighted higher than 10-K (60-day lag)
   - Earnings call (live) given high weight
3. **Explicit recency adjustment:**
   - "This score is based on data from [date]; recent news not yet incorporated"
   - Update score within 24 hours of major announcements
4. **Real-time alert signals:**
   - Monitor news, earnings calls, insider transactions in parallel
   - Alert analyst immediately on material changes (don't wait for batch)

**Detection:**
- Compare score timing to actual events
- "Score dropped on April 15; what happened on April 1-14 that wasn't yet in score?"
- Monitor data lag: are signals fresh or stale?

---

## Moderate Pitfalls

Common mistakes; not rewrite-level, but operationally painful.

### Pitfall 6: Missing Data Handling (Moderate)

**What goes wrong:**
- Company has no GitHub org → github_signal = missing/zero
- Company doesn't file patents (business model doesn't use IP) → patent_signal = missing
- System computes score using only 3/7 signals; analyst assumes score incorporates all signals
- Score seems low, but actually just missing favorable signals

**Why it happens:**
- Not all companies have all data sources
- Early-stage companies sparse GitHub activity
- Service companies (no patents) vs. product companies (many patents)

**Consequences:**
- Unfair scoring; companies missing data sources scored low just because data absent
- Confidence not properly adjusted for missing data

**Prevention:**
1. **Explicit missing data handling:**
   ```python
   if signal_missing:
       score = weighted_average(available_signals) / sum(available_weights)
       confidence = confidence * (num_available / num_total_signals)
   ```
2. **Imputation (use industry averages):**
   - If GitHub data missing, use industry peer average
   - Flag as imputed (low confidence)
3. **Confidence adjustment:**
   - Full data coverage: confidence HIGH
   - 1-2 signals missing: confidence MEDIUM
   - 3+ signals missing: confidence LOW (don't alert)
4. **Per-company metadata:**
   - Track which signals available for each company
   - Industry classification (software vs. hardware)
   - Size/age (startup vs. established)

**Detection:**
- Dashboard column: "Data completeness: 6/7 signals (86%)"
- Filter: "Show companies with complete data only"
- Alert: "Score low but 3 signals missing; confidence is LOW"

---

### Pitfall 7: Industry Normalization Fails (Moderate)

**What goes wrong:**
- Score company by software industry norms; company actually hardware (or fintech, or healthcare)
- Mistaken industry classification → wrong peer group → wrong normalized scores
- All companies in cohort are washing (e.g., crypto scams) → normalization by peer gives false legitimacy

**Why it happens:**
- Company description ambiguous (is Tesla a car company or AI company?)
- Automatic industry classification (GICS) sometimes wrong
- No validation that peer group is valid

**Consequences:**
- Score is systematically biased (too high or too low for cohort)
- False negatives: washing companies score high because all peers are washing

**Prevention:**
1. **Manual industry validation:** Analyst reviews industry classification
2. **Multiple cohort definitions:**
   - Primary: GICS industry
   - Secondary: Custom cohort (AI companies, automotive, fintech, etc.)
   - Show both, let analyst choose
3. **Peer group sanity check:**
   - If 80% of cohort in washing risk, flag (cohort may all be bad)
   - Compare cohort average to market average
4. **Per-company industry override:**
   - Analyst can manually specify "treat as software company, not hardware"

**Detection:**
- Compare company's score to published analyst reports
- "Is this company classified correctly?"
- Cohort validation: "Do these companies make sense as peers?"

---

### Pitfall 8: Seasonal / Time-Based Bias (Moderate)

**What goes wrong:**
- AI companies have higher earnings call activity during earnings season (Q1, Q2, Q3, Q4)
- Comparing company at earnings time vs. non-earnings time → different signal strength
- Score swings wildly month-to-month (false trend)

**Why it happens:**
- Earnings calls release all at once (Q1 earnings: Jan 20 - Feb 20)
- 10-K filed once/year (March-April)
- Some signals are episodic (insider trading, announcements)

**Consequences:**
- Score appears to trend when actually just seasonal
- Analyst misinterprets natural variation as real change

**Prevention:**
1. **Account for seasonality:**
   - When computing trend, detrend seasonality first
   - "Score increased 15 points; 10 points due to seasonality; 5 points real change"
2. **Seasonal adjustment:**
   - Use 12-month rolling average to smooth seasonal effects
   - Compare month-to-month with same month last year
3. **Explicit documentation:**
   - Flag scores as "from earnings season" (higher signal strength)
   - Adjust confidence for seasonal signals
4. **Multi-year trending:**
   - Don't read too much into single-month changes
   - Focus on 6+ month trends

**Detection:**
- Compare same-month scores year-over-year
- Visualize seasonality: overlay current year vs. prior year
- Statistical test: is score change statistically significant?

---

### Pitfall 9: Analyst Overconfidence (Moderate)

**What goes wrong:**
- System assigns 45/100 score with 55% confidence
- Analyst interprets this as "45% chance of fraud" (wrong)
- Analyst sizes position based on false confidence
- Makes big bet that loses when score was actually unreliable

**Why it happens:**
- Confidence level is system's assessment of data quality, not probability of fraud
- Analyst doesn't understand the difference

**Consequences:**
- Oversized positions based on overconfident scores
- Portfolio concentration risk

**Prevention:**
1. **Clear confidence definition:**
   - "HIGH confidence: 5+ signals available, data fresh, signals agree"
   - "LOW confidence: 1-2 signals, data stale, signals diverge"
2. **Not a probability:**
   - "This score is 45; confidence in this estimate is MEDIUM"
   - NOT: "45% chance of fraud"
3. **Position sizing guidance:**
   - HIGH confidence: can trade on this
   - MEDIUM confidence: smaller position size
   - LOW confidence: hold position, don't increase
4. **Training:** Teach analysts how to interpret scores

**Detection:**
- Analyst training / documentation review
- Survey: "What does a 45/100 score mean to you?"
- Monitor position sizing: is it proportional to confidence?

---

## Minor Pitfalls

Low-impact issues; operational nuisances.

### Pitfall 10: API Rate Limiting Causes Delays

**What goes wrong:**
- SEC Edgar rate limit 10 req/sec hit; pipeline waits for rate limit window
- Takes 45 minutes instead of 20 minutes to complete batch

**Prevention:**
- Cache aggressively (24-hour TTL)
- Batch requests (pull all 500 companies at once, not serially)
- Use exponential backoff (don't slam API on retry)

---

### Pitfall 11: Stale Score Presented as Current

**What goes wrong:**
- Analyst sees score; assumes it's updated today
- Actually last updated 7 days ago (pipeline failed silently)
- Analyst makes decision on very stale information

**Prevention:**
- Always show "Updated: [timestamp]" prominently
- Alert if data >3 days old
- Color-code stale scores (gray background)

---

### Pitfall 12: GitHub Activity Noise (Private Repos)

**What goes wrong:**
- Company uses GitHub but keeps repos private (internal development)
- GitHub signal is zero; score penalized
- Company actually has strong engineering but can't measure it

**Prevention:**
- Acknowledge GitHub limitation in confidence notes
- Use alternative signals (patents, job postings) to validate
- Only use GitHub as confirming signal, not primary

---

### Pitfall 13: Earnings Call Transcripts Inaccurate

**What goes wrong:**
- Transcript has errors (OCR issues, name misspellings)
- CEO quote misattributed
- Sentiment analysis picks up joke or sarcasm as real statement

**Prevention:**
- Use official transcripts (company investor relations) when possible
- Manual spot-check on high-impact companies
- Don't rely on earnings sentiment alone

---

### Pitfall 14: Insider Selling Can Be Innocent

**What goes wrong:**
- CEO diversifies portfolio (not fraud signal, just tax planning)
- System penalizes for insider selling; score drops
- Score misinterprets innocent action as red flag

**Prevention:**
- Distinguish between types of insider transactions:
  - Rule 10b5-1 plans (pre-planned, less suspicious)
  - Opportunistic sales (more suspicious)
- Weight officer-level sales higher than director sales
- Look for correlation: selling during hype peak = more suspicious

---

### Pitfall 15: AI Buzzword Extraction Noisy

**What goes wrong:**
- Company mentions "AI" once in passing; score reflects high AI density
- Sentence: "We're not using AI for this feature" caught as AI mention
- Regulatory disclaimers about AI risks trigger buzzword count

**Prevention:**
- Use NLP (spaCy) not just regex
- Contextualize: is sentence positive/negative about AI?
- Weight claims in main business section higher than disclaimers
- Normalize by document length (density = mentions / total words)

---

## Phase-Specific Warnings

| Phase | Likely Pitfall | Mitigation |
|-------|---------------|-----------|
| **Phase 1: MVP** | Data pipeline brittleness; API changes break things | Build redundancy early; assume APIs will break |
| **Phase 1: MVP** | False positives erode trust immediately | Extensive backtesting; conservative thresholds |
| **Phase 1: MVP** | Missing infrastructure monitoring | Add CloudWatch, alerting from day 1 |
| **Phase 2: Expansion** | Score weights become stale | Implement quarterly weight review process |
| **Phase 2: Expansion** | Confidence not properly tracked | Add confidence scores to all outputs; monitor |
| **Phase 2: Expansion** | Industry classification wrong at scale | Implement industry validation workflow |
| **Phase 3: Production** | Regulatory exposure when publishing | Legal review before any external communication |
| **Phase 3: Production** | Analyst overconfidence in system | Training + documentation; position sizing guardrails |
| **Phase 3: Production** | Real-time monitoring breaks SLA | Implement circuit breakers; graceful degradation |

---

## Risk Mitigation Checklist (Pre-Launch)

### Data Quality
- [ ] Backtest on 50+ known cases (target: >70% accuracy on known washing, <15% false positives)
- [ ] Validate signal reliability (each signal >55% accuracy individually)
- [ ] Measure data freshness (average lag per signal documented)
- [ ] Test missing data handling (score computed correctly with incomplete data)

### Operational Resilience
- [ ] Pipeline monitoring (CloudWatch alerts, PagerDuty on failure)
- [ ] Data redundancy (multiple sources per signal)
- [ ] Graceful degradation (pipeline works even if one API fails)
- [ ] Database backups (daily automated, tested restore)
- [ ] Error logging (all failures logged, searchable)

### Legal & Compliance
- [ ] Securities lawyer review (methodology defensible)
- [ ] Audit trail (track all score computations, changes)
- [ ] No publication of accusations (frame as credibility score)
- [ ] Use only public data (no non-public intelligence)
- [ ] Documentation (keep methodology docs updated)

### Analyst Usability
- [ ] Clear confidence levels (analyst understands what they mean)
- [ ] Explainable scores (show signal contributions)
- [ ] Data freshness visible (timestamp on all outputs)
- [ ] Alert tuning (true positive rate >80% before launching alerts)
- [ ] Training (analysts understand system limitations)

---

## Conclusion

**Critical pitfalls to obsess over:**
1. False positives eroding trust (test extensively)
2. Regulatory exposure (legal review)
3. Data pipeline brittleness (redundancy + monitoring)

**High-priority mitigations:**
- Extensive backtesting on known cases
- Multi-source data architecture
- Clear confidence tracking
- Conservative alert thresholds
- Comprehensive monitoring + alerting

**Success factor:** Analyst trust. Build it slowly with consistent, explainable signals. Lose it quickly with false positives.
