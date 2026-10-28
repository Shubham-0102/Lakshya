# Lakshya — Project Plan

Oct 28, 2026

## Overview

Lakshya is a personal AI job agent: it collects jobs from across the web, matches each one to your CV, alerts you to the right ones, and prepares a tailored application that you review and submit.

**Pitch:** "Upload your CV once. An AI agent watches every job in Nepal (and remote jobs abroad) and tells you which ones fit you, and why."

**The problem:** jobs are scattered across many portals, company websites and social posts. The same job appears in several places, salaries are often hidden, fake postings ask for fees, and job seekers waste hours checking sites and rewriting CVs.

**Three layers:**

1. **Collect:** a scraping agent gathers jobs, cleans them into one format and removes duplicates, and repairs itself when a website changes.
2. **Understand:** AI reads your CV, scores every job against it, explains the gaps, and flags suspicious postings.
3. **Act:** the agent sends alerts, prepares a tailored CV and cover letter, and tracks your applications. You always approve before anything is sent.

**Why it suits big-tech applications:** it combines real data engineering (scraping at scale, deduplication, scheduling), measurable AI (extraction accuracy, match quality, scam detection), an agent with human approval, and real users.

## Features

The MVP is collection, match scores and alerts; everything else builds on a working, trusted job feed.

**MVP (must ship)**

- [ ] Scrape jobs from at least 10 sources on a schedule (job portals, company career pages, remote job feeds)
- [ ] Clean every job into one format: title, company, location, salary, experience, skills, deadline, source link
- [ ] Remove duplicates, so the same job posted on several sites appears once
- [ ] Self-healing scrapers that re-learn a page when its layout changes
- [ ] Search and filter jobs on a web app
- [ ] Upload a CV once; the AI builds your profile
- [ ] Match score for each job with reasons ("82% match: you have Python and FastAPI, missing Docker")
- [ ] Alerts on Telegram and email for new jobs above your chosen match score

**Later (after the MVP has real users)**

- [ ] Tailored application kit: CV highlights and a cover letter rewritten for each job
- [ ] Application tracker with statuses, deadlines and follow-up reminders
- [ ] Scam flags for suspicious postings (upfront fees, no company details, unrealistic pay)
- [ ] Skill-gap insights from the market ("40% of AI jobs this month ask for Docker")
- [ ] Salary insights by role and experience, from real postings
- [ ] Interview practice questions generated from the job description
- [ ] Nepali-language search and alerts

## How it works

The top row runs on a schedule for everyone; the bottom row runs for each user whenever new jobs arrive.

**Collection pipeline (scheduled):**
Job sites (portals, career pages) → Scraper agent (learns once, reuses; self-heals when a layout changes) → Clean + dedupe (one format, no copies) → Jobs database (Postgres + pgvector)

**Per-user pipeline:**
Your CV (uploaded once) → Matcher (scores every new job from the Jobs database) → Alerts + application kit (Telegram, tailored CV) → You review and submit

Matching happens in two steps: embeddings quickly shortlist likely jobs, then the LLM scores the shortlist and explains the reasons and missing skills.

## Data sources and scraping rules

Start with a few sources you can scrape reliably and legally, then grow; the scraping rules below are part of the design, not an afterthought.

**Sources to start with**

