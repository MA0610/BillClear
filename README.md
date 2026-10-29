# BillClear — Medical Bill Decoder

BillClear takes a medical bill or Explanation of Benefits (EOB), runs it through a local AI model, and returns a plain-English breakdown: what each charge is, what you actually owe, flagged billing errors, and specific questions to ask your provider.

Runs 100% locally — no API key, no data leaves your machine.

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com) with `llama3.2` pulled

Install Ollama and pull the model:
```bash
ollama pull llama3.2
```

---

## Setup

### Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

---

## Running the app

You need three things running at the same time:

**1. Ollama** (if not already running as a background service):
```bash
ollama serve
```

**2. Backend** (from `backend/` with venv activated):
```bash
python app.py
```
Runs on `http://localhost:5001`

**3. Frontend** (from `frontend/`):
```bash
npm run dev
```
Runs on `http://localhost:5173`

Open `http://localhost:5173` in your browser.

---

## Running tests

From `backend/` with the venv activated:

```bash
pip install -r requirements-dev.txt
pytest
```

The suite has 104 tests:

- **Unit tests** (`tests/test_utils.py`, 78 tests) — amount parsing, thousands-separator fixes, row-level validation, and flag checks against the sample documents, including the PDF. No Ollama needed.
- **API tests** (`tests/test_api.py`, 26 tests) — health check and input validation, plus end-to-end analysis of both text samples through the real model. Tests marked `ai` require Ollama running with `llama3.2`.

To run only the tests that don't need Ollama:

```bash
pytest -m "not ai"
```

---

## Usage

1. Upload a `.pdf` or `.txt` bill, or paste bill text directly
2. Click **Analyze my bill**
3. Review the results:
   - **Potential overcharge banner** — flags duplicate charges with the disputed dollar amount
   - **You owe** — patient responsibility with a corrected amount if an overcharge is found
   - **Potential issues** — specific warnings with actions to take
   - **Charges breakdown** — line-by-line table with CPT codes; duplicate rows highlighted in yellow
   - **Questions to ask billing** — copy-paste ready with one click
   - **Next steps** — ordered action list
4. Click **↓ Save as PDF** to export the full analysis

---

## Sample Data

Three synthetic documents are in `backend/sample_data/`. Use the sample buttons in the app to load the two text samples instantly; upload the PDF with **Upload file**.

### `sample_bill.txt` — ER bill with duplicate charge
An emergency room visit billed to Aetna PPO. CPT code `96365` (IV Infusion) appears twice for the same date — a common billing error.

**Expected output:**
- Patient responsibility: $1,201.00
- Potential overcharge: $320.00
- Corrected amount if resolved: $881.00
- Flag: duplicate IV Infusion charge with yellow row highlight
- Questions and next steps for contesting the charge

### `sample_eob.txt` — Aetna Explanation of Benefits
The corresponding EOB for the same visit. The insurer denied the duplicate IV Infusion charge.

**Expected output:**
- Document type: EOB
- Flag: denied duplicate — patient should not pay the $640 if billed by provider
- Deductible status and next steps

### `sample_eob_urgent_care.pdf` — Summit Health Plan EOB (PDF)
An urgent care visit for a fictional insurer, laid out as a real PDF table. Exercises the PDF upload path: pdfplumber collapses the table's columns to single spaces, so amounts are matched to columns by header name. The insurer denied a $45 Dexamethasone Injection (`J1100`).

**Expected output:**
- Document type: EOB
- Patient responsibility: $88.20 (20% coinsurance on the allowed amount)
- Charges: 5 line items; `J1100` shows $0.00 paid and $0.00 owed
- Flag: one warning for the denied `J1100` charge — no duplicate or large-balance flags

### Invalid input
Click the **Invalid input** sample button to demo the edge case. Pasting non-medical text returns a `"This doesn't look like a medical bill"` card instead of broken results.

---

## Architecture

```
frontend (React/Vite :5173)
    │  POST /api/analyze
    ▼
backend (Flask :5001)
    │  Extract text from PDF (pdfplumber) or accept raw text
    │  Build structured prompt
    ▼
Ollama (llama3.2, localhost:11434)
    │  Returns JSON analysis via format="json" (temperature 0)
    ▼
backend validates amounts against the source document:
    │  - fixes thousands-separator mistakes (1.201 → 1201)
    │  - replaces patient responsibility with the document's stated total
    │  - checks each charge against the row carrying its CPT code
    │    (columns matched by header name, e.g. "Plan Paid", "Your Cost")
    ▼
backend validates flags:
    │  - drops duplicate flags with no repeated code or "duplicate" in the document
    │  - large-balance flag only when patient responsibility is over $500
    │  - adds a warning for every charge the document says was denied
    ▼
backend attaches _meta (model, elapsed time) → returns to frontend
    ▼
frontend renders: savings banner, summary, flags, charges table,
                  questions (copy button), next steps, PDF export
```

To use a different Ollama model, set the environment variable before starting the backend:
```bash
OLLAMA_MODEL=llama3.1:8b python app.py
```

---

## Dependencies

**Backend**
| Package | Purpose |
|---|---|
| `ollama` | Ollama Python client |
| `flask` | HTTP server |
| `flask-cors` | Cross-origin requests from frontend |
| `pdfplumber` | Extract text from PDF uploads |
| `pytest` (dev) | Test suite |

**Frontend**
| Package | Purpose |
|---|---|
| `react` + `react-dom` | UI framework |
| `vite` + `@vitejs/plugin-react` | Dev server + bundler |

---

## What's implemented vs. deferred

| Feature | Status |
|---|---|
| PDF text extraction | Implemented |
| Plain text / paste input | Implemented |
| Duplicate charge detection | Implemented |
| Charges table with CPT codes + duplicate highlighting | Implemented |
| Potential savings + corrected amount | Implemented |
| Questions to ask (one-click copy) | Implemented |
| Save as PDF export | Implemented |
| Invalid input handling | Implemented |
| Amount validation against source document | Implemented |
| Flag validation (duplicates, large balance, denied charges) | Implemented |
| Automated test suite (pytest) | Implemented |
| Sample data (synthetic, labeled) | Included |
| OCR for scanned/photographed bills | Not implemented |
| EOB ↔ bill cross-reference | Not implemented |
| CPT code database validation | Not implemented |
| Appeal letter generator | Not implemented |

---

## What I'd investigate next

1. **OCR for scanned bills** — most paper bills are photographed, not digitized. Tesseract or a vision model (llava via Ollama) would cover this.
2. **EOB ↔ bill cross-reference** — upload both documents and compare what the insurer paid vs. what the provider is charging.
3. **CPT code database** — flag when a code doesn't match the stated diagnosis (possible upcoding).
4. **Appeal letter generator** — auto-draft a dispute letter when a flag is found.

---

## Time spent

~4 hours total

## AI usage

Claude Code was used to scaffold and write the majority of the frontend and backend code. I reviewed all output, iterated on the prompt to produce consistent structured JSON, verified sample data produced the expected flags, and tested edge cases manually. Model output is checked by an automated pytest suite (see [Running tests](#running-tests)). The problem framing, solution direction, system architecture, and prompt design are my own, and I directed the testing and validation work, including deciding which issues to fix.
