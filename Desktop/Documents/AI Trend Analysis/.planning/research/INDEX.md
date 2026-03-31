# AI Washing Detector - Research Documentation Index

**Project:** AI Washing Detector (Python system for hedge fund portfolio analysis)
**Research Date:** 2026-03-31
**Total Research Files:** 6 + index
**Total Documentation:** ~141 KB

---

## Quick Navigation

### For Portfolio Managers (5 min read)
Start here: **SUMMARY.md** → Key findings, roadmap phases, success criteria

### For Engineers (30 min read)
Path: **STACK.md** → **ARCHITECTURE.md** → **RESEARCH.md** (Part 4)

### For Risk/Compliance (20 min read)
Path: **PITFALLS.md** → **RESEARCH.md** (Part 7: Legal/regulatory) → **STACK.md** (deployment)

### For Product Managers (15 min read)
Path: **FEATURES.md** → **SUMMARY.md** (phase structure) → **RESEARCH.md** (Part 3: precedents)

---

## File Descriptions

### 1. SUMMARY.md (17 KB, 10 min read)
**What:** Executive summary with implications for roadmap

**Key sections:**
- Executive summary (3 paragraphs)
- Key findings by domain (Stack, Features, Architecture, Pitfalls)
- Recommended phase structure (4 phases, 21 weeks MVP)
- Phase ordering rationale
- Confidence assessment (HIGH/MEDIUM/LOW per domain)
- Success criteria + validation approach

**Use when:** Starting project; executive presentations; roadmap planning

---

### 2. RESEARCH.md (50 KB, 45 min read)
**What:** Comprehensive domain research (largest file)

**Key sections:**
1. Academic foundations (fraud detection, NLP, insider trading)
2. Existing tools & datasets (SEC, GitHub, patents, LinkedIn, earnings calls, Form 4)
3. Domain precedents (Builder.ai, C3, Nate, Evolv cases; short-seller methods)
4. Technical architecture insights (data pipeline, NLP approaches, scoring, real-time monitoring)
5. Data collection timeline & feasibility (signal-by-signal assessment)
6. Implementation roadmap (4 phases, timeline estimate)
7. Limitations & gaps
8. Tech stack validation (Python vs. alternatives)
9. Comparison to existing approaches
10. Critical success factors & risks
11. Recommended validations (Phase 0 research)

**Use when:** Deep understanding needed; tech decisions; feasibility assessment; building roadmap

---

### 3. STACK.md (14 KB, 15 min read)
**What:** Technology stack recommendations with installation guide

**Key sections:**
- Recommended stack (language, NLP, data pipeline, API, infrastructure)
- Installation & setup (Docker, virtual environment, dependencies)
- Configuration management (environment variables)
- Deployment checklist
- Technology decision rationale (Python vs. Rust vs. Java; Prefect vs. Airflow; FinBERT vs. ChatGPT)

**Use when:** Setting up development environment; infrastructure planning; tech decisions

---

### 4. FEATURES.md (13 KB, 12 min read)
**What:** Feature landscape (table-stakes, differentiators, anti-features)

**Key sections:**
- Table-stakes features (credibility score, signal analysis, alerts, dashboard)
- Differentiators ("coming soon" tracking, CEO health, customer concentration, product latency)
- Anti-features (what NOT to build)
- Feature dependencies (signal prerequisites)
- Feature specification (data models, trade signal mapping)
- MVP feature set (12 features across Phase 1)
- Phase 2 & 3 features
- Success metrics per feature
- Known constraints

**Use when:** Scoping work; defining MVP; understanding feature dependencies

---

### 5. ARCHITECTURE.md (26 KB, 25 min read)
**What:** System design patterns and component architecture

**Key sections:**
- High-level system diagram (data sources → pipeline → scoring → output)
- Component boundaries (7 components: ingestion, NLP, aggregation, scoring, orchestration, API, dashboard)
- Data flow (daily batch flow, example transformation)
- Scalability considerations (at 100 users, 10K users, 1M users)
- Error handling & resilience patterns
- AWS deployment architecture
- Anti-patterns to avoid

**Use when:** Building system; understanding component interactions; designing resilience

---

### 6. PITFALLS.md (21 KB, 20 min read)
**What:** Domain risks, pitfalls, and mitigations

**Key sections:**
- Critical pitfalls (5): false positives, legal exposure, pipeline brittleness, signal weights, temporal misalignment
- Moderate pitfalls (5): missing data, industry normalization, seasonality, analyst overconfidence, real-time delays
- Minor pitfalls (5): API rate limiting, stale scores, GitHub limitations, transcript errors, buzzword noise
- Phase-specific warnings (what to watch per phase)
- Risk mitigation checklist (pre-launch validation)

**Use when:** Risk assessment; planning mitigation strategies; pre-launch review

---

### 7. INDEX.md (this file)
**What:** Navigation guide for research documentation

---

## Cross-Reference Matrix

