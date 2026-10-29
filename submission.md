# Case Study Submission — Matthew Arboleda

---

## Choose your problem

### Three problems I considered

**Problem 1 — Medical bills are incomprehensible**

I encountered this during a routine urgent care visit. After receiving both a hospital bill and an Explanation of Benefits (EOB) from my insurer, I had two documents using different codes, different dollar amounts, and no clear explanation of what I actually owed or why the numbers differed. I spent an hour cross-referencing CPT codes on Google before calling the billing department — and found a duplicate charge I wouldn't have caught otherwise.

Who experiences it: virtually every American who receives healthcare. The problem isn't rare or edge-case; it's the default experience. A 2022 study by Patients for Fair Compensation found that 80% of medical bills contain at least one error, costing patients an estimated $68B in overpayments annually.

What happens because it remains unsolved: patients overpay, miss billing errors, skip care because they don't understand costs, or get sent to collections on balances they shouldn't have owed.

---

**Problem 2 — Deployment configs drift from their documented state**

During work at a federal contractor, I built tooling that auto-generated deployment folders from client-supplied Helm charts. Before that tool existed, engineers manually reviewed each config — a slow, error-prone process that relied on institutional knowledge. Configs drift over time through hotfixes, manual overrides, and undocumented exceptions. The person who knows why a flag was set a certain way often isn't on the project anymore.

Who experiences it: platform engineers, DevOps teams, and contractors who inherit someone else's infrastructure.

What happens: misconfigs cause deployment failures, create security gaps, and block junior engineers who can't distinguish intentional choices from accidents.

---

**Problem 3 — English pronunciation feedback is inaccessible and expensive**

During my ACM research on phoneme detection for children's speech, I noticed how few affordable tools exist for adult English Language Learners seeking honest, specific pronunciation feedback. Apps like Duolingo are gamified but shallow. Human speech therapists charge $100–250 per hour. Most learners have no feedback loop beyond their own ears.

Who experiences it: adult immigrants, international students, non-native English speakers entering professional environments.

What happens: slow pronunciation acquisition, lack of confidence in professional settings, and no scalable path to improvement without expensive 1:1 coaching.

---

### Why I chose Problem 1

I chose the medical billing problem because the evidence is direct and the people affected have no good recourse today.

**What I observed:** I've personally received bills I couldn't parse without research. The specific duplicate charge in the sample data (CPT `96365` billed twice) reflects a real pattern — IV infusion codes are among the most commonly duplicated charges in ER settings.

**What I'm assuming:** That the pattern holds broadly — my one experience is consistent with published research on billing error rates, but I haven't audited a large sample of bills myself.

**Why it beats the alternatives:** Problem 2 (Helm config review) is real and I could build a strong prototype, but it affects a narrow audience (DevOps engineers) and existing tools partially address it. Problem 3 has the strongest human story but is too close to work I've already published — I'd be retreading my own research rather than solving a new problem.

The medical bill problem is urgent (people are actively losing money), broad (affects nearly everyone), and underserved at the consumer level. Most tools in this space are either insurance-company portals with obvious conflicts of interest, or expensive health advocates. There's no simple, accessible tool that just reads a bill and explains it.

---

## Develop your approach

### How people handle it today

Most patients do one of three things:
1. Pay the bill without reviewing it
2. Call the billing department and ask someone to explain it to them (wait times: 30–90 minutes)
3. Hire a patient advocate or billing specialist (cost: 15–35% of recovered savings)

The few who dig in manually search CPT codes on CMS.gov or Google, cross-reference their EOB, and hope they catch errors before the collections window closes.

### What a better outcome looks like

A patient uploads their bill and gets back, in under a minute: a plain-English summary of every charge, the total they actually owe, flagged anomalies with specific actions to take, and the exact questions to ask when they call billing. No medical knowledge required. No waiting on hold.

### Proposed direction and first step

The direction is an AI-powered document analyzer: extract text from the bill, send it to a language model with a structured prompt, return a JSON object the UI can render clearly.

The **smallest useful first step** is getting the core analysis right: can the model reliably identify a duplicate charge and recommend calling billing? I started there — the sample data was designed to test this specifically — before building the full UI around it.

### Alternative I considered

**A rule-based CPT code parser** — build a database of common codes and flag anomalies algorithmically. This would be more deterministic and auditable than an LLM. I didn't choose it because: (1) the scope of CPT codes is enormous and changes annually; (2) the plain-English explanation layer — "this charge is for an IV drip given in your first hour in the ER" — requires language generation that a lookup table can't provide; (3) for a prototype within a 4-hour window, an LLM approach gets to the useful output faster.

