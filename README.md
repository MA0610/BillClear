# BillClear — Medical Bill Decoder

## Overview

The purpose of this application (BillClear) is to have it read a medical bill or Explanation of Benefits (EOB) and have it return what you owe, what the charges are, billing errors, and suggestions of things to ask billing. The application supports two modes: a local mode using llama3.2 via Ollama (no API key required, data never leaves your machine) and a cloud mode using OpenRouter for the live demo deployment.

---

## The Problems

### Medical billing errors *(chosen)*

Medical bills and EOBs use a lot of different codes and a lot of numbers on top of other technical jargon. This makes it difficult for the average patient to make sure that they aren't getting overbilled due to duplicate charges or other billing issues. I chose to tackle this problem because having dealt with this in the past at places like urgent care billing me twice for something, I found this really hard to stop before I got charged. These bills can sometimes be a lot, especially under the circumstances of being sick.

### Expense report categorization

Finance teams at mid-size companies spend hours manually reviewing and re-categorizing employee expenses submitted with very vague descriptions. Errors can create audit risk and delay things like reimbursements. Existing tools flag anomalies but don't really explain the policy violation or even say how to fix it. I encountered this through a family member who has complained about these tools in the past.

### Lease agreement review

Renters sign leases without understanding non-standard clauses like subletting restrictions, maintenance responsibilities, and more. First time renters such as many of my friends have struggled with fully understanding certain parts of their lease agreement. If untreated this problem can lead to unexpected costs and disputes later down the line.

### Why I chose medical billing

Medical costs can be really expensive and complicated. Things such as the different codes and just the sheer amount of terms and values on a bill can make it difficult to spot mistakes which take money out of the patient's pocket. And even though I am usually very good at catching things, these bills can be very difficult to read and given how expensive medical is I thought it was worth trying to mitigate.

---

## Develop My Approach

### How people handle it today & what a better outcome looks like

Most patients usually either pay the bill and have to call the provider to fix the billing issue (takes a very long time), or they have to carefully read every single statement to fix mistakes that aren't even the patient's fault. A better patient outcome would involve the patient uploading a bill and getting a plain-English summary where every charge is listed and what they need to say to billing in order to get the issues resolved. This would allow for the patient to better understand what they are being billed for and have a better chance at catching pricing errors.

### What my proposed direction looks like

My solution involves local LLM analysis with document-level validation. The model (llama3.2 via Ollama) extracts structured data (charges, amounts, flags), and the backend cross-checks every number against the source text before returning results to the user. I added this level of verification because when working on this the local model would sometimes mess up values occasionally (like instead of 200.50 it might become 200.40), so I added code safeguards to ensure that values stayed correct. The model is mainly used for language understanding while the code handles the validation.

### Other things considered

I considered trying to rely entirely on adjusting the prompts to keep values consistent, but from experience I noticed models can mess numbers up in predictable ways and didn't want to risk it.

### What would make me stop

I would choose to stop if the model's structured output was unreliable to the point that the validation layer couldn't cover it. So if the model hallucinated things like CPT codes that didn't appear in the bill at all, this would make using the model more of a liability than a help — wrong information is way worse than no information at all. In testing I was able to get the model to consistently pull real codes and real amounts, and as stated previously I made sure to use verification in the backend to make it reliable.

---

## Prerequisites

- Python 3.10+
- Node.js 18+

**For local mode (default):** [Ollama](https://ollama.com) with `llama3.2` pulled
```bash
ollama pull llama3.2
```

**For cloud mode:** An [OpenRouter](https://openrouter.ai) API key with `LLM_PROVIDER=openrouter` set

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

## Prototype

### Core workflow

Upload a PDF, txt file, or paste in text and the Flask backend extracts the text. From there the prompt is sent to the local model (llama3.2 via Ollama) and the JSON response is validated against the source document. The React frontend renders the charges table, flags, questions, and the next steps the user should take with billing.

### Representative use case — ER bill with duplicate charge (`sample_bill.txt`)

Input: ER visit billed to Aetna. CPT 96365 (IV Infusion) appears twice.

Expected output:
- Patient responsibility: $1,201.00
- Duplicate flag
- Corrected amount if resolved: $881.00
- Question asking billing to confirm CPT 96365 was performed twice

### Difficult use case — EOB with denial (`sample_eob.txt`)

The document has a denial where a duplicate service was billed twice. The model sees $0 owed on that line. The validation layer reads the denial note, adds a warning flag, and tells the patient not to pay if the provider ends up billing them separately. The model alone would likely miss the distinction between "denied so you owe nothing" and "covered" — which is why this is the difficult case.

### Invalid input

Pasting non-medical text (like a news article) returns a clear message: "This doesn't look like a medical bill or EOB." This stops a broken analysis card from being displayed to the user.

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

**Provider toggle** — set `LLM_PROVIDER` before starting the backend:

```bash
# Local (default)
python app.py

# OpenRouter
LLM_PROVIDER=openrouter OPENROUTER_API_KEY=your_key python app.py

# Groq
LLM_PROVIDER=groq GROQ_API_KEY=your_key python app.py
```

---

## Dependencies

**Backend**
| Package | Purpose |
|---|---|
| `ollama` | Ollama Python client (local mode) |
| `groq` | Groq API client (cloud mode) |
| `openai` | OpenAI-compatible client used for OpenRouter (cloud mode) |
| `flask` | HTTP server |
| `flask-cors` | Cross-origin requests from frontend |
| `pdfplumber` | Extract text from PDF uploads |
| `gunicorn` | Production WSGI server |
| `pytest` (dev) | Test suite |

**Frontend**
| Package | Purpose |
|---|---|
| `react` + `react-dom` | UI framework |
| `vite` + `@vitejs/plugin-react` | Dev server + bundler |

---

## Implemented vs. Deferred

| Feature | Status | Why |
|---|---|---|
| PDF & text extraction | Implemented | Core input path — without it the tool only works for copy-pasted text |
| Structured JSON analysis via local LLM | Implemented | The central problem-solving step |
| Amount validation against source document | Implemented | LLM was misformatting numbers — without this the application has no reason to exist |
| Duplicate, denial, and large-balance flags | Implemented | Highest-value insight for the patient |
| One-click copy of questions to ask billing | Implemented | Reduces friction so users can put it in their notes for later |
| Save as PDF export | Implemented | Patients need a record to bring to a call |
| Test suite (104 tests, pytest) | Implemented | Validation logic is complex enough that manual testing wouldn't catch regressions |
| Optical Character Recognition for scanned bills | Deferred | Requires a vision model — out of scope and likely not needed since digital bills are text-based |
| EOB & bill cross-reference | Deferred | Needs two documents uploaded and cross-referenced — too complex for a prototype |
| CPT code database validation | Deferred | Requires a licensed or public CPT dataset and matching logic — out of scope given time frame |
| Appeal letter generator | Deferred | High value but requires more time and may be a bad idea to put total trust into an LLM |

---

## AI Usage

I used Claude Code to help scaffold and write a majority of the boilerplate for the frontend and backend code. I chose the tech stack and made all the architecture and design choices for the core logic behind the application as well as what I thought should and shouldn't be in scope. I iterated on the prompt structure to produce consistent JSON outputs, verified the sample documents, and tested edge cases on the frontend manually. The validation layer took a majority of my time to get consistently right. The problem framing, solution direction, prompt design, and decision about what to validate through code and what to trust the model with are all my own.

---

## Time Spent

~3 hours 45 minutes
