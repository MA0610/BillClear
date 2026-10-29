from flask import Flask, request, jsonify
from flask_cors import CORS
import ollama
import pdfplumber
import io
import json
import os
import re

app = Flask(__name__)
CORS(app)

MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")


def fix_amount(val):
    """Fix amounts where the model used a dot as a thousands separator (e.g. 1.201 → 1201.0)."""
    if val is None:
        return val
    try:
        f = float(val)
        # Heuristic: medical bills are rarely under $10.
        # If the value looks like X.YYY (3 decimal places) and is under 10,
        # it's likely a thousands-separated number like 1.201 meaning 1201.
        s = str(val)
        if "." in s:
            decimals = s.split(".")[1]
            if len(decimals) == 3 and f < 10:
                return f * 1000
        return f
    except (TypeError, ValueError):
        return val


def normalize_amounts(result):
    """Walk the result and fix any misformatted monetary amounts."""
    if isinstance(result.get("patient_responsibility"), dict):
        pr = result["patient_responsibility"]
        pr["amount"] = fix_amount(pr.get("amount"))

    for charge in result.get("charges") or []:
        for field in ("billed_amount", "insurance_paid", "patient_owes"):
            charge[field] = fix_amount(charge.get(field))

    return result


def parse_doc_amounts(text):
    """Extract every dollar amount present in the document as a set of floats."""
    amounts = set()
    for m in re.findall(r'\$\s*([\d,]+(?:\.\d{1,2})?)', text):
        try:
            amounts.add(round(float(m.replace(',', '')), 2))
        except ValueError:
            pass
    return amounts


