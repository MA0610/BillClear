# BillClear — Medical Bill Decoder

BillClear takes a medical bill or Explanation of Benefits (EOB), runs it through Claude, and returns a plain-English breakdown: what each charge is, what you actually owe, flagged billing errors, and specific questions to ask your provider.

---

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- An Anthropic API key ([get one here](https://console.anthropic.com))

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

Create a `.env` file in `backend/`:
```
ANTHROPIC_API_KEY=your_key_here
```

Start the Flask server:
```bash
python app.py
```
The backend runs on `http://localhost:5000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Usage

1. Open `http://localhost:5173`
2. Either upload a `.pdf` or `.txt` bill, or paste bill text directly
3. Click **Analyze my bill**
4. Review:
   - **You owe** — patient responsibility at a glance
   - **Potential issues** — flagged billing errors with actions to take
   - **Charges breakdown** — line-by-line table with CPT codes
   - **Questions to ask billing** — copy-paste ready
   - **Next steps** — ordered action list

---

## Sample Data

Two synthetic documents are included in `backend/sample_data/`:

### `sample_bill.txt` — ER bill with duplicate charge
An emergency room visit billed to Aetna PPO. CPT code `96365` (IV Infusion) appears twice for the same date — a common billing error that costs patients ~$320 if unchallenged.

**Expected output:**
- Patient responsibility: ~$1,201
- Flag: duplicate IV Infusion charge (`96365` billed twice)
- Action: call billing and request removal of the second line item

### `sample_eob.txt` — Aetna Explanation of Benefits
The corresponding EOB for the same visit. The insurer already denied the duplicate IV Infusion charge but the patient still needs to verify the provider doesn't bill them for the denied $640.

**Expected output:**
- Document type: EOB
- Flag: denied duplicate charge — patient should not pay the $640 if billed
- Remaining deductible status and next steps

### Invalid / edge case input
Pasting unrelated text (e.g., a recipe, gibberish, or a very short string) will either:
- Return a `document_type: "unknown"` with an explanation, or
- Return a 400 error: "Document appears empty or too short"

---

## Architecture

```
frontend (React/Vite :5173)
    │  POST /api/analyze
    ▼
backend (Flask :5000)
    │  Extract text from PDF (pdfplumber) or accept raw text
    │  Build prompt with document content
    ▼
Anthropic API (claude-sonnet-4-6)
    │  Returns structured JSON analysis
    ▼
backend parses JSON → returns to frontend
    ▼
frontend renders: summary, flags, charges table, next steps
```

**Prompt caching** is enabled on the system prompt via `cache_control: ephemeral`, reducing latency and cost on repeated calls.

---

## Dependencies

**Backend**
| Package | Purpose |
|---|---|
| `anthropic` | Claude API client |
| `flask` | HTTP server |
| `flask-cors` | Cross-origin requests from frontend |
| `pdfplumber` | Extract text from PDF uploads |
| `python-dotenv` | Load `ANTHROPIC_API_KEY` from `.env` |

**Frontend**
| Package | Purpose |
|---|---|
| `react` + `react-dom` | UI framework |
| `vite` + `@vitejs/plugin-react` | Dev server + bundler |

---

## What's implemented vs. mocked

| Feature | Status |
|---|---|
| PDF text extraction | Implemented |
| Plain text / paste input | Implemented |
| Claude analysis with structured JSON output | Implemented |
| Duplicate charge detection | Implemented (via Claude) |
| Charges table with CPT codes | Implemented |
| Questions to ask / next steps | Implemented |
| Drag-and-drop file upload | Implemented |
| Sample data (synthetic) | Included — labeled as synthetic |
| User accounts / history | Not implemented |
| Image/scan OCR | Not implemented (PDF text layer only) |
| Direct insurer API integration | Not implemented |

---

## What I'd investigate next

1. **OCR for scanned bills** — most paper bills get photographed, not digitized. Adding Tesseract or a vision model would cover this.
2. **EOB ↔ bill cross-reference** — if both documents are uploaded, compare what insurance says vs. what the provider is charging.
3. **CPT code database lookup** — flag when a code doesn't match the stated diagnosis (possible upcoding).
4. **Appeal letter generator** — if a flag is found, auto-draft a dispute letter the patient can send.

---

## Time spent

~3.5 hours total:
- 30 min: problem selection and approach
- 45 min: backend (Flask, prompt engineering, edge cases)  
- 60 min: frontend (React components, CSS, upload flow)
- 45 min: sample data, integration testing, README
- 30 min: written submission

## AI usage

Claude Code was used to scaffold and write the majority of the frontend and backend code. I reviewed all output, adjusted the Claude prompt through several iterations to produce consistent structured JSON, verified the sample data produced expected flags, and tested edge cases (empty input, wrong file type, non-medical text). The problem framing, solution direction, and prompt design are my own.
