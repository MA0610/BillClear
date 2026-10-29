"""
Integration tests for BillClear API endpoints.
Requires Ollama running with llama3.2 pulled.

Run all:          pytest tests/test_api.py -v
Skip AI tests:    pytest tests/test_api.py -v -m "not ai"
AI tests only:    pytest tests/test_api.py -v -m ai
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import io
import pytest
from app import app as flask_app

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_data")


def read_sample(fname):
    with open(os.path.join(SAMPLE_DIR, fname), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ─────────────────────────────────────────────
# Health check (no Ollama needed)
# ─────────────────────────────────────────────

class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self, client):
        data = client.get("/health").get_json()
        assert data["status"] == "ok"

    def test_health_returns_model_name(self, client):
        data = client.get("/health").get_json()
        assert "model" in data


# ─────────────────────────────────────────────
# Input validation (no Ollama needed)
# ─────────────────────────────────────────────

class TestInputValidation:
    def test_no_body_returns_400(self, client):
        resp = client.post("/analyze", json={})
        assert resp.status_code == 400

    def test_empty_text_returns_400(self, client):
        resp = client.post("/analyze", json={"text": ""})
        assert resp.status_code == 400

    def test_too_short_text_returns_400(self, client):
        resp = client.post("/analyze", json={"text": "hi"})
        assert resp.status_code == 400

    def test_whitespace_only_returns_400(self, client):
        resp = client.post("/analyze", json={"text": "   \n\t  "})
        assert resp.status_code == 400

    def test_error_field_present_on_400(self, client):
        resp = client.post("/analyze", json={"text": "too short"})
        data = resp.get_json()
        assert "error" in data

    def test_unsupported_file_type_returns_400(self, client):
        data = {"file": (io.BytesIO(b"fake content"), "test.docx", "application/msword")}
        resp = client.post("/analyze", content_type="multipart/form-data", data=data)
        assert resp.status_code == 400

    def test_txt_file_upload_not_rejected_on_type(self, client):
        """A valid .txt upload should pass file-type validation (may still fail if Ollama is down)."""
        bill_bytes = read_sample("sample_bill.txt").encode("utf-8")
        data = {"file": (io.BytesIO(bill_bytes), "bill.txt", "text/plain")}
        resp = client.post("/analyze", content_type="multipart/form-data", data=data)
        # 200 (success) or 502 (Ollama down) are both acceptable — just not 400 (bad file type)
        assert resp.status_code in (200, 502), f"Unexpected status {resp.status_code}: {resp.get_json()}"


# ─────────────────────────────────────────────
# AI analysis — sample bill
# ─────────────────────────────────────────────

@pytest.mark.ai
class TestSampleBill:
    def test_returns_200(self, bill_analysis):
        _, status = bill_analysis
        assert status == 200

    def test_document_type_is_bill(self, bill_analysis):
        data, _ = bill_analysis
        doc_type = (data.get("document_type") or "").lower()
        assert "bill" in doc_type or "medical" in doc_type, f"Got: {doc_type}"

    def test_patient_responsibility_is_1201(self, bill_analysis):
        data, _ = bill_analysis
        amount = (data.get("patient_responsibility") or {}).get("amount", 0)
        assert abs(amount - 1201.0) < 1.0, f"Expected ~1201, got {amount}"

    def test_has_seven_charges(self, bill_analysis):
        data, _ = bill_analysis
        assert len(data.get("charges", [])) == 7

    def test_duplicate_96365_appears_twice(self, bill_analysis):
        data, _ = bill_analysis
        codes = [c.get("code") for c in data.get("charges", [])]
        assert codes.count("96365") == 2, f"Expected 96365 twice, got: {codes}"

    def test_er_visit_billed_2850(self, bill_analysis):
        data, _ = bill_analysis
        er = next((c for c in data.get("charges", []) if c.get("code") == "99284"), None)
        assert er is not None, "ER visit charge (99284) not found"
        assert abs(er["billed_amount"] - 2850.0) < 1.0, f"Expected 2850, got {er['billed_amount']}"

    def test_duplicate_flag_present(self, bill_analysis):
        data, _ = bill_analysis
        flags = data.get("flags", [])
        has_dup = any(
            "duplic" in (f.get("issue") or "").lower() or
            "duplic" in (f.get("explanation") or "").lower()
            for f in flags
        )
        assert has_dup, f"No duplicate flag found. Flags: {[f.get('issue') for f in flags]}"

    def test_summary_is_non_empty(self, bill_analysis):
        data, _ = bill_analysis
        assert data.get("summary", "").strip() != ""

    def test_has_questions_to_ask(self, bill_analysis):
        data, _ = bill_analysis
        assert len(data.get("questions_to_ask", [])) >= 1

    def test_has_next_steps(self, bill_analysis):
        data, _ = bill_analysis
        assert len(data.get("next_steps", [])) >= 1

    def test_meta_model_is_llama(self, bill_analysis):
        data, _ = bill_analysis
        assert data.get("_meta", {}).get("model") == "llama3.2"

    def test_meta_elapsed_is_positive_float(self, bill_analysis):
        data, _ = bill_analysis
        elapsed = data.get("_meta", {}).get("elapsed_seconds")
        assert isinstance(elapsed, float) and elapsed > 0, f"Got: {elapsed}"


# ─────────────────────────────────────────────
# AI analysis — sample EOB
# ─────────────────────────────────────────────

@pytest.mark.ai
class TestSampleEOB:
    def test_returns_200(self, eob_analysis):
        _, status = eob_analysis
        assert status == 200

    def test_document_type_is_eob(self, eob_analysis):
        data, _ = eob_analysis
        doc_type = (data.get("document_type") or "").lower()
        assert any(w in doc_type for w in ["eob", "explanation", "benefit"]), f"Got: {doc_type}"

    def test_patient_responsibility_is_516(self, eob_analysis):
        data, _ = eob_analysis
        amount = (data.get("patient_responsibility") or {}).get("amount", 0)
        assert abs(amount - 516.0) < 1.0, f"Expected ~516, got {amount}"

    def test_er_visit_billed_2850_if_present(self, eob_analysis):
        """If the model includes 99284, its billed amount must be 2850 (snapped by validator)."""
        data, _ = eob_analysis
        er = next((c for c in data.get("charges", []) if c.get("code") == "99284"), None)
        if er is not None:
            assert abs(er["billed_amount"] - 2850.0) < 1.0, f"Expected 2850, got {er['billed_amount']}"

    def test_er_visit_insurance_paid_1368_if_present(self, eob_analysis):
        """If the model includes 99284, insurance paid must be 1368."""
        data, _ = eob_analysis
        er = next((c for c in data.get("charges", []) if c.get("code") == "99284"), None)
        if er is not None:
            assert abs(er["insurance_paid"] - 1368.0) < 1.0, f"Expected 1368, got {er['insurance_paid']}"

    def test_er_visit_patient_owes_342_if_present(self, eob_analysis):
        """If the model includes 99284, patient owes must be 342."""
        data, _ = eob_analysis
        er = next((c for c in data.get("charges", []) if c.get("code") == "99284"), None)
        if er is not None:
            assert abs(er["patient_owes"] - 342.0) < 1.0, f"Expected 342, got {er['patient_owes']}"

    def test_has_at_least_one_charge(self, eob_analysis):
        data, _ = eob_analysis
        assert len(data.get("charges", [])) >= 1

    def test_iv_infusion_denied_or_zero_paid(self, eob_analysis):
        """96365 was denied in the EOB — if present, insurance_paid should be 0."""
        data, _ = eob_analysis
        iv = next((c for c in data.get("charges", []) if c.get("code") == "96365"), None)
        if iv is not None:
            assert abs((iv.get("insurance_paid") or 0) - 0.0) < 1.0, \
                f"Expected denied (ins=0), got {iv.get('insurance_paid')}"
        # If model omits the denied charge entirely, that's also acceptable

    def test_has_flags(self, eob_analysis):
        data, _ = eob_analysis
        assert len(data.get("flags", [])) >= 1

    def test_has_questions_to_ask(self, eob_analysis):
        data, _ = eob_analysis
        assert len(data.get("questions_to_ask", [])) >= 1

    def test_summary_is_non_empty(self, eob_analysis):
        data, _ = eob_analysis
        assert data.get("summary", "").strip() != ""


# ─────────────────────────────────────────────
# AI analysis — edge cases
# ─────────────────────────────────────────────

@pytest.mark.ai
class TestEdgeCases:
    def test_non_medical_text_returns_unknown(self, client):
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is a recipe for chocolate cake with flour and sugar. "
            "Mix all ingredients and bake at 350 degrees for 30 minutes."
        )
        resp = client.post("/analyze", json={"text": text})
        assert resp.status_code == 200
        doc_type = (resp.get_json().get("document_type") or "").lower()
        assert "unknown" in doc_type, f"Expected 'unknown', got: {doc_type}"

    def test_amount_normalization_thousands_separator(self, client):
        text = (
            "PATIENT STATEMENT\n"
            "Patient: Test User  Account: 123\n"
            "Date of Service: 01/01/2024\n"
            "Services: IV Infusion 96365 $320.00\n"
            "         IV Infusion 96365 $320.00\n"
            "Total Billed: $4,940.00\n"
            "Insurance Payment: -$2,847.00\n"
            "AMOUNT DUE: $1,201.00"
        )
        resp = client.post("/analyze", json={"text": text})
        assert resp.status_code == 200
        amount = (resp.get_json().get("patient_responsibility") or {}).get("amount", 0)
        assert abs(amount - 1201.0) < 2.0, f"Expected ~1201, got {amount}"

    def test_response_always_has_required_keys(self, bill_analysis):
        data, _ = bill_analysis
        for key in ("document_type", "summary", "patient_responsibility",
                    "charges", "flags", "questions_to_ask", "next_steps", "_meta"):
            assert key in data, f"Missing key: {key}"
