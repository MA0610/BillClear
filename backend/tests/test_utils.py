"""
Unit tests for BillClear backend utility functions.
No Ollama or network connection required.
Run with: pytest tests/test_utils.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from app import fix_amount, normalize_amounts, parse_doc_amounts, parse_doc_responsibility, snap_to_document, validate_against_document, line_amounts, map_row_columns, find_charge_rows, validate_flags

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_data")


def read_sample(fname):
    with open(os.path.join(SAMPLE_DIR, fname), encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────
# fix_amount
# ─────────────────────────────────────────────

class TestFixAmount:
    def test_normal_float_unchanged(self):
        assert fix_amount(1201.00) == 1201.00

    def test_thousands_separator_bug_corrected(self):
        # Model wrote 1.201 meaning 1201
        result = fix_amount(1.201)
        assert abs(result - 1201.0) < 0.01

    def test_thousands_separator_large(self):
        # 2.847 → 2847 (3 decimal places, value < 10)
        result = fix_amount(2.847)
        assert abs(result - 2847.0) < 0.01

    def test_small_legitimate_amount_unchanged(self):
        # $5.00 copay — should NOT be multiplied
        assert fix_amount(5.00) == 5.00

    def test_two_decimal_unchanged(self):
        # 320.00 is a normal amount, not a thousands-sep pattern
        assert fix_amount(320.00) == 320.00

    def test_zero_unchanged(self):
        assert fix_amount(0.0) == 0.0

    def test_none_returns_none(self):
        assert fix_amount(None) is None

    def test_integer_input(self):
        assert fix_amount(516) == 516.0

    def test_string_float_coerced(self):
        assert fix_amount("425.00") == 425.00


# ─────────────────────────────────────────────
# normalize_amounts
# ─────────────────────────────────────────────

class TestNormalizeAmounts:
    def test_fixes_patient_responsibility(self):
        result = normalize_amounts({
            "patient_responsibility": {"amount": 1.201, "explanation": "test"},
            "charges": []
        })
        assert abs(result["patient_responsibility"]["amount"] - 1201.0) < 0.01

    def test_fixes_charge_amounts(self):
        # 2.847 and 1.368 are thousands-separator bugs (3 decimal places, < 10)
        result = normalize_amounts({
            "patient_responsibility": {"amount": 516.0},
            "charges": [
                {"billed_amount": 2.847, "insurance_paid": 1.368, "patient_owes": 342.0}
            ]
        })
        c = result["charges"][0]
        assert abs(c["billed_amount"] - 2847.0) < 0.01
        assert abs(c["insurance_paid"] - 1368.0) < 0.01
        assert c["patient_owes"] == 342.0

    def test_preserves_none_amounts(self):
        result = normalize_amounts({
            "patient_responsibility": {"amount": None},
            "charges": [{"billed_amount": None, "insurance_paid": None, "patient_owes": None}]
        })
        assert result["patient_responsibility"]["amount"] is None
        assert result["charges"][0]["billed_amount"] is None

    def test_handles_missing_charges_key(self):
        result = normalize_amounts({"patient_responsibility": {"amount": 100.0}})
        assert result["patient_responsibility"]["amount"] == 100.0

    def test_handles_empty_result(self):
        result = normalize_amounts({})
        assert result == {}


# ─────────────────────────────────────────────
# parse_doc_amounts
# ─────────────────────────────────────────────

class TestParseDocAmounts:
    def test_extracts_basic_amounts(self):
        text = "Total: $1,201.00 and also $320.00"
        amounts = parse_doc_amounts(text)
        assert 1201.00 in amounts
        assert 320.00 in amounts

    def test_extracts_amounts_without_cents(self):
        amounts = parse_doc_amounts("Balance: $500")
        assert 500.0 in amounts

    def test_extracts_multiple_amounts(self):
        text = "$2,850.00 $425.00 $180.00 $650.00"
        amounts = parse_doc_amounts(text)
        assert len(amounts) >= 4

    def test_ignores_non_dollar_numbers(self):
        amounts = parse_doc_amounts("CPT code 99284 billed on 09/15/24")
        assert 99284.0 not in amounts
        assert 9.0 not in amounts

    def test_empty_text_returns_empty_set(self):
        assert parse_doc_amounts("") == set()

    def test_commas_in_amounts_parsed_correctly(self):
        amounts = parse_doc_amounts("$4,940.00")
        assert 4940.00 in amounts


# ─────────────────────────────────────────────
# parse_doc_responsibility
# ─────────────────────────────────────────────

class TestParseDocResponsibility:
    def test_amount_due_pattern(self):
        text = "AMOUNT DUE: $1,201.00"
        assert abs(parse_doc_responsibility(text) - 1201.0) < 0.01

    def test_amount_due_lowercase(self):
        text = "Amount Due: $516.00"
        assert abs(parse_doc_responsibility(text) - 516.0) < 0.01

    def test_balance_due_pattern(self):
        text = "Balance Due: $342.00"
        assert abs(parse_doc_responsibility(text) - 342.0) < 0.01

    def test_patient_responsibility_pattern(self):
        text = "Patient Responsibility: $250.00"
        assert abs(parse_doc_responsibility(text) - 250.0) < 0.01

    def test_your_cost_eob_pattern(self):
        text = "Your Cost $516.00"
        assert abs(parse_doc_responsibility(text) - 516.0) < 0.01

    def test_total_due_pattern(self):
        text = "TOTAL DUE: $899.50"
        assert abs(parse_doc_responsibility(text) - 899.50) < 0.01

    def test_no_match_returns_none(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert parse_doc_responsibility(text) is None

    def test_amount_without_cents(self):
        text = "AMOUNT DUE: $1201"
        assert abs(parse_doc_responsibility(text) - 1201.0) < 0.01

    def test_amount_with_commas(self):
        text = "Balance Due: $1,201.00"
        assert abs(parse_doc_responsibility(text) - 1201.0) < 0.01


# ─────────────────────────────────────────────
# snap_to_document
# ─────────────────────────────────────────────

class TestSnapToDocument:
    def test_exact_match_unchanged(self):
        amounts = {2850.0, 425.0, 320.0}
        assert snap_to_document(2850.0, amounts) == 2850.0

    def test_snaps_within_one_percent(self):
        # Model read 2840 but document has 2850 (0.35% difference)
        amounts = {2850.0, 425.0}
        result = snap_to_document(2840.0, amounts)
        assert abs(result - 2850.0) < 0.01

    def test_does_not_snap_outside_tolerance(self):
        # 2750 is too far from 2850 (3.5% difference)
        amounts = {2850.0}
        assert snap_to_document(2750.0, amounts) == 2750.0

    def test_snaps_within_min_one_dollar(self):
        # Small amounts use $1 minimum tolerance
        amounts = {51.0}
        result = snap_to_document(50.5, amounts)
        assert abs(result - 51.0) < 0.01

    def test_none_returns_none(self):
        assert snap_to_document(None, {100.0}) is None

    def test_empty_doc_amounts_unchanged(self):
        assert snap_to_document(320.0, set()) == 320.0

    def test_picks_closest_when_multiple_candidates(self):
        # 319 is within 1% of 320 (tolerance=3.19), so snaps to 320 over 318
        amounts = {318.0, 320.0, 325.0}
        result = snap_to_document(319.0, amounts)
        assert abs(result - 320.0) < 0.01

    def test_no_snap_when_all_candidates_outside_tolerance(self):
        # 320 → nearest is 325 (diff=5), tolerance is max(1, 3.2)=3.2 — no snap
        amounts = {300.0, 325.0, 350.0}
        result = snap_to_document(320.0, amounts)
        assert result == 320.0

    def test_rescales_x1000_when_in_document(self):
        # Model wrote 2.85 meaning 2850 (2-decimal thousands separator bug)
        amounts = {2850.0, 425.0, 516.0}
        result = snap_to_document(2.85, amounts)
        assert abs(result - 2850.0) < 0.01


# ─────────────────────────────────────────────
# validate_against_document
# ─────────────────────────────────────────────

class TestValidateAgainstDocument:
    def test_corrects_wrong_responsibility(self):
        result = {
            "patient_responsibility": {"amount": 1.201, "explanation": "test"},
            "charges": []
        }
        text = "AMOUNT DUE: $1,201.00"
        out = validate_against_document(result, text)
        assert abs(out["patient_responsibility"]["amount"] - 1201.0) < 0.01

    def test_leaves_correct_responsibility_unchanged(self):
        result = {
            "patient_responsibility": {"amount": 516.0, "explanation": "test"},
            "charges": []
        }
        text = "Your Cost $516.00"
        out = validate_against_document(result, text)
        assert abs(out["patient_responsibility"]["amount"] - 516.0) < 0.01

    def test_snaps_charge_billed_amount(self):
        result = {
            "patient_responsibility": {"amount": 516.0},
            "charges": [
                {"code": "99284", "billed_amount": 2840.0, "insurance_paid": 1368.0, "patient_owes": 342.0}
            ]
        }
        text = "ER Visit $2,850.00 insurance paid $1,368.00 you owe $342.00\nYour Cost $516.00"
        out = validate_against_document(result, text)
        assert abs(out["charges"][0]["billed_amount"] - 2850.0) < 0.01

    def test_handles_no_responsibility_in_document(self):
        result = {
            "patient_responsibility": {"amount": 516.0},
            "charges": []
        }
        out = validate_against_document(result, "no amounts here")
        assert abs(out["patient_responsibility"]["amount"] - 516.0) < 0.01

    def test_handles_missing_patient_responsibility(self):
        result = {"charges": []}
        out = validate_against_document(result, "AMOUNT DUE: $100.00")
        assert "charges" in out


# ─────────────────────────────────────────────
# Row-level charge validation
# ─────────────────────────────────────────────

class TestRowHelpers:
    def test_line_amounts_in_order(self):
        assert line_amounts("ER  $2,850.00  $0.00  $342.00") == [2850.0, 0.0, 342.0]

    def test_find_charge_rows_requires_whole_code_and_amounts(self):
        lines = ["99284 $10.00", "199284 $20.00", "CPT 99284 no amounts", "99284-25 $30.00"]
        assert find_charge_rows(lines, "99284") == [0]

    def test_maps_eob_columns(self):
        lines = read_sample("sample_eob.txt").splitlines()
        idx = find_charge_rows(lines, "99284")[0]
        mapping = map_row_columns(lines, idx, line_amounts(lines[idx]))
        assert mapping == {"billed_amount": 2850.0, "insurance_paid": 1368.0, "patient_owes": 342.0}

    def test_maps_bill_amount_column_to_billed(self):
        lines = read_sample("sample_bill.txt").splitlines()
        idx = find_charge_rows(lines, "99284")[0]
        mapping = map_row_columns(lines, idx, line_amounts(lines[idx]))
        assert mapping == {"billed_amount": 2850.0}

    def test_maps_single_spaced_header(self):
        # PDF text extraction collapses column gaps to single spaces
        lines = [
            "Service Description Code Billed Not Covered Discount Plan Paid Your Cost",
            "Office Visit, Level 4 99214 $310.00 $0.00 $124.00 $148.80 $37.20",
        ]
        mapping = map_row_columns(lines, 1, line_amounts(lines[1]))
        assert mapping == {"billed_amount": 310.0, "insurance_paid": 148.8, "patient_owes": 37.2}

    def test_header_label_count_must_match_amounts(self):
        # A prose line mentioning "billed" between rows must not be taken as the header
        lines = [
            "Billed Plan Paid Your Cost",
            "Denial reason: billed twice",
            "X-Ray 71046 $650.00 $312.00 $78.00",
        ]
        mapping = map_row_columns(lines, 2, line_amounts(lines[2]))
        assert mapping == {"billed_amount": 650.0, "insurance_paid": 312.0, "patient_owes": 78.0}

    def test_no_header_returns_empty_mapping(self):
        lines = ["ER Visit 99284 $2,850.00 $342.00"]
        assert map_row_columns(lines, 0, line_amounts(lines[0])) == {}


class TestChargeRowValidation:
    def _validate(self, charge, sample):
        result = {"patient_responsibility": {"amount": 516.0}, "charges": [charge]}
        return validate_against_document(result, read_sample(sample))["charges"][0]

    def test_eob_total_misplaced_on_line_is_corrected(self):
        # Regression: model put the $516 claim total on the ER line; $516 is
        # in the document, so document-wide snapping let it through.
        c = self._validate(
            {"code": "99284", "billed_amount": 2850.0, "insurance_paid": 1368.0, "patient_owes": 516.0},
            "sample_eob.txt",
        )
        assert c["patient_owes"] == 342.0

    def test_eob_swapped_columns_corrected(self):
        c = self._validate(
            {"code": "80053", "billed_amount": 425.0, "insurance_paid": 51.0, "patient_owes": 204.0},
            "sample_eob.txt",
        )
        assert c["insurance_paid"] == 204.0
        assert c["patient_owes"] == 51.0

    def test_eob_correct_values_unchanged(self):
        c = self._validate(
            {"code": "71046", "billed_amount": 650.0, "insurance_paid": 312.0, "patient_owes": 78.0},
            "sample_eob.txt",
        )
        assert (c["billed_amount"], c["insurance_paid"], c["patient_owes"]) == (650.0, 312.0, 78.0)

    def test_eob_denied_charge_zero_paid(self):
        c = self._validate(
            {"code": "96365", "billed_amount": 640.0, "insurance_paid": 0.0, "patient_owes": 0.0},
            "sample_eob.txt",
        )
        assert c["insurance_paid"] == 0.0
        assert c["patient_owes"] == 0.0

    def test_eob_thousands_bug_on_row_rescaled(self):
        c = self._validate(
            {"code": "99284", "billed_amount": 2.85, "insurance_paid": 1368.0, "patient_owes": 342.0},
            "sample_eob.txt",
        )
        assert c["billed_amount"] == 2850.0

    def test_bill_value_not_on_row_is_cleared(self):
        # Bill has no "you owe" column; $516-style values pulled from elsewhere are dropped
        c = self._validate(
            {"code": "80053", "billed_amount": 425.0, "insurance_paid": None, "patient_owes": 2850.0},
            "sample_bill.txt",
        )
        assert c["billed_amount"] == 425.0
        assert c["patient_owes"] is None

    def test_bill_value_on_row_kept(self):
        c = self._validate(
            {"code": "99284", "billed_amount": 2850.0, "insurance_paid": 0.0, "patient_owes": 2850.0},
            "sample_bill.txt",
        )
        assert c["billed_amount"] == 2850.0
        assert c["insurance_paid"] == 0.0
        assert c["patient_owes"] == 2850.0

    def test_pdf_eob_shifted_columns_corrected(self):
        # Regression: on the PDF EOB the model shifted every value one column
        # left (paid=Discount, owes=Plan Paid) and all of them are on the row.
        import pdfplumber
        with pdfplumber.open(os.path.join(SAMPLE_DIR, "sample_eob_urgent_care.pdf")) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        result = {"patient_responsibility": {"amount": 88.2}, "charges": [
            {"code": "99214", "billed_amount": 310.0, "insurance_paid": 124.0, "patient_owes": 148.8},
            {"code": "J1100", "billed_amount": 45.0, "insurance_paid": 45.0, "patient_owes": 0.0},
        ]}
        office, denied = validate_against_document(result, text)["charges"]
        assert (office["insurance_paid"], office["patient_owes"]) == (148.8, 37.2)
        assert (denied["insurance_paid"], denied["patient_owes"]) == (0.0, 0.0)

    def test_code_not_in_document_falls_back_to_document_snap(self):
        c = self._validate(
            {"code": "00000", "billed_amount": 2840.0, "insurance_paid": None, "patient_owes": None},
            "sample_eob.txt",
        )
        assert c["billed_amount"] == 2850.0


# ─────────────────────────────────────────────
# validate_flags
# ─────────────────────────────────────────────

def pdf_sample_text(fname):
    import pdfplumber
    with pdfplumber.open(os.path.join(SAMPLE_DIR, fname)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def flag(issue, explanation="", severity="warning"):
    return {"severity": severity, "issue": issue, "explanation": explanation, "action": "call"}


def issues(result):
    return [f["issue"] for f in result["flags"]]


PDF_CHARGES = [
    {"code": "99214", "description": "Office Visit", "billed_amount": 310.0, "insurance_paid": 148.8, "patient_owes": 37.2},
    {"code": "87880", "description": "Rapid Strep Test", "billed_amount": 65.0, "insurance_paid": 31.2, "patient_owes": 7.8},
    {"code": "J1100", "description": "Dexamethasone Injection", "billed_amount": 45.0, "insurance_paid": 0.0, "patient_owes": 0.0},
]


class TestValidateFlags:
    def test_pdf_eob_false_flags_removed_and_denial_added(self):
        # Regression: exact flags llama3.2 produced for sample_eob_urgent_care.pdf
        result = {
            "patient_responsibility": {"amount": 88.2},
            "charges": [dict(c) for c in PDF_CHARGES],
            "flags": [
                flag("Duplicate Charges", "The same CPT code (99214) was billed twice for the same date."),
                flag("Large Balance", "Your patient responsibility is $88.20, which is over $500.", "info"),
            ],
        }
        out = validate_flags(result, pdf_sample_text("sample_eob_urgent_care.pdf"))
        assert issues(out) == ["Denied charge: Dexamethasone Injection (J1100)"]
        assert "$45.00" in out["flags"][0]["explanation"]

    def test_bill_duplicate_flag_kept(self):
        result = {
            "patient_responsibility": {"amount": 1201.0},
            "charges": [{"code": "96365", "billed_amount": 320.0}, {"code": "96365", "billed_amount": 320.0}],
            "flags": [flag("Duplicate charge", "CPT 96365 billed twice")],
        }
        out = validate_flags(result, read_sample("sample_bill.txt"))
        assert "Duplicate charge" in issues(out)

    def test_bill_duplicate_flag_added_when_missing(self):
        result = {
            "patient_responsibility": {"amount": 1201.0},
            "charges": [{"code": "96365", "billed_amount": 320.0}, {"code": "96365", "billed_amount": 320.0}],
            "flags": [],
        }
        out = validate_flags(result, read_sample("sample_bill.txt"))
        assert "Duplicate charge: CPT 96365" in issues(out)

    def test_eob_duplicate_flag_kept_when_document_mentions_duplicate(self):
        # The text EOB lists 96365 once but its denial reason says "Duplicate service"
        result = {
            "patient_responsibility": {"amount": 516.0},
            "charges": [{"code": "96365", "description": "IV Infusion", "billed_amount": 640.0, "insurance_paid": 0.0}],
            "flags": [flag("Duplicate IV infusion denied", "96365 was denied as a duplicate")],
        }
        out = validate_flags(result, read_sample("sample_eob.txt"))
        assert issues(out) == ["Duplicate IV infusion denied", "Large balance"]

    def test_large_balance_flag_added_over_threshold(self):
        result = {"patient_responsibility": {"amount": 1201.0}, "charges": [], "flags": []}
        out = validate_flags(result, "AMOUNT DUE: $1,201.00")
        assert issues(out) == ["Large balance"]
        assert out["flags"][0]["severity"] == "info"

    def test_large_balance_flag_kept_over_threshold(self):
        result = {"patient_responsibility": {"amount": 1201.0}, "charges": [],
                  "flags": [flag("Large Balance", "Ask about payment plans", "info")]}
        out = validate_flags(result, "AMOUNT DUE: $1,201.00")
        assert issues(out) == ["Large Balance"]

    def test_denied_flag_not_duplicated_when_model_already_flagged(self):
        result = {
            "patient_responsibility": {"amount": 88.2},
            "charges": [dict(c) for c in PDF_CHARGES],
            "flags": [flag("Denied injection", "J1100 was denied by your plan")],
        }
        out = validate_flags(result, pdf_sample_text("sample_eob_urgent_care.pdf"))
        assert issues(out) == ["Denied injection"]

    def test_warnings_sorted_before_info(self):
        result = {"patient_responsibility": {"amount": 1201.0}, "charges": [],
                  "flags": [flag("Large Balance", "payment plan", "info"), flag("Something odd")]}
        out = validate_flags(result, "")
        assert [f["severity"] for f in out["flags"]] == ["warning", "info"]

    def test_handles_missing_flags_and_responsibility(self):
        out = validate_flags({"charges": []}, "")
        assert out["flags"] == []
