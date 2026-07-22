"""
qc_checks.py
---------------------------------
Rule-based QC layer for ADaM datasets (ADSL + ADAE).

These are DERIVATION-LOGIC checks — the kind Pinnacle 21 typically does
NOT catch, because P21 validates against CDISC compliance rules (variable
presence, controlled terminology, formats), not whether the underlying
derivation logic is internally consistent.

Each check function returns a pandas DataFrame of flagged rows plus a
plain-English explanation, so results can feed directly into the
Streamlit UI or into an LLM summary layer.
"""

from dataclasses import dataclass, field
import pandas as pd

# Canonical AVISITN -> AVISIT mapping used by this study.
# In a real pipeline this would be pulled from the study's define.xml.
VISIT_MAP = {1: "Baseline", 2: "Visit 2 (Week 4)", 3: "Visit 3 (Week 8)",
             4: "Visit 4 (Week 12)", 5: "Visit 5 (Week 16)", 6: "End of Study"}


@dataclass
class QCResult:
    check_id: str
    description: str
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    n_flagged: int
    flagged: pd.DataFrame = field(repr=False)


def check_trtdt_logic(adsl: pd.DataFrame) -> QCResult:
    """TRTEDT must not be before TRTSDT."""
    df = adsl.copy()
    df["TRTSDT_dt"] = pd.to_datetime(df["TRTSDT"], errors="coerce")
    df["TRTEDT_dt"] = pd.to_datetime(df["TRTEDT"], errors="coerce")
    bad = df[(df["TRTSDT_dt"].notna()) & (df["TRTEDT_dt"].notna()) &
             (df["TRTEDT_dt"] < df["TRTSDT_dt"])]
    return QCResult(
        check_id="ADSL-01",
        description="TRTEDT occurs before TRTSDT (treatment end date precedes start date)",
        severity="HIGH",
        n_flagged=len(bad),
        flagged=bad[["USUBJID", "TRTSDT", "TRTEDT"]],
    )


def check_saffl_consistency(adsl: pd.DataFrame) -> QCResult:
    """Subjects flagged SAFFL='N' but with TRT01A populated (or vice versa
    should be reviewed by a human), and SAFFL='Y' subjects with no treatment date."""
    df = adsl.copy()
    bad = df[(df["SAFFL"] == "Y") & (df["TRTSDT"].isna() | (df["TRTSDT"] == ""))]
    return QCResult(
        check_id="ADSL-02",
        description="SAFFL='Y' (in safety population) but TRTSDT is missing",
        severity="HIGH",
        n_flagged=len(bad),
        flagged=bad[["USUBJID", "SAFFL", "TRT01A", "TRTSDT"]],
    )


def check_avisit_consistency(adae: pd.DataFrame) -> QCResult:
    """AVISITN must map to the expected AVISIT text per the study's visit structure."""
    df = adae.copy()
    df["AVISITN_num"] = pd.to_numeric(df["AVISITN"], errors="coerce")
    df["EXPECTED_AVISIT"] = df["AVISITN_num"].map(VISIT_MAP)
    bad = df[df["AVISIT"] != df["EXPECTED_AVISIT"]]
    return QCResult(
        check_id="ADAE-01",
        description="AVISITN does not map to the expected AVISIT text for this study",
        severity="MEDIUM",
        n_flagged=len(bad),
        flagged=bad[["USUBJID", "AESEQ", "AVISITN", "AVISIT", "EXPECTED_AVISIT"]],
    )


def check_missing_aseq(adae: pd.DataFrame) -> QCResult:
    """ASEQ (analysis sequence) should never be missing — it's required for
    unique record identification in TLF programming."""
    bad = adae[adae["ASEQ"].isna()]
    return QCResult(
        check_id="ADAE-02",
        description="ASEQ is missing (breaks unique record identification for TLFs)",
        severity="HIGH",
        n_flagged=len(bad),
        flagged=bad[["USUBJID", "AESEQ", "AETERM", "ASEQ"]],
    )


def check_duplicate_aseq(adae: pd.DataFrame) -> QCResult:
    """ASEQ must be unique within USUBJID."""
    df = adae.dropna(subset=["ASEQ"])
    dupes = df[df.duplicated(subset=["USUBJID", "ASEQ"], keep=False)]
    return QCResult(
        check_id="ADAE-03",
        description="Duplicate ASEQ values within the same subject",
        severity="HIGH",
        n_flagged=len(dupes),
        flagged=dupes[["USUBJID", "AESEQ", "ASEQ", "AETERM"]].sort_values("USUBJID"),
    )


def check_ae_date_logic(adae: pd.DataFrame) -> QCResult:
    """AESTDTC (AE start) must not be after AEENDTC (AE end)."""
    df = adae.copy()
    df["ASTDT_dt"] = pd.to_datetime(df["ASTDT"], errors="coerce")
    df["AENDT_dt"] = pd.to_datetime(df["AENDT"], errors="coerce")
    bad = df[(df["ASTDT_dt"].notna()) & (df["AENDT_dt"].notna()) &
              (df["ASTDT_dt"] > df["AENDT_dt"])]
    return QCResult(
        check_id="ADAE-04",
        description="AE start date (ASTDT) occurs after AE end date (AENDT)",
        severity="HIGH",
        n_flagged=len(bad),
        flagged=bad[["USUBJID", "AESEQ", "ASTDT", "AENDT"]],
    )


def check_referential_integrity(adsl: pd.DataFrame, adae: pd.DataFrame) -> QCResult:
    """Every USUBJID in ADAE must exist in ADSL."""
    valid_ids = set(adsl["USUBJID"])
    bad = adae[~adae["USUBJID"].isin(valid_ids)]
    return QCResult(
        check_id="ADAE-05",
        description="USUBJID present in ADAE but not found in ADSL (referential integrity break)",
        severity="HIGH",
        n_flagged=len(bad),
        flagged=bad[["USUBJID", "AESEQ", "AETERM"]],
    )


def run_all_checks(adsl: pd.DataFrame, adae: pd.DataFrame) -> list[QCResult]:
    return [
        check_trtdt_logic(adsl),
        check_saffl_consistency(adsl),
        check_avisit_consistency(adae),
        check_missing_aseq(adae),
        check_duplicate_aseq(adae),
        check_ae_date_logic(adae),
        check_referential_integrity(adsl, adae),
    ]


def summarize_results(results: list[QCResult]) -> pd.DataFrame:
    return pd.DataFrame([
        {"Check ID": r.check_id, "Description": r.description,
         "Severity": r.severity, "Records Flagged": r.n_flagged}
        for r in results
    ])


if __name__ == "__main__":
    adsl = pd.read_csv("../data/adsl.csv", dtype=str)
    adae = pd.read_csv("../data/adae.csv", dtype=str)
    adae["ASEQ"] = pd.to_numeric(adae["ASEQ"], errors="coerce")

    results = run_all_checks(adsl, adae)
    summary = summarize_results(results)
    print(summary.to_string(index=False))
    print()
    for r in results:
        if r.n_flagged > 0:
            print(f"\n--- {r.check_id}: {r.description} ---")
            print(r.flagged.to_string(index=False))