| Source type | Examples | How to collect |
| --- | --- | --- |
| Nepali job portals | Large local portals such as merojob, jobsnepal and kumarijob (check each one's terms first) | Scraping agent, gently and on a schedule |
| Company career pages | Nepali tech companies, banks, NGOs, international organizations with Kathmandu offices | Scraping agent; the AI learns each page layout |
| Remote job boards | International boards that publish official feeds or APIs | Use the feed or API instead of scraping |
| Partnerships | Portals or companies willing to share listings | Ask; a data agreement beats scraping |

**How the scraping agent works**

1. The first time it sees a page, the AI works out where the job data is and saves a reusable "recipe" (which elements hold the title, salary, deadline, and so on).
2. Every later run uses the saved recipe with plain code, with no AI call, so daily scraping costs almost nothing.
3. If the recipe stops working (missing fields, zero jobs found), the agent re-learns the page with AI and saves a new recipe. That is the self-healing.
4. Every job is cleaned into one format, checked for duplicates, and stored with a link back to the original posting.

**Scraping rules (never break these)**

- Respect each site's `robots.txt` and terms of service; skip sites that forbid scraping and ask them instead.
- Go slowly: at most one request every few seconds per site, and only during scheduled runs.
- Identify your scraper honestly in its user agent.
- Show a short summary and send users to the original posting to apply. This sends traffic back to the source site rather than copying it.
- Never collect personal data beyond what a public job posting contains.

## Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | Next.js (React) + TypeScript + Tailwind | Job search, profile, matches and tracker pages |
| Backend API | FastAPI (Python) | Known well; async support |
| Database | PostgreSQL + pgvector | Jobs, users and matches in one place; vector search for matching |
| Scheduling and jobs | Redis + Celery (Celery Beat for schedules) | Runs scrapers on a timetable and processes jobs in the background |
| Browsing | Playwright | Opens pages like a real browser, including JavaScript-heavy sites |
| Extraction | Own AI extraction step that produces reusable recipes | The self-healing logic is the strongest interview story |
| LLM | Any model API with structured output, behind one small wrapper | Extraction, CV parsing, match explanations, cover letters |
| Embeddings | An embedding model for jobs and CVs | Fast first-pass matching before the LLM explains the score |
| Alerts | Telegram Bot API and an email service | Where students actually see notifications |
| Deployment | Docker Compose on a small cloud server; frontend on Vercel | A live link for the CV |
| Tracing | Langfuse or OpenTelemetry, plus structured logs | Tracks every scrape, AI call, cost and failure |

## Data model

| Table | What it stores | Key fields |
| --- | --- | --- |
| `sources` | Every website the scraper visits | url, type, saved extraction recipe, last success, health status, failure count |
| `jobs` | One row per unique job | title, company, location, salary range, experience, skills, deadline, description summary, source links, first seen, last seen, scam score, embedding |
| `companies` | Employers, merged across sources | name, website, verified flag |
| `users` | Accounts and preferences | email, Telegram id, alert threshold, preferred locations |
| `profiles` | What the AI learned from each CV | skills, experience years, education, embedding |
| `matches` | Score of each job for each user | user, job, score, reasons, missing skills, alerted flag |
| `applications` | The user's tracker | user, job, status, applied date, follow-up date, notes |

Duplicates are caught by comparing company, title, location and description similarity; a job seen on several sites keeps one row with several source links.

## Build timeline

About 16 weeks at 8–10 hours a week, with real users from week 9. Don't start a phase until the previous gate is met.

1. **Weeks 1–3, Scraping basics:** repo, Docker Compose, database, and hand-written scrapers for 3 sources with cleaning and scheduled runs.
2. **Weeks 4–6, Smart scraping:** AI extraction that saves reusable recipes, self-healing, deduplication, and 10+ sources. **Gate:** 1,000+ clean jobs.
3. **Weeks 7–9, Matching:** CV upload and parsing, embeddings, LLM match scores with reasons, and Telegram alerts. **Gate:** 20 classmates using it.
4. **Weeks 10–12, Web app:** job search and filters, profile page, matches page and the application tracker.
5. **Weeks 13–16, Agent + launch:** tailored CV and cover letter kit, scam flags, evaluation runs, deployment and demo video. **Gate:** 100+ users and real numbers for the CV.

## Metrics to measure

| Metric | How you measure it | Suggested target |
| --- | --- | --- |
| Coverage | Active jobs and sources in the database | 1,000+ jobs from 10+ sources |
| Extraction accuracy | Fields correct in a hand-checked sample of 200 jobs | 95% or more |
| Duplicate rate | Duplicate jobs shown ÷ jobs shown | Under 3% |
| Self-heal rate | Broken scrapers fixed automatically ÷ all breakages | Report the real number |
| Cost per job | AI cost to process one new job | Report the real number |
| Match quality | Correct ranking on a labelled set of CVs and jobs; users' thumbs up | Report the real number |
| Scam detection | Precision and recall on a labelled set of real and fake postings | Report the real number |
| Real usage | Weekly active users and alerts clicked | 100+ users by week 16 |

Build the hand-checked samples early and rerun them after every change to prompts or recipes.

## CV bullets and interview talking points

**Lakshya — AI job agent** | Next.js, FastAPI, PostgreSQL + pgvector, Redis, Celery, Playwright, LLMs

- Built a self-healing scraping agent that collects [N]+ jobs from [N] sources, reusing AI-learned extraction recipes to cut processing cost to [X] per job, with [Y]% field accuracy
- Designed CV-to-job matching with embeddings and LLM explanations, delivering personalised alerts to [N]+ active users via Telegram and email
- Implemented deduplication across sources (under [X]% duplicates) and a scam-posting classifier with [Y]% precision on a labelled set

**Questions interviewers will likely ask:**

1. How does the scraper detect that a site changed, and how does it repair itself?
2. Why not call the LLM on every page? What did reusable recipes save?
3. How do you decide two postings are the same job?
4. How does matching work, and how did you measure whether it is good?
5. How do you scrape responsibly? What would you do if a site asked you to stop?
6. How would this scale to every job in South Asia?

## Risks, privacy rules and tips

**Privacy rules for users' CVs**

- Store CVs encrypted, never share them, and delete everything when a user asks.
- Send CV text to the AI model only for the user's own matching, and say so clearly in the app.
- Never submit an application or contact an employer without the user's approval.

**Risks and how to handle them**

| Risk | What to do |
| --- | --- |
| A site blocks scraping or forbids it | Respect it, drop or pause that source, and ask for a partnership |
| Extraction errors make the feed untrustworthy | Hand-checked accuracy samples, a "report a problem" button, and a link to the original posting |
| Scam flags wrongly accuse a real employer | Word them as "possible risks", explain the reasons, and let users report mistakes |
| AI costs grow with more jobs | Reusable recipes, embeddings for first-pass matching, and AI only for top matches |
| Too few users | Launch to your class and college clubs by week 9; collect feedback weekly |

**Tips**

- Use the product yourself for your own internship search.
- Write the extraction and self-healing logic yourself; that is the part interviewers will dig into.
- Record a 2-minute demo video for the GitHub README.
- Keep this fully separate from internship work: own time, code and data.
