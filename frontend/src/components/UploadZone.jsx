import { useState, useRef } from "react";

const SAMPLE_BILL = `VALLEY MEDICAL CENTER
1234 Healthcare Blvd, Los Angeles, CA 90001

PATIENT STATEMENT

Patient: John Smith  |  Account #: VMC-7829034
Date of Service: 09/15/2024  |  Statement Date: 10/01/2024
Insurance: Aetna PPO  |  Member ID: AET-8834729

SERVICES RENDERED:

Date        Description                         CPT Code    Amount
09/15/24    Emergency Room Visit (Level 4)       99284       $2,850.00
09/15/24    Comprehensive Metabolic Panel        80053         $425.00
09/15/24    Complete Blood Count w/ Diff         85025         $180.00
09/15/24    Chest X-Ray, 2 Views                 71046         $650.00
09/15/24    IV Infusion, Initial Hour            96365         $320.00
09/15/24    IV Infusion, Initial Hour            96365         $320.00
09/15/24    Physician Interpretation Fee         93000         $195.00

Total Billed:              $4,940.00
Insurance Payment (Aetna): -$2,847.00
Insurance Adjustment:        -$892.00
AMOUNT DUE:                $1,201.00

Payment due by: 10/31/2024
Questions? Call (213) 555-0150`;

const SAMPLE_EOB = `AETNA HEALTH INSURANCE — Explanation of Benefits
This is not a bill. Keep this for your records.

Member: John Smith  |  Member ID: AET-8834729
Claim #: CLM-2024-09287634  |  Date Processed: 09/28/2024
Provider: Valley Medical Center  |  Date of Service: 09/15/2024

Service Description      Code    Billed     Not Covered   Discount    Plan Paid    Your Cost
ER Visit Level 4         99284   $2,850.00  $0.00         $1,140.00   $1,368.00    $342.00
Metabolic Panel          80053     $425.00  $0.00           $170.00     $204.00     $51.00
Complete Blood Count     85025     $180.00  $0.00            $72.00      $86.40     $21.60
Chest X-Ray 2 Views      71046     $650.00  $0.00           $260.00     $312.00     $78.00
IV Infusion Init Hour    96365     $640.00  $640.00           $0.00       $0.00      $0.00
  DENIAL: Duplicate service — CPT 96365 billed twice, only one unit covered per visit.
Physician Interp Fee     93000     $195.00  $0.00            $78.00      $93.60     $23.40

TOTALS:                          $4,940.00  $640.00       $1,720.00   $2,064.00    $516.00

Deductible: $1,500/year | Applied this claim: $516.00 | YTD met: $984.00

NOTE: The $640.00 IV Infusion denial is a duplicate charge. Do NOT pay this if billed by your provider.`;

export default function UploadZone({ onAnalyze, loading }) {
  const [tab, setTab] = useState("upload");
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleFile = (f) => {
    if (!f) return;
    const allowed = ["application/pdf", "text/plain"];
    if (!allowed.includes(f.type) && !f.name.endsWith(".txt")) {
      alert("Please upload a PDF or .txt file.");
      return;
    }
    setFile(f);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFile(e.dataTransfer.files[0]);
  };

  const canSubmit = tab === "upload" ? !!file : text.trim().length > 30;

  const handleSubmit = () => {
    if (tab === "upload" && file) {
      onAnalyze({ type: "file", file });
    } else if (tab === "paste" && text.trim()) {
      onAnalyze({ type: "text", text: text.trim() });
    }
  };

  return (
    <div className="upload-card">
      <div className="tab-row">
        <button className={`tab ${tab === "upload" ? "active" : ""}`} onClick={() => setTab("upload")}>
          Upload file
        </button>
        <button className={`tab ${tab === "paste" ? "active" : ""}`} onClick={() => setTab("paste")}>
          Paste text
        </button>
      </div>

      <div className="upload-body">
        {tab === "upload" ? (
          <div
            className={`drop-zone ${dragging ? "dragging" : ""} ${file ? "file-selected" : ""}`}
            onClick={() => !file && inputRef.current.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.txt"
              onChange={(e) => handleFile(e.target.files[0])}
            />
            {file ? (
              <>
                <div className="drop-icon">📄</div>
                <div className="file-name">{file.name}</div>
                <div className="file-meta">
                  {(file.size / 1024).toFixed(1)} KB —{" "}
                  <span
                    style={{ color: "var(--blue)", cursor: "pointer" }}
                    onClick={(e) => { e.stopPropagation(); setFile(null); inputRef.current.value = ""; }}
                  >
                    remove
                  </span>
                </div>
              </>
            ) : (
              <>
                <div className="drop-icon">📂</div>
                <h3>Drop your bill here</h3>
                <p>
                  or <strong>click to browse</strong> — PDF or .txt
                </p>
              </>
            )}
          </div>
        ) : (
          <>
            <textarea
              className="paste-area"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste the text from your medical bill or EOB here..."
            />
            <div className="paste-hint">
              Copy the text directly from your bill or EOB document and paste it above.
            </div>
          </>
        )}

        <div className="sample-row">
          <span className="sample-label">Try a sample:</span>
          <button
            className="sample-btn"
            onClick={() => { setTab("paste"); setText(SAMPLE_BILL); }}
          >
            ER bill with duplicate charge
          </button>
          <button
            className="sample-btn"
            onClick={() => { setTab("paste"); setText(SAMPLE_EOB); }}
          >
            Insurance EOB
          </button>
        </div>

        <button
          className="analyze-btn"
          disabled={!canSubmit || loading}
          onClick={handleSubmit}
        >
          {loading ? "Analyzing…" : "Analyze my bill →"}
        </button>
      </div>
    </div>
  );
}
