# 🧪 AI Clinical Data QC & Query Assistant

**A natural-language query interface and automated QC layer for CDISC ADaM clinical trial datasets — built to catch the class of derivation-logic errors that standard compliance tools like Pinnacle 21 miss.**


---

## The Problem

Two recurring bottlenecks in clinical statistical programming:

1. **Pinnacle 21 doesn't catch derivation-logic errors.** It validates CDISC structure and controlled terminology — not whether the underlying derivation logic is internally consistent. A treatment end date before the start date, a visit number that doesn't match its label, a duplicate sequence ID: all structurally valid, all still wrong, all typically caught manually (if caught at all).
2. **Ad hoc data questions bottleneck on programmer time.** Biostatisticians and medical writers need quick answers — *"how many subjects in the safety population had a Grade 3+ AE after Visit 4?"* — that otherwise require a programmer to write fresh SQL/SAS every time.

## What This Does

| Tab | What it does | Requires API key? |
|---|---|---|
| **✅ Data QC Dashboard** | Runs 7 rule-based checks against ADSL/ADAE for derivation-logic errors, with severity levels and flagged records | No — pure pandas |
| **💬 Ask a Question** | Translates a plain-English question into a pandas query, runs it, and returns a plain-English summary | Yes — free Gemini key |

## Example Queries

```
Which subjects discontinued due to an adverse event, and what was their treatment arm?
How many subjects in the safety population had a Grade 3+ AE after Visit 4?
Compare the number of serious adverse events across the three treatment arms.
What percentage of adverse events were considered related to treatment?
```

## The QC Checks

| ID | Check | Why P21 misses it |
|---|---|---|
| ADSL-01 | TRTEDT before TRTSDT | Structurally valid dates, just logically wrong order |
| ADSL-02 | SAFFL='Y' but TRTSDT missing | Cross-field consistency, not a CT/format rule |
| ADAE-01 | AVISITN doesn't match AVISIT label | Requires study-specific visit-map knowledge |
| ADAE-02 | Missing ASEQ | Breaks downstream TLF joins, not CDISC-invalid on its own |
| ADAE-03 | Duplicate ASEQ within subject | Uniqueness logic, not controlled terminology |
| ADAE-04 | AE start date after AE end date | Same class as ADSL-01 |
| ADAE-05 | ADAE USUBJID not in ADSL | Referential integrity across datasets |

Each check returns a `QCResult` (ID, description, severity, flagged records) — a single object the dashboard, a report generator, or an LLM summary layer can all consume.

## How the Natural-Language Layer Works

```
User question (plain English)
        │
        ▼
Gemini + ADSL/ADAE schema description
        │
        ▼
Single pandas expression (code only, no explanation)
        │
        ▼
Executed in a RESTRICTED namespace
(only adsl, adae, pd exposed — no builtins, no file/network access)
        │
        ▼
Result sent back to Gemini → plain-English summary
```

The restricted execution namespace is the safety boundary that matters here: a model-generated expression can query the two dataframes and nothing else — no file access, no imports, no network calls — regardless of what the generated code tries to do.

## Tech Stack

Python · pandas · Streamlit · Google Gemini API (free tier) · restricted code execution

## Project Structure

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

# run the full app
export GEMINI_API_KEY=...     
streamlit run app.py
```

The QC dashboard works immediately with no key. The NL query tab needs a free Gemini API key (no credit card, ~1,500 requests/day) from [Google AI Studio](https://aistudio.google.com/apikey).

## Data Note

All data is **synthetic**, generated with `data/generate_synthetic_adam.py` to mimic CDISC ADaM structure and naming conventions. No real patient data is used anywhere in this project. A handful of derivation errors are intentionally injected into the generated data so the QC layer has real issues to catch.

## Extending This Project

- Add ADLB/ADVS and build lab-shift-table or vital-signs-specific QC rules
- Swap the rule-based QC layer for LLM-assisted anomaly review — feed it flagged rows and ask for likely root causes
- Add a query-history log to surface which derivations biostatisticians ask about most
- Wire in real SQL generation for teams that want an actual query string, not a pandas expression

## Background

Built during my MSc in Applied Statistics and Analytics, informed by hands-on SDTM/ADaM development and Pinnacle 21 validation work during my statistical programming internship at Eli Lilly. This isn't a hypothetical business case — the QC checks reflect derivation-logic issues that come up in that pipeline.

---

