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

export default function AnalysisResults({ data, onReset }) {
  const warningCount = (data.flags || []).filter((f) => f.severity === "warning").length;

  return (
    <>
      <div className="results-header">
        <h2>Analysis complete</h2>
        <button className="reset-btn" onClick={onReset}>
          ← Analyze another
        </button>
      </div>

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
                {data.charges.map((c, i) => (
                  <tr key={i}>
                    <td>{c.description}</td>
                    <td>
                      {c.code ? <span className="code-chip">{c.code}</span> : <span className="amount-null">—</span>}
                    </td>
                    <td className="right amount">{fmt(c.billed_amount)}</td>
                    <td className="right amount">{fmt(c.insurance_paid)}</td>
                    <td className="right amount">{fmt(c.patient_owes)}</td>
                  </tr>
                ))}
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
    </>
  );
}
