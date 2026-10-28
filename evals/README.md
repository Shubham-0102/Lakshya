# Evals

Hand-checked samples and evaluation scripts. Every change to prompts, recipes or matching is re-run against these.

Planned contents, each added in the phase that needs it:

| Eval | Measures | Phase |
| --- | --- | --- |
| Extraction accuracy | Fields correct in a hand-checked sample of 200 jobs (target: 95%+) | 2 |
| Duplicate rate | Duplicate jobs shown ÷ jobs shown (target: under 3%) | 2 |
| Self-heal rate | Broken scrapers fixed automatically ÷ all breakages | 2 |
| Match quality | Ranking on a labelled set of CVs and jobs | 3 |
| Scam detection | Precision and recall on labelled real and fake postings | 5 |

Empty in Phase 1: this folder becomes a Python package when the first eval script is written.