def parse_doc_responsibility(text):
    """
    Regex-scan the document for the canonical 'amount you owe' figure.
    Returns a float if found, else None.
    """
    patterns = [
        r'AMOUNT\s+DUE\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)',
        r'Amount\s+Due\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)',
        r'TOTAL\s+DUE\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)',
        r'Balance\s+Due\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)',
        r'Patient\s+Responsibility\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)',
        r'YOUR?\s+COST\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)',   # EOB
        r'Your\s+Cost\s*\$?\s*([\d,]+(?:\.\d{1,2})?)',              # EOB table total
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return round(float(m.group(1).replace(',', '')), 2)
            except ValueError:
                pass
    return None


def snap_to_document(val, doc_amounts):
    """
    If val is not in the document's known amounts:
    1. Try x1000 rescale (catches 2.85 → 2850 style thousands-separator bugs)
    2. Snap to nearest document amount within 1% tolerance (min $1)
    Returns val unchanged if no correction found.
    """
    if val is None:
        return val
    rounded = round(val, 2)
    if rounded in doc_amounts:
        return val
    # Try x1000 rescale — model wrote 2.85 meaning 2850
    scaled = round(val * 1000, 2)
    if scaled in doc_amounts:
        return scaled
    # Tolerance snap for small reading errors (e.g. 2840 → 2850)
    tolerance = max(1.0, val * 0.01)
    close = [a for a in doc_amounts if abs(a - val) <= tolerance]
    if close:
        return min(close, key=lambda a: abs(a - val))
    return val


def validate_against_document(result, raw_text):
    """
    Cross-check the model's extracted amounts against the source document.
    1. Correct patient_responsibility if it doesn't match the document total.
    2. Snap each charge amount to the nearest value actually in the document.
    """
    doc_amounts = parse_doc_amounts(raw_text)
    doc_responsibility = parse_doc_responsibility(raw_text)

    # Fix patient responsibility
    if isinstance(result.get("patient_responsibility"), dict):
        pr = result["patient_responsibility"]
        model_amount = pr.get("amount")
        if doc_responsibility is not None and model_amount is not None:
            if abs(model_amount - doc_responsibility) > 0.5:
                pr["amount"] = doc_responsibility

    # Snap individual charge amounts to values present in the document
    for charge in result.get("charges") or []:
        for field in ("billed_amount", "insurance_paid", "patient_owes"):
            charge[field] = snap_to_document(charge.get(field), doc_amounts)

    return result

SYSTEM_PROMPT = """You are a medical billing expert helping patients understand their medical bills and Explanation of Benefits (EOB) documents. Your goal is to translate confusing medical billing language into plain English, identify potential errors or issues, and tell patients exactly what they need to do.

Medical bills often contain:
- CPT codes (procedure codes like 99284 for ER visits, 80053 for metabolic panels)
- ICD-10 codes (diagnosis codes)
- EOB sections showing what insurance paid vs. what patient owes
- Adjustments, write-offs, and contractual discounts

Common billing errors to watch for:
- Duplicate charges (same CPT code billed twice in same visit)
- Upcoding (billing for a more expensive service than was provided)
- Unbundling (charging separately for services that should be billed together)
- Services not matching the stated diagnosis
- Insurance payments not credited against the balance
- Charges outside the coverage period

Always be specific, actionable, and empathetic. Patients are often stressed and confused by these documents. Use dollar amounts precisely when they appear in the document."""

ANALYSIS_PROMPT = """Analyze the following medical billing document carefully.

Document:
{document_text}

Return ONLY a valid JSON object with this exact structure. No markdown fences, no explanation, just the raw JSON:
{{
  "document_type": "one of: medical_bill, eob, unknown",
  "summary": "2-3 sentence plain English summary of what this document is and what action is required",
  "patient_responsibility": {{
    "amount": 0.00,
    "explanation": "plain English explanation of what the patient owes and why"
  }},
  "charges": [
    {{
      "description": "plain English name for this charge (not just the CPT code)",
      "code": "CPT or service code, or null if not present",
      "billed_amount": 0.00,
      "insurance_paid": 0.00,
      "patient_owes": 0.00
    }}
  ],
  "flags": [
    {{
      "severity": "warning",
      "issue": "short title for the potential problem",
      "explanation": "plain English explanation of why this might be a problem",
      "action": "specific thing the patient should do or say when they call"
    }}
  ],
  "questions_to_ask": [
    "Specific question to ask the billing department"
  ],
  "next_steps": [
    "Ordered, specific action for the patient to take"
  ]
}}

IMPORTANT - Before writing the flags array, scan the charges list for these issues:
1. DUPLICATE CHARGES: If the same CPT code appears more than once on the same date, that is a duplicate. Add a warning flag for it.
2. LARGE BALANCES: If patient_responsibility amount is over $500, add an info flag suggesting they request an itemized bill and ask about payment plans.

Rules:
- ALL monetary amounts must be plain decimal numbers. Write 1201.00 not 1,201 or 1.201. Never use commas or periods as thousands separators. A bill for twelve hundred dollars is 1200.00, not 1.200 or 1,200.
- Use null for missing numeric values, not 0
- flags array should be empty [] only if truly no issues exist
- Be specific — use actual dollar amounts and codes from the document
- document_type must be exactly "medical_bill" (a provider's bill or statement), "eob" (an insurer's Explanation of Benefits, often marked "This is not a bill"), or "unknown"
- If the document doesn't look like a medical bill or EOB, set document_type to "unknown" and explain in summary
- Output raw JSON only — no markdown, no ```json fences, no explanation before or after"""


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": MODEL})


@app.route("/analyze", methods=["POST"])
def analyze_bill():
    text = None

    if "file" in request.files:
        file = request.files["file"]
        filename = file.filename.lower()

        if filename.endswith(".pdf"):
            try:
                pdf_bytes = file.read()
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    pages = [page.extract_text() or "" for page in pdf.pages]
                    text = "\n".join(pages)
            except Exception as e:
                return jsonify({"error": f"Failed to read PDF: {str(e)}"}), 400
        elif filename.endswith((".txt", ".text")):
            try:
                text = file.read().decode("utf-8")
            except Exception:
                return jsonify({"error": "Could not read file. Please upload a PDF or .txt file."}), 400
        else:
            return jsonify({"error": "Unsupported file type. Please upload a PDF or .txt file."}), 400

    elif request.is_json and request.json.get("text"):
        text = request.json["text"]

    else:
        return jsonify({"error": "Please provide a file or paste bill text."}), 400

    text = text.strip()
    if len(text) < 30:
        return jsonify({"error": "Document appears empty or too short. Please check your upload."}), 400

    document_text = text[:5000]

    try:
        import time
        t0 = time.time()

        response = ollama.chat(
            model=MODEL,
            format="json",
            options={"temperature": 0},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": ANALYSIS_PROMPT.format(document_text=document_text)},
            ],
        )

        elapsed = round(time.time() - t0, 1)
        response_text = response["message"]["content"].strip()

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Try extracting JSON if model wrapped it in markdown
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(response_text[start:end])
            else:
                return jsonify({"error": "Analysis failed to produce structured output.", "raw": response_text}), 500

        result = normalize_amounts(result)
        result = validate_against_document(result, document_text)
        result["_meta"] = {"model": MODEL, "elapsed_seconds": elapsed}
        return jsonify(result)

    except ollama.ResponseError as e:
        return jsonify({"error": f"Ollama error: {str(e)}. Is Ollama running?"}), 502
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
