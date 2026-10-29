# Case Study Submission — Matthew Arboleda

---

## Overview

The purpose of this application (BillClear) is to have it read a medical bill or Explanation of Benefits (EOB) and have it return what you owe, what the charges are, billing errors, and suggestions of things to ask billing. The application supports two modes: a local mode using llama3.2 via Ollama (no API key required, data never leaves your machine) and a cloud mode using OpenRouter, which powers the live demo. The backend has a provider toggle so the same codebase works in both environments.

---

## The Problems

### Medical billing errors *(chosen)*

Medical bills and EOBs use a lot of different codes and a lot of numbers on top of other technical jargon. This makes it difficult for the average patient to make sure that they aren't getting overbilled due to duplicate charges or other billing issues. I chose to tackle this problem because having dealt with this in the past at places like urgent care billing me twice for something, I found this really hard to stop before I got charged. These bills can sometimes be a lot, especially under the circumstances of being sick.

### Expense report categorization

Finance teams at mid-size companies spend hours manually reviewing and re-categorizing employee expenses submitted with very vague descriptions. Errors can create audit risk and delay things like reimbursements. Existing tools flag the anomalies but don't really explain the policy violation or even say how to fix it. I encountered this through a family member who has complained about these tools in the past.

### Lease agreement review

Renters sign leases without understanding non-standard clauses like subletting restrictions, maintenance responsibilities, and more. First time renters such as many of my friends have struggled with fully understanding certain parts of their lease agreement. If untreated this problem can lead to unexpected costs and disputes later down the line.

### Why I chose medical billing

Medical costs can be really expensive and complicated. Things such as the different codes and just the sheer amount of terms and values on a bill can make it difficult to spot mistakes which take money out of the patient's pocket. And even though I am usually very good at catching things, these bills can be very difficult to read and given how expensive medical is I thought it was worth trying to mitigate.

---

## Develop My Approach

### How people handle it today & what a better outcome looks like

Most patients usually either pay the bill and have to call the provider to fix the billing issue (takes a very long time), or they have to carefully read every single statement to fix mistakes that aren't even the patient's fault. A better patient outcome would involve the patient uploading a bill and getting a plain-English summary where every charge is listed and what they need to say to billing in order to get the issues resolved. This would allow for the patient to better understand what they are being billed for and have a better chance at catching these pricing errors.

### What my proposed direction looks like

My solution involves local LLM analysis with document-level validation. The model (llama3.2 via Ollama) extracts structured data (charges, amounts, flags), and the backend cross-checks every number against the source text before returning results to the user. I added this level of verification because when working on this the local model would sometimes mess up values occasionally (like instead of 200.50 it might become 200.40), so I added code safeguards to ensure that values stayed correct. The model is mainly used for language understanding while the code portion handles the validation.

### Other things considered

I considered trying to rely entirely on adjusting the prompts to keep values consistent, but from experience I noticed models can sometimes mess numbers up in predictable ways and didn't want to risk it.

### What would make me stop

I would choose to stop if the model's structured output was unreliable to the point that the validation layer couldn't cover it. So if the model hallucinated things like CPT codes that didn't appear in the bill at all, this would make using the model more of a liability than a help — wrong information is way worse than no information at all. In testing I was able to get the model to consistently pull real codes and real amounts, and as stated previously I made sure to use verification in the backend to make it reliable.

---

## Prototype

### Core workflow

Upload a PDF, txt file, or paste in text and the Flask backend extracts the text. The prompt is sent to the configured LLM (llama3.2 via Ollama locally, or a Llama 3.1 model via OpenRouter on the live demo) and the JSON response is validated against the source document. The React frontend renders the charges table, flags, questions, and the next steps the user should take with billing. The footer shows which model and provider handled the analysis.

### Representative use case — ER bill with duplicate charge (`sample_bill.txt`)

For the use case I used synthetic data of an ER bill with a duplicate charge.

Input: ER visit billed to Aetna. CPT 96365 (IV Infusion) appears twice.

Expected output:
- Patient responsibility: $1,201.00
- Duplicate flag
- Corrected amount if resolved: $881.00
- Question asking billing to confirm CPT 96365 was performed twice

### Difficult use case — EOB with denial (`sample_eob.txt`)

For this case the document has a denial where a duplicate service was billed twice. The model sees that $0 is owed on that line. The validation layer reads the denial note, adds a warning flag, and tells the patient not to pay if the provider ends up billing them separately. The model alone would probably miss the distinction between "denied so you owe nothing" and "covered" — which is why this is the difficult case.

### Invalid input

Pasting non-medical text (like a news article) returns a clear message: "This doesn't look like a medical bill or EOB." This stops a broken analysis card from being displayed to the user.

### Implemented vs. Deferred

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
| Appeal letter generator | Deferred | High value but would require more time and may be generally a bad idea to put total trust into an LLM |

---

## AI Usage

I used Claude Code to help scaffold and write a majority of the boilerplate for the frontend and backend code. I chose the tech stack and made all the architecture and design choices for the core logic behind the application as well as what I thought should and shouldn't be in scope. I iterated on the prompt structure to produce consistent JSON outputs, verified the sample documents which I had Claude make, and tested edge cases on the frontend manually. The validation layer took a majority of my time in order to get consistently right. The problem framing, solution direction, prompt design, and decision about what to validate through code and what to trust the model with are all my own. I would be more than happy to talk more about how I productively use LLMs to improve my workflow!

---

## Time Spent

~3 hours 45 minutes