A production system would likely combine both: structured rules for known error patterns, LLM for explanation and edge cases.

### What I'd need to learn

- What percentage of bills arrive as scanned images vs. text-layer PDFs (determines whether OCR is required in v1)
- Whether patients are more likely to catch errors before or after receiving a collections notice (determines urgency framing)
- Whether providers' billing departments respond differently when patients cite specific CPT codes vs. general complaints

### What would make this not worth solving

If the core analysis is unreliable — if the model regularly misidentifies amounts, invents flags that don't exist, or gives advice that increases patient liability — the prototype would cause more harm than the status quo. The right test: give it ten real bills and check accuracy on the "amount you owe" figure specifically. If that number is wrong more than 20% of the time without clear caveats, the trust problem is unsolvable without a fundamentally different approach.

---

## Prototype

**BillClear** — a web application that reads medical bills and EOBs and tells patients exactly what they owe and what to do about it.

### Core workflow

1. User uploads a bill (PDF or .txt) or pastes bill text
2. Flask backend extracts text and sends it to Claude with a structured prompt
3. Claude returns a JSON object: document type, patient responsibility, line-item charges, flags, questions to ask, and next steps
4. React frontend renders the analysis with clear visual hierarchy — the "you owe" number is prominent, warnings are surfaced first

### Representative use case

**Input:** `sample_bill.txt` — an ER visit billed to Aetna PPO totaling $4,940 billed, $1,201 patient responsibility. CPT `96365` (IV Infusion) appears twice for the same date.

**Expected output:**
- Patient responsibility: $1,201
- Flag (warning): duplicate IV Infusion charge — CPT `96365` billed twice, ~$320 overcharge
- Action: "Call billing at (213) 555-0150, reference account VMC-7829034, ask them to remove the duplicate 96365 line item dated 09/15/24"
- Questions: "Can you confirm CPT 96365 was administered twice, or is this a billing error?"

### Difficult / invalid input case

**Input:** Random text ("The quick brown fox jumps over the lazy dog") or a very short string (<30 characters)

**Expected output:**
- 400 error: "Document appears empty or too short. Please check your upload."
- Or: `document_type: "unknown"` with summary: "This does not appear to be a medical bill or EOB..."

### What's implemented vs. deferred

| Feature | Status |
|---|---|
| PDF text extraction (pdfplumber) | Implemented |
| Plain text / paste input | Implemented |
| Structured Claude analysis (JSON) | Implemented |
| Duplicate charge detection | Implemented via Claude |
| Drag-and-drop file upload | Implemented |
| Prompt caching (system prompt) | Implemented |
| OCR for scanned/photographed bills | Deferred |
| EOB ↔ bill cross-reference | Deferred |
| CPT code database validation | Deferred |
| Appeal letter generator | Deferred |

### How AI is used

Claude (`claude-sonnet-4-6`) does the analytical work: it reads the bill, identifies each charge in plain English, flags potential errors, calculates patient responsibility, and generates the questions and next steps. The system prompt is cached with `cache_control: ephemeral` to reduce latency on repeated calls.

I iterated on the prompt over ~6 attempts to get consistent structured JSON output. The key design decision was asking for `null` on missing numeric fields rather than `0`, so the UI can distinguish "insurance paid nothing" from "insurance payment not listed."

### Connection to the broader opportunity

The first step — reliable single-bill analysis — is the prerequisite for everything more valuable: cross-referencing an EOB against the bill it corresponds to, building a longitudinal record of a patient's billing history, auto-generating dispute letters, or integrating with insurance portals directly. The prototype validates that the core analysis is good enough to be useful before any of that infrastructure is built.

---

## Time and AI usage

**Time spent:** ~3.5 hours

**AI tools used:** Claude Code (Anthropic) for scaffolding and writing the majority of the code. I reviewed all generated code, iterated on the Claude prompt through multiple test runs, verified that sample data produced the expected flags, and tested edge cases manually.

**What I checked:** Every component was run in the browser. The analysis prompt was tested against both sample documents and invalid inputs before finalizing. The duplicate charge detection was specifically verified — it was the core hypothesis of the prototype.

**Parts reused from prior work:** None. This project was built from scratch for this submission.

**What I'd investigate next:**
1. OCR support — most paper bills are scanned, not digitized
2. EOB ↔ bill cross-reference — compare insurance's version against the provider's
3. CPT code database — flag when a code doesn't match the stated diagnosis
4. Appeal letter generator — auto-draft a dispute letter when a flag is found
