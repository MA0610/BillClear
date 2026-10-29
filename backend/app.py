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


# Header keywords for each charge field, checked in order (most specific first).
# Money-column labels seen in bill/EOB table headers, mapped to the charge
# field they hold (None = a money column we don't track, e.g. "discount").
COLUMN_LABELS = {
    "billed": "billed_amount", "billed amount": "billed_amount", "amount billed": "billed_amount",
    "billed charges": "billed_amount", "total charges": "billed_amount", "charges": "billed_amount",
    "charge": "billed_amount", "amount": "billed_amount",
    "plan paid": "insurance_paid", "insurance paid": "insurance_paid", "ins. paid": "insurance_paid",
    "ins paid": "insurance_paid", "amount paid": "insurance_paid", "plan pays": "insurance_paid",
    "paid": "insurance_paid",
    "your cost": "patient_owes", "you owe": "patient_owes", "what you owe": "patient_owes",
    "patient owes": "patient_owes", "patient responsibility": "patient_owes", "patient resp": "patient_owes",
    "your responsibility": "patient_owes", "member responsibility": "patient_owes",
    "your share": "patient_owes", "amount due": "patient_owes", "balance": "patient_owes",
    "unit price": None, "price": None, "not covered": None, "non-covered": None, "discount": None,
    "plan discount": None, "network discount": None, "adjustment": None, "adjustments": None,
    "allowed": None, "allowed amount": None, "amount allowed": None, "deductible": None,
    "copay": None, "co-pay": None, "coinsurance": None,
}
# Longest first so "plan paid" wins over "paid" and "allowed amount" over "amount".
COLUMN_LABEL_RE = re.compile(
    r'(?<!\w)(' + '|'.join(re.escape(l) for l in sorted(COLUMN_LABELS, key=len, reverse=True)) + r')(?!\w)',
    re.IGNORECASE,
)


def line_amounts(line):
    """Dollar amounts on a single line, in left-to-right order."""
    amounts = []
    for m in re.findall(r'\$\s*([\d,]+(?:\.\d{1,2})?)', line):
        try:
            amounts.append(round(float(m.replace(',', '')), 2))
        except ValueError:
            pass
    return amounts


def map_row_columns(lines, row_idx, amounts):
    """
    Find the table header above a charge row and map each field to the amount
    in its column. The header is the nearest line above with exactly one money
    column label per amount on the row; labels are matched by name rather than
    spacing, since PDF text extraction often collapses columns to single spaces.
    Returns {field: amount}, empty if no usable header is found.
    """
    for i in range(row_idx - 1, max(-1, row_idx - 16), -1):
        line = lines[i]
        if '$' in line:
            continue
        labels = [m.lower() for m in COLUMN_LABEL_RE.findall(line)]
        if len(labels) != len(amounts):
            continue
        mapping = {}
        for label, amount in zip(labels, amounts):
            field = COLUMN_LABELS[label]
            if field and field not in mapping:
                mapping[field] = amount
        if mapping:
            return mapping
    return {}


def find_charge_rows(lines, code):
    """Indexes of lines that mention this code as a whole word and contain dollar amounts."""
    pattern = re.compile(rf'(?<![\w-]){re.escape(code)}(?![\w-])')
    return [i for i, line in enumerate(lines) if pattern.search(line) and line_amounts(line)]


def validate_charge(charge, lines, doc_amounts):
    """
    Check a charge's amounts against the document row(s) carrying its code.
    - If the row's table header tells us which column a field is, use that value.
    - Otherwise the value must appear on the row; if it doesn't, the model
      likely pulled it from elsewhere (e.g. a total), so it's cleared to None.
    - Charges whose code isn't found fall back to a document-wide snap.
    """
    code = (charge.get("code") or "").strip()
    rows = find_charge_rows(lines, code) if code else []

    if not rows:
        for field in ("billed_amount", "insurance_paid", "patient_owes"):
            charge[field] = snap_to_document(charge.get(field), doc_amounts)
        return

    row_amounts = set()
    expected = {}
    for idx in rows:
        amounts = line_amounts(lines[idx])
        row_amounts.update(amounts)
        for field, amount in map_row_columns(lines, idx, amounts).items():
            expected.setdefault(field, set()).add(amount)

    for field in ("billed_amount", "insurance_paid", "patient_owes"):
        val = charge.get(field)
        if val is None:
            continue
        if field in expected:
            snapped = snap_to_document(val, expected[field])
            if round(snapped, 2) in expected[field]:
                charge[field] = snapped
            elif len(expected[field]) == 1:
                charge[field] = next(iter(expected[field]))
            else:
                charge[field] = None
        elif val == 0:
            continue
        else:
            snapped = snap_to_document(val, row_amounts)
            charge[field] = snapped if round(snapped, 2) in row_amounts else None


LARGE_BALANCE_THRESHOLD = 500.0


def flag_text(flag):
    return f"{flag.get('issue') or ''} {flag.get('explanation') or ''}".lower()


