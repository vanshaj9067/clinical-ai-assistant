"""
generate_synthetic_adam.py
---------------------------------
Generates synthetic ADSL (Subject-Level) and ADAE (Adverse Events)
ADaM-like datasets for the AI Clinical Data QC & Query Assistant.

This is NOT real patient data. It mimics the structure and variable
naming conventions of CDISC ADaM (ADSL/ADAE) so the QC and NL-query
layers have something realistic to work against. A handful of rows
have intentionally broken derivation logic injected (see comments
marked "INJECTED ERROR") so the QC module has real issues to catch.

Run:
    python generate_synthetic_adam.py
Produces:
    adsl.csv, adae.csv  (written to the same folder)
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random

random.seed(42)
np.random.seed(42)

N_SUBJECTS = 120
TRT_ARMS = ["Placebo", "Low Dose", "High Dose"]
SITES = [f"S{str(i).zfill(3)}" for i in range(1, 9)]
RACES = ["WHITE", "BLACK OR AFRICAN AMERICAN", "ASIAN", "OTHER"]
DC_REASONS = ["COMPLETED", "ADVERSE EVENT", "WITHDREW CONSENT",
              "LOST TO FOLLOW-UP", "PROTOCOL DEVIATION", "DEATH"]

AE_TERMS = [
    ("Headache", "Nervous system disorders"),
    ("Nausea", "Gastrointestinal disorders"),
    ("Fatigue", "General disorders"),
    ("Rash", "Skin and subcutaneous tissue disorders"),
    ("Elevated liver enzymes", "Investigations"),
    ("Diarrhoea", "Gastrointestinal disorders"),
    ("Dizziness", "Nervous system disorders"),
    ("Insomnia", "Psychiatric disorders"),
    ("Neutropenia", "Blood and lymphatic system disorders"),
    ("Hypertension", "Vascular disorders"),
]

VISIT_MAP = {1: "Baseline", 2: "Visit 2 (Week 4)", 3: "Visit 3 (Week 8)",
             4: "Visit 4 (Week 12)", 5: "Visit 5 (Week 16)", 6: "End of Study"}


def gen_adsl():
    rows = []
    study_start = datetime(2024, 1, 1)
    for i in range(1, N_SUBJECTS + 1):
        usubjid = f"STUDY01-{str(i).zfill(4)}"
        subjid = str(i).zfill(4)
        site = random.choice(SITES)
        trt = random.choices(TRT_ARMS, weights=[0.34, 0.33, 0.33])[0]
        age = int(np.clip(np.random.normal(52, 14), 18, 89))
        sex = random.choice(["M", "F"])
        race = random.choices(RACES, weights=[0.55, 0.2, 0.15, 0.1])[0]

        trtsdt = study_start + timedelta(days=random.randint(0, 400))
        duration = random.randint(28, 168)
        trtedt = trtsdt + timedelta(days=duration)

        dcsreas = random.choices(
            DC_REASONS, weights=[0.65, 0.12, 0.08, 0.05, 0.06, 0.04]
        )[0]
        eosstt = "COMPLETED" if dcsreas == "COMPLETED" else "DISCONTINUED"

        saffl = "Y" if random.random() > 0.03 else "N"   # ~3% not in safety pop
        ittfl = "Y" if random.random() > 0.02 else "N"

        rows.append({
            "USUBJID": usubjid, "SUBJID": subjid, "SITEID": site,
            "TRT01P": trt, "TRT01A": trt,
            "TRTSDT": trtsdt.strftime("%Y-%m-%d"),
            "TRTEDT": trtedt.strftime("%Y-%m-%d"),
            "AGE": age, "SEX": sex, "RACE": race,
            "SAFFL": saffl, "ITTFL": ittfl,
            "DCSREAS": dcsreas, "EOSSTT": eosstt,
        })

    df = pd.DataFrame(rows)

    # INJECTED ERROR 1: a few subjects have TRTEDT before TRTSDT
    # (classic derivation-logic bug: date fields swapped upstream)
    bad_idx = df.sample(3, random_state=1).index
    df.loc[bad_idx, ["TRTSDT", "TRTEDT"]] = df.loc[bad_idx, ["TRTEDT", "TRTSDT"]].values

    # INJECTED ERROR 2: a couple of subjects have TRT01A populated but SAFFL = 'N'
    # with no treatment date — inconsistent safety population flagging
    bad_idx2 = df.sample(2, random_state=2).index
    df.loc[bad_idx2, "SAFFL"] = "N"
    df.loc[bad_idx2, "TRTSDT"] = ""
    df.loc[bad_idx2, "TRTEDT"] = ""

    return df


def gen_adae(adsl: pd.DataFrame):
    rows = []
    ae_seq_counter = {}

    for _, subj in adsl.iterrows():
        n_ae = np.random.poisson(1.8)
        for _ in range(n_ae):
            usubjid = subj["USUBJID"]
            ae_seq_counter.setdefault(usubjid, 0)
            ae_seq_counter[usubjid] += 1
            aeseq = ae_seq_counter[usubjid]

            term, soc = random.choice(AE_TERMS)
            sev = random.choices(["MILD", "MODERATE", "SEVERE"], weights=[0.55, 0.33, 0.12])[0]
            grade = {"MILD": 1, "MODERATE": random.choice([2, 3]), "SEVERE": random.choice([3, 4])}[sev]
            aeser = "Y" if grade >= 3 and random.random() < 0.3 else "N"
            aerel = random.choices(["RELATED", "NOT RELATED"], weights=[0.4, 0.6])[0]

            try:
                trtsdt = datetime.strptime(subj["TRTSDT"], "%Y-%m-%d") if subj["TRTSDT"] else datetime(2024, 1, 1)
            except ValueError:
                trtsdt = datetime(2024, 1, 1)

            astdt = trtsdt + timedelta(days=random.randint(1, 150))
            aendt = astdt + timedelta(days=random.randint(0, 14))

            visitn = random.randint(1, 6)
            visit = VISIT_MAP[visitn]

            rows.append({
                "USUBJID": usubjid, "AESEQ": aeseq,
                "AETERM": term, "AEDECOD": term.upper(), "AEBODSYS": soc,
                "AESTDTC": astdt.strftime("%Y-%m-%d"), "AEENDTC": aendt.strftime("%Y-%m-%d"),
                "AESEV": sev, "AETOXGR": grade, "AESER": aeser, "AEREL": aerel,
                "TRTA": subj["TRT01A"],
                "AVISIT": visit, "AVISITN": visitn,
                "ASTDT": astdt.strftime("%Y-%m-%d"), "AENDT": aendt.strftime("%Y-%m-%d"),
                "ASEQ": aeseq,
            })

    df = pd.DataFrame(rows)

    # INJECTED ERROR 3: AVISITN / AVISIT mismatch on a few rows
    bad_idx = df.sample(4, random_state=3).index
    df.loc[bad_idx, "AVISITN"] = df.loc[bad_idx, "AVISITN"].apply(lambda v: (v % 6) + 1)

    # INJECTED ERROR 4: missing ASEQ on a few rows
    bad_idx2 = df.sample(3, random_state=4).index
    df.loc[bad_idx2, "ASEQ"] = np.nan

    # INJECTED ERROR 5: duplicate ASEQ within the same USUBJID
    dup_candidates = df.groupby("USUBJID").filter(lambda g: len(g) >= 2)
    if len(dup_candidates) >= 2:
        pair = dup_candidates.sample(2, random_state=5)
        same_subj = pair.iloc[0]["USUBJID"]
        same_rows = df[df["USUBJID"] == same_subj]
        if len(same_rows) >= 2:
            idxs = same_rows.index[:2]
            df.loc[idxs[1], "ASEQ"] = df.loc[idxs[0], "ASEQ"]

    # INJECTED ERROR 6: AESTDTC after AEENDTC (start after end)
    bad_idx3 = df.sample(3, random_state=6).index
    df.loc[bad_idx3, ["AESTDTC", "AEENDTC"]] = df.loc[bad_idx3, ["AEENDTC", "AESTDTC"]].values
    df.loc[bad_idx3, ["ASTDT", "AENDT"]] = df.loc[bad_idx3, ["AENDT", "ASTDT"]].values

    # INJECTED ERROR 7: a couple of AE rows reference a USUBJID not in ADSL
    # (referential integrity break)
    fake_rows = df.sample(2, random_state=7).copy()
    fake_rows["USUBJID"] = ["STUDY01-9991", "STUDY01-9992"]
    df = pd.concat([df, fake_rows], ignore_index=True)

    return df


if __name__ == "__main__":
    adsl = gen_adsl()
    adae = gen_adae(adsl)

    adsl.to_csv("adsl.csv", index=False)
    adae.to_csv("adae.csv", index=False)

    print(f"ADSL: {len(adsl)} subjects -> adsl.csv")
    print(f"ADAE: {len(adae)} AE records -> adae.csv")
