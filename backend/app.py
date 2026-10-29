from flask import Flask, request, jsonify
from flask_cors import CORS
import ollama
import pdfplumber
import io
import json
import os

app = Flask(__name__)
CORS(app)

MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

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
  "document_type": "medical_bill",
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
3. DENIED CHARGES: If any charge shows $0 insurance paid with no adjustment, flag it.

Rules:
- Use null for missing numeric values, not 0
- flags array should be empty [] only if truly no issues exist
- Be specific — use actual dollar amounts and codes from the document
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

        result["_meta"] = {"model": MODEL, "elapsed_seconds": elapsed}
        return jsonify(result)

    except ollama.ResponseError as e:
        return jsonify({"error": f"Ollama error: {str(e)}. Is Ollama running?"}), 502
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