def is_duplicate_flag(flag):
    return "duplic" in flag_text(flag)


def is_large_balance_flag(flag):
    text = flag_text(flag)
    return "large balance" in text or "payment plan" in text


def money(val):
    return f"${val:,.2f}"


def duplicate_codes(result, lines):
    """Codes the model listed more than once that also appear on more than one document row."""
    codes = [(c.get("code") or "").strip() for c in result.get("charges") or []]
    return [code for code in dict.fromkeys(codes)
            if code and codes.count(code) > 1 and len(find_charge_rows(lines, code)) > 1]


def denied_charges(result, lines):
    """Charges whose code appears on a document line that says the service was denied."""
    denied = []
    for charge in result.get("charges") or []:
        code = (charge.get("code") or "").strip()
        if not code:
            continue
        pattern = re.compile(rf'(?<![\w-]){re.escape(code)}(?![\w-])')
        if any(pattern.search(line) and re.search(r'\bdeni(ed|al)\b', line, re.IGNORECASE) for line in lines):
            denied.append(charge)
    return denied


def validate_flags(result, raw_text):
    """
    Enforce the flag rules the prompt asks for, since the model doesn't follow them reliably:
    - Duplicate flags need evidence: a code repeated on the bill, or the document saying so.
    - Large-balance flags only when patient responsibility is over the threshold.
    - Every charge the document says was denied gets a warning.
    Warnings are listed before info flags.
    """
    lines = raw_text.splitlines()
    flags = [f for f in result.get("flags") or [] if isinstance(f, dict)]

    dup_codes = duplicate_codes(result, lines)
    if not dup_codes and "duplicate" not in raw_text.lower():
        flags = [f for f in flags if not is_duplicate_flag(f)]
    for code in dup_codes:
        if not any(is_duplicate_flag(f) and code.lower() in flag_text(f) for f in flags):
            flags.append({
                "severity": "warning",
                "issue": f"Duplicate charge: CPT {code}",
                "explanation": f"CPT {code} is billed more than once for the same visit. "
                               "This is a common billing error.",
                "action": f"Ask billing to confirm CPT {code} was provided more than once, "
                          "or remove the duplicate line.",
            })

    amount = (result.get("patient_responsibility") or {}).get("amount")
    if amount is not None:
        if amount <= LARGE_BALANCE_THRESHOLD:
            flags = [f for f in flags if not is_large_balance_flag(f)]
        elif not any(is_large_balance_flag(f) for f in flags):
            flags.append({
                "severity": "info",
                "issue": "Large balance",
                "explanation": f"You owe {money(amount)}. For balances this size it's worth "
                               "checking every line before paying.",
                "action": "Request an itemized bill and ask whether a payment plan or "
                          "financial assistance is available.",
            })

    for charge in denied_charges(result, lines):
        code = charge["code"].strip()
        if any(code.lower() in flag_text(f) and "deni" in flag_text(f) for f in flags):
            continue
        billed = charge.get("billed_amount")
        what = f"the {money(billed)} charge" if billed else "the charge"
        name = charge.get("description") or f"CPT {code}"
        flags.append({
            "severity": "warning",
            "issue": f"Denied charge: {name} ({code})",
            "explanation": f"Your insurance denied {what} for {name}. Read the denial reason "
                           "on your EOB — for many denials the provider can't bill you for it.",
            "action": f"Don't pay {what} for {name} if the provider bills you for it. Call your "
                      "insurer's member services first and ask whether you're responsible.",
        })

    flags.sort(key=lambda f: 0 if f.get("severity") == "warning" else 1)
    result["flags"] = flags
    return result


def validate_against_document(result, raw_text):
    """
    Cross-check the model's extracted amounts against the source document.
    1. Correct patient_responsibility if it doesn't match the document total.
    2. Check each charge's amounts against its own row in the document.
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

    # Check individual charge amounts against their rows in the document
    lines = raw_text.splitlines()
    for charge in result.get("charges") or []:
        validate_charge(charge, lines, doc_amounts)

    validate_flags(result, raw_text)

    return result

SYSTEM_PROMPT = """You are a medical billing expert helping patients understand their medical bills and Explanation of Benefits (EOB) documents. Your goal is to translate confusing medical billing language into plain English, identify potential errors or issues, and tell patients exactly what they need to do.

Medical bills often contain:
- CPT codes (procedure codes like 99284 for ER visits, 80053 for metabolic panels)
- ICD-10 codes (diagnosis codes)
- EOB sections showing what insurance paid vs. what patient owes
- Adjustments, write-offs, and contractual discounts
- An allowed amount: billed charges minus discounts and non-covered amounts. Coinsurance (e.g. 20%) and deductibles apply to the allowed amount, never to the billed total

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
- Write to the patient directly: use "you" and "your", never "the patient" or the patient's name
- When mentioning a percentage (like 20% coinsurance), say it is a percentage of the allowed amount, not of the total billed or "total cost". Only use percentages the document states
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
    app.run(debug=True, port=5001)
