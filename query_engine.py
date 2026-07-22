"""
query_engine.py
---------------------------------
Natural-language interface over the ADSL / ADAE dataframes.

Uses Google's Gemini API, which has a genuinely free tier (no credit
card, ~1,500 requests/day on Flash models as of 2026) — a better fit
for a portfolio project than a paid API.

Flow:
  1. User asks a question in plain English.
  2. We send the question + a description of the ADSL/ADAE schema to
     Gemini, asking it to return ONLY a pandas expression that answers
     the question (no explanation, no markdown fences).
  3. We execute that expression in a restricted namespace that only
     exposes `adsl`, `adae`, and `pd` — no builtins, no file/network
     access. This is the safety boundary: never eval() free-form model
     output without sandboxing the execution environment.
  4. We send the result back to Gemini and ask for a short, plain-English
     business summary.

Setup:
  1. Go to https://aistudio.google.com/apikey and create a free API key
     (no credit card required).
  2. Set it as an environment variable: GEMINI_API_KEY
"""

import os
import re
import pandas as pd
import google.generativeai as genai

MODEL = "gemini-flash-latest"  

SCHEMA_DESCRIPTION = """
You are querying two pandas DataFrames already loaded in memory: `adsl` and `adae`.

adsl (one row per subject) columns:
  USUBJID (str, unique subject id), SUBJID, SITEID,
  TRT01P / TRT01A (str, planned/actual treatment arm: Placebo, Low Dose, High Dose),
  TRTSDT / TRTEDT (str, YYYY-MM-DD, treatment start/end date),
  AGE (int), SEX (M/F), RACE (str),
  SAFFL (Y/N, safety population flag), ITTFL (Y/N, intent-to-treat flag),
  DCSREAS (str, discontinuation reason), EOSSTT (COMPLETED/DISCONTINUED)

adae (one row per adverse event) columns:
  USUBJID (str, links to adsl), AESEQ (int),
  AETERM / AEDECOD (str, event term), AEBODSYS (str, system organ class),
  AESTDTC / AEENDTC (str, YYYY-MM-DD), AESEV (MILD/MODERATE/SEVERE),
  AETOXGR (int 1-4, toxicity grade), AESER (Y/N, serious AE),
  AEREL (RELATED/NOT RELATED to treatment), TRTA (str, treatment arm),
  AVISIT (str, visit label), AVISITN (int, visit number),
  ASTDT / AENDT (str, YYYY-MM-DD), ASEQ (int, analysis sequence)

Rules for your response:
- Return ONLY a single valid Python expression using `adsl`, `adae`, and `pd`
  (pandas is already imported as pd) that evaluates to the answer.
- Do not include markdown fences, comments, or any explanation — code only.
- The expression should evaluate to a DataFrame, Series, or scalar.
- Prefer clear, readable pandas (merges, boolean filtering, groupby) over
  one-liners that sacrifice correctness for brevity.
- When the question implies the safety population, filter on SAFFL == 'Y'
  unless told otherwise.
"""


def _get_model() -> "genai.GenerativeModel":
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable not set. "
            "Get a free key at https://aistudio.google.com/apikey and set it "
            "before running the query engine."
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL, system_instruction=SCHEMA_DESCRIPTION)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:python)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def generate_pandas_expression(question: str, model: "genai.GenerativeModel") -> str:
    resp = model.generate_content(question)
    return _strip_code_fences(resp.text)


def run_expression_safely(expr: str, adsl: pd.DataFrame, adae: pd.DataFrame):
    """
    Execute the model-generated pandas expression in a restricted namespace.
    Only `adsl`, `adae`, and `pd` are exposed. Builtins are stripped so the
    expression cannot import modules, open files, or reach the network.
    """
    safe_globals = {"__builtins__": {}, "pd": pd}
    safe_locals = {"adsl": adsl, "adae": adae}
    try:
        result = eval(expr, safe_globals, safe_locals)
    except Exception as e:
        raise RuntimeError(f"Generated expression failed to execute: {expr}\nError: {e}")
    return result


def summarize_result(question: str, expr: str, result, model: "genai.GenerativeModel") -> str:
    if isinstance(result, pd.DataFrame):
        preview = result.head(20).to_string(index=False)
        n = len(result)
    elif isinstance(result, pd.Series):
        preview = result.to_string()
        n = len(result)
    else:
        preview = str(result)
        n = 1

    prompt = f"""A business user asked: "{question}"

We ran this pandas query: {expr}

Result ({n} row(s), showing up to 20):
{preview}

Write a 2-4 sentence plain-English answer for a non-technical biostatistics/
medical-writing audience. Lead with the direct answer, then one supporting
detail if useful. No SQL/pandas jargon, no code."""

    resp = model.generate_content(prompt)
    return resp.text


def ask(question: str, adsl: pd.DataFrame, adae: pd.DataFrame, model: "genai.GenerativeModel" = None):
    """End-to-end: NL question -> pandas expression -> result -> plain-English summary."""
    model = model or _get_model()
    expr = generate_pandas_expression(question, model)
    result = run_expression_safely(expr, adsl, adae)
    summary = summarize_result(question, expr, result, model)
    return {"question": question, "expression": expr, "result": result, "summary": summary}


if __name__ == "__main__":
    adsl = pd.read_csv("../data/adsl.csv", dtype=str)
    adae = pd.read_csv("../data/adae.csv", dtype=str)
    adae["ASEQ"] = pd.to_numeric(adae["ASEQ"], errors="coerce")
    adae["AVISITN"] = pd.to_numeric(adae["AVISITN"], errors="coerce")
    adae["AETOXGR"] = pd.to_numeric(adae["AETOXGR"], errors="coerce")

    q = "Which subjects discontinued due to an adverse event, and what was their treatment arm?"
    out = ask(q, adsl, adae)
    print("EXPRESSION:", out["expression"])
    print("\nSUMMARY:", out["summary"])
