# AI Clinical Data QC & Query Assistant

A portfolio project for statistical programming / clinical data analyst roles.
It demonstrates natural-language querying over ADaM datasets and an
AI-augmented QC layer that catches **derivation-logic errors** —
the class of issues that standard CDISC compliance tools (e.g. Pinnacle 21)
typically don't catch, because P21 checks structure and controlled
terminology, not whether the derivation logic is internally consistent.

## Business problem this solves

1. Statistical programmers spend significant time manually cross-checking
   SDTM/ADaM datasets for derivation-logic issues that pass P21 but are
   still wrong (e.g. a treatment end date before the start date, an
   AVISITN that doesn't match its AVISIT label, duplicate ASEQ values).
2. Biostatisticians and medical writers routinely have ad hoc questions
   about the data ("how many subjects in the safety population had a
   Grade 3+ AE after Visit 4?") that require a programmer to write fresh
   SAS/SQL every time.

This project addresses both with one lightweight tool.

## Project structure

```
clinical-ai-assistant/
├── data/
│   └── generate_synthetic_adam.py   # builds synthetic adsl.csv / adae.csv
├── qc/
│   └── qc_checks.py                 # 7 derivation-logic QC rules
├── nl/
│   └── query_engine.py              # NL question -> pandas -> plain-English answer
├── app.py                           # Streamlit front end (2 tabs)
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt

# regenerate the synthetic data (already included, but reproducible)
python data/generate_synthetic_adam.py

# run the QC checks standalone
python qc/qc_checks.py

# run the full app (needs a free Gemini API key for the NL tab)
export GEMINI_API_KEY=...
streamlit run app.py
```

The QC dashboard tab works with **no API key** — it's pure pandas rule
logic. The natural-language query tab requires `GEMINI_API_KEY`, which
you can get for free (no credit card) at https://aistudio.google.com/apikey.
The free tier covers ~1,500 requests/day on Gemini Flash models, more
than enough for demoing this project.

## How the natural-language layer works

1. The user's question + a description of the ADSL/ADAE schema is sent to
   Gemini, which returns a single pandas expression (no explanation).
2. That expression is executed in a **restricted namespace** — only
   `adsl`, `adae`, and `pd` are exposed, and builtins are stripped. This
   is the safety boundary that keeps a model-generated expression from
   doing anything beyond querying the two dataframes.
3. The result is sent back to Gemini with a second prompt asking for a
   short, plain-English summary aimed at a non-technical audience
   (biostatisticians / medical writers), not a programmer.

## The QC checks (qc/qc_checks.py)

| ID | Check | Why P21 misses it |
|---|---|---|
| ADSL-01 | TRTEDT before TRTSDT | Structurally valid dates, just logically wrong order |
| ADSL-02 | SAFFL='Y' but TRTSDT missing | Cross-field consistency, not a CT/format rule |
| ADAE-01 | AVISITN doesn't match AVISIT label | Requires study-specific visit-map knowledge |
| ADAE-02 | Missing ASEQ | Only breaks downstream TLF joins, not CDISC-invalid on its own |
| ADAE-03 | Duplicate ASEQ within subject | Uniqueness logic, not controlled terminology |
| ADAE-04 | AE start date after AE end date | Same class as ADSL-01 |
| ADAE-05 | ADAE USUBJID not in ADSL | Referential integrity across datasets |

Each function returns a `QCResult` (check ID, description, severity,
flagged records) so the dashboard, a report generator, or an LLM summary
layer can all consume the same object.

## Extending this project

- Add ADLB/ADVS and build lab-shift-table or vital-signs-specific QC rules
- Swap the rule-based QC layer for an LLM-assisted anomaly review: feed
  it a sample of derivation code + the flagged rows and ask it to suggest
  root causes
- Add a "query history" log so repeated ad hoc questions from
  biostatisticians reveal which derivations are consistently confusing
- Wire in real SQL generation (SQLite) for teams that want an actual
  query string instead of a pandas expression

## Talking points for interviews

- "Pinnacle 21 validates CDISC compliance rules — I built a layer for the
  derivation-logic issues that sit outside what P21 checks."
- "The safety boundary in the NL layer is the restricted eval namespace —
  I don't let a model-generated expression touch anything except the two
  dataframes."
- "I generated synthetic data with intentionally injected errors so the
  QC layer has something real to catch — this mirrors how you'd validate
  a QC tool before trusting it on real study data."