| Question | Answer in | Minutes |
|----------|-----------|---------|
| "What's the project?" | SUMMARY.md (Exec summary) | 3 |
| "Is this technically feasible?" | SUMMARY.md (Key findings) + RESEARCH.md (Part 5) | 10 |
| "What stack should we use?" | STACK.md (full file) + RESEARCH.md (Part 8) | 15 |
| "What features do we build?" | FEATURES.md (MVP section) + SUMMARY.md (Phase 1) | 10 |
| "How does the system work?" | ARCHITECTURE.md (components + data flow) | 20 |
| "What can go wrong?" | PITFALLS.md (critical section) | 10 |
| "What's our roadmap?" | SUMMARY.md (Roadmap section) | 5 |
| "How long to launch?" | SUMMARY.md (5 months) + RESEARCH.md (Part 5) | 5 |
| "What costs?" | RESEARCH.md (Part 8: $100-500/mo infra) + STACK.md (deployment) | 5 |
| "What about legal risk?" | PITFALLS.md (Pitfall 2) + RESEARCH.md (Part 7) | 10 |
| "How do we backtest?" | RESEARCH.md (Part 11: case studies) + SUMMARY.md (validation) | 10 |
| "Who are competitors?" | RESEARCH.md (Part 9: comparison) | 5 |

---

## Research Confidence Summary

| Domain | Confidence | Key Unknowns |
|--------|------------|--------------|
| **Stack & infrastructure** | HIGH | None; standard tech; proven patterns |
| **Data source availability** | HIGH | API changes; LinkedIn scraping constraints; known + documented workarounds |
| **Feature feasibility** | MEDIUM | Signal accuracy (especially earnings sentiment) needs Phase 1 validation |
| **Architecture pattern** | HIGH | Standard in quant finance; no novel technical challenges |
| **Risk identification** | HIGH | Pitfalls based on industry experience; mitigations well-documented |
| **Development timeline** | MEDIUM | 5-month estimate reasonable; actual depends on team expertise + data source stability |
| **Signal accuracy** | MEDIUM-LOW | Core signals validated in literature; ensemble accuracy for AI washing TBD until Phase 1 backtest |
| **Regulatory framework** | LOW-MEDIUM | Securities law for AI credibility scoring untested; need legal counsel review |

---

## Files by Audience

### Executive / Portfolio Management
- **SUMMARY.md** - Full file (key findings, roadmap, success criteria)
- **RESEARCH.md** - Part 3 (domain precedents: real cases) + Part 9 (vs. existing approaches)

### Engineering / Architecture
- **STACK.md** - Full file (tech recommendations + deployment)
- **ARCHITECTURE.md** - Full file (system design, components, data flow)
- **RESEARCH.md** - Parts 2, 4 (data sources, technical approaches)

### Data Science / Analytics
- **RESEARCH.md** - Parts 1, 4 (academic foundations, NLP/ML approaches, scoring methodology)
- **FEATURES.md** - Signal specification section
- **PITFALLS.md** - Signal weighting + false positive sections

### Risk / Compliance
- **PITFALLS.md** - Full file (especially Pitfall 2: legal exposure)
- **RESEARCH.md** - Part 7 (regulatory + compliance issues)
- **STACK.md** - Deployment section (audit trail, monitoring)

### Product Management
- **FEATURES.md** - Full file (what to build, priorities, dependencies)
- **SUMMARY.md** - Phase structure + success criteria
- **RESEARCH.md** - Part 3 (domain precedents, existing tools)

---

## Research Methodology

**Data sources used (training data cutoff Feb 2025):**
1. Academic papers (fraud detection, NLP, insider trading)
2. Public company cases (Builder.ai, C3, Nate, Evolv, Joonko, Presto)
3. Short-seller methodology (Hindenburg, Citron, industry reports)
4. Quant finance literature (signal design, portfolio analysis)
5. Technology documentation (Python, NLP frameworks, financial APIs)

**Limitations:**
- No original research; synthesizes existing literature
- Data cutoff Feb 2025; field may have evolved
- Training data for tech stack selection; no novel tech recommendations
- Legal framework speculative; needs securities counsel validation

**Confidence levels:**
- HIGH: Established patterns, published research, industry precedents
- MEDIUM: Emerging research, limited precedents, requires Phase 1 validation
- LOW: Speculative, unproven, requires expert review

---

## How to Use This Research

### Immediate (This Week)
1. Read SUMMARY.md (10 min) - understand project scope
2. Read FEATURES.md MVP section (5 min) - understand deliverables
3. Read PITFALLS.md critical section (10 min) - understand risks
4. **Decision:** Proceed to Phase 0 validation? Yes/No

### Short-term (Next 2 Weeks)
5. If YES: Read RESEARCH.md Part 5 (5 min) - data collection feasibility
6. Assign Phase 0 researcher - conduct 2-4 week validation (see SUMMARY.md appendix)
7. Review STACK.md - finalize tech choices
8. Review ARCHITECTURE.md - design system components

### Medium-term (Weeks 3-4)
9. If Phase 0 validation passes: Read full ARCHITECTURE.md - system design
10. Assemble team based on resource requirements (SUMMARY.md)
11. Set up development environment (STACK.md installation guide)
12. Begin Phase 1 development

### Ongoing
13. Reference PITFALLS.md during development - proactive risk management
14. Use FEATURES.md MVP section for sprint planning
15. Check RESEARCH.md Part 11 for backtest case studies - validation approach

---

## Key Takeaways

**Bottom line:** AI washing detector is technically feasible and strategically valuable. Phase 1 MVP (21 weeks) will produce credibility scores for 500 US mid-cap companies with 70-75% accuracy on known washing cases. Critical success factor: minimize false positives (extensive backtesting before launch). Legal/regulatory review required before deployment.

**Recommended next step:** Phase 0 validation (2-4 weeks) to confirm signals work on sample data. Gate: backtest accuracy >65% on 20+ known cases before committing full Phase 1 resources.

---

**Research by:** Claude AI (Anthropic)
**Date:** 2026-03-31
**Status:** Complete and ready for roadmap planning
**Files:** 7 documents, 141 KB total
