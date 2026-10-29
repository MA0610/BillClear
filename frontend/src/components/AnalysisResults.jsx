import { useState } from "react";

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button className={`copy-btn ${copied ? "copied" : ""}`} onClick={handleCopy}>
      {copied ? "Copied!" : "Copy all"}
    </button>
  );
}

function fmt(val) {
  if (val === null || val === undefined) return <span className="amount-null">—</span>;
  return `$${Number(val).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function DocTypeBadge({ type }) {
  const labels = {
    medical_bill: "Medical Bill",
    eob: "Explanation of Benefits",
    unknown: "Unknown Document",
  };
  return <span className="doc-type-badge">{labels[type] || type}</span>;
}

function FlagItem({ flag }) {
  return (
    <li className="flag-item">
      <div className={`flag-dot ${flag.severity}`} />
      <div>
        <div className="flag-issue">{flag.issue}</div>
        <div className="flag-explanation">{flag.explanation}</div>
        <span className="flag-action">→ {flag.action}</span>
      </div>
    </li>
  );
}

function calcDuplicates(charges) {
  if (!charges?.length) return { savings: 0, duplicateCodes: new Set() };
  const seen = {};
  const duplicateCodes = new Set();
  let savings = 0;
  for (const c of charges) {
    if (!c.code) continue;
    const key = c.code.trim().toUpperCase();
    if (seen[key]) {
      savings += c.billed_amount || 0;
      duplicateCodes.add(key);
    } else {
      seen[key] = true;
    }
  }
  return { savings, duplicateCodes };
}

function UnknownDocument({ summary, onReset }) {
  return (
    <>
      <div className="results-header">
        <h2>Analysis complete</h2>
        <button className="reset-btn" onClick={onReset}>← Analyze another</button>
      </div>
      <div className="unknown-card">
        <div className="unknown-icon">🤔</div>
        <h3>This doesn't look like a medical bill</h3>
        <p>{summary || "The document you uploaded doesn't appear to be a medical bill or Explanation of Benefits."}</p>
        <p className="unknown-hint">
          Try uploading a hospital bill, doctor's invoice, or EOB from your insurance company.
          Text-layer PDFs and plain text files work best.
        </p>
        <button className="analyze-btn" style={{ marginTop: 0 }} onClick={onReset}>
          Try a different document
        </button>
      </div>
    </>
  );
}

export default function AnalysisResults({ data, onReset }) {
  if (data.document_type === "unknown") {
    return <UnknownDocument summary={data.summary} onReset={onReset} />;
  }

  const warningCount = (data.flags || []).filter((f) => f.severity === "warning").length;
  const { savings: potentialSavings, duplicateCodes } = calcDuplicates(data.charges);

  return (
    <>
      <div className="results-header">
        <h2>Analysis complete</h2>
        <div className="results-actions">
          <button className="export-btn" onClick={() => window.print()}>
            ↓ Save as PDF
          </button>
          <button className="reset-btn" onClick={onReset}>
            ← Analyze another
          </button>
        </div>
      </div>

      {/* Potential savings banner */}
      {potentialSavings > 0 && (
        <div className="savings-banner">
          <div className="savings-amount">
            ${Number(potentialSavings).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="savings-text">
            <strong>Potential overcharge detected</strong>
            <span>Duplicate charge found — verify this amount before paying</span>
          </div>
        </div>
      )}

      {/* Summary + responsibility */}
      <div className="summary-card">
        <div>
          <DocTypeBadge type={data.document_type} />
          <p className="summary-text">{data.summary}</p>
          {data.patient_responsibility?.explanation && (
            <p className="summary-text" style={{ marginTop: 10, fontSize: 13, color: "var(--gray-500)" }}>
              {data.patient_responsibility.explanation}
            </p>
          )}
        </div>
        <div className="responsibility-box">
          <div className="responsibility-label">You owe</div>
          <div className="responsibility-amount">
            {data.patient_responsibility?.amount != null
              ? `$${Number(data.patient_responsibility.amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}`
              : "—"}
          </div>
          <div className="responsibility-note">Patient responsibility</div>
          {potentialSavings > 0 && data.patient_responsibility?.amount != null && (
            <div className="corrected-amount">
              <span className="corrected-label">If resolved:</span>
              <span className="corrected-value">
                ${Number(data.patient_responsibility.amount - potentialSavings).toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Flags */}
      {data.flags?.length > 0 && (
        <div className="section-card">
          <div className="section-header">
            <span className="section-icon">⚠️</span>
            <h3>Potential issues</h3>
            <span className={`badge ${warningCount > 0 ? "warning" : ""}`}>
              {data.flags.length} found
            </span>
          </div>
          <ul className="flag-list">
            {data.flags.map((flag, i) => (
              <FlagItem key={i} flag={flag} />
            ))}
          </ul>
        </div>
      )}

      {/* Charges table */}
      {data.charges?.length > 0 && (
        <div className="section-card">
          <div className="section-header">
            <span className="section-icon">🧾</span>
            <h3>Charges breakdown</h3>
            <span className="badge">{data.charges.length} line items</span>
          </div>
          <div className="charges-table-wrap">
            <table className="charges-table">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Code</th>
                  <th className="right">Billed</th>
                  <th className="right">Ins. Paid</th>
                  <th className="right">You Owe</th>
                </tr>
              </thead>
              <tbody>
                {data.charges.map((c, i) => {
                  const isDuplicate = c.code && duplicateCodes.has(c.code.trim().toUpperCase());
                  return (
                    <tr key={i} className={isDuplicate ? "row-duplicate" : ""}>
                      <td>
                        {c.description}
                        {isDuplicate && <span className="duplicate-tag">duplicate</span>}
                      </td>
                      <td>
                        {c.code ? <span className="code-chip">{c.code}</span> : <span className="amount-null">—</span>}
                      </td>
                      <td className="right amount">{fmt(c.billed_amount)}</td>
                      <td className="right amount">{fmt(c.insurance_paid)}</td>
                      <td className="right amount">{fmt(c.patient_owes)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Questions to ask */}
      {data.questions_to_ask?.length > 0 && (
        <div className="section-card">
          <div className="section-header">
            <span className="section-icon">💬</span>
            <h3>Questions to ask billing</h3>
            <CopyButton text={data.questions_to_ask.map((q, i) => `${i + 1}. ${q}`).join("\n")} />
          </div>
          <div className="list-section">
            <ul>
              {data.questions_to_ask.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Next steps */}
      {data.next_steps?.length > 0 && (
        <div className="section-card">
          <div className="section-header">
            <span className="section-icon">✅</span>
            <h3>Recommended next steps</h3>
          </div>
          <div className="list-section">
            <ol>
              {data.next_steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </div>
        </div>
      )}

      {/* Analysis metadata */}
      {data._meta && (
        <div className="analysis-meta">
          <span className="meta-chip">⚡ {data._meta.model}</span>
          <span className="meta-chip">🕐 {data._meta.elapsed_seconds}s</span>
          <span className="meta-chip">🔒 Local · no data uploaded</span>
        </div>
      )}
    </>
  );
}
