import { useState } from "react";
import UploadZone from "./components/UploadZone";
import AnalysisResults from "./components/AnalysisResults";

export default function App() {
  const [state, setState] = useState("idle"); // idle | loading | results | error
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  const handleAnalyze = async ({ type, file, text }) => {
    setState("loading");
    setError(null);

    try {
      let response;

      if (type === "file") {
        const form = new FormData();
        form.append("file", file);
        response = await fetch(`${import.meta.env.VITE_API_URL ? import.meta.env.VITE_API_URL + "/analyze" : "/api/analyze"}`, { method: "POST", body: form });
      } else {
        response = await fetch(`${import.meta.env.VITE_API_URL ? import.meta.env.VITE_API_URL + "/analyze" : "/api/analyze"}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
      }

      let data;
      const rawText = await response.text();
      try {
        data = JSON.parse(rawText);
      } catch {
        throw new Error(
          response.ok
            ? "Server returned an unexpected response. Is the backend running?"
            : `Server error (${response.status}). Is the Flask backend running on port 5001?`
        );
      }

      if (!response.ok) {
        throw new Error(data.error || "Analysis failed. Please try again.");
      }

      setResults(data);
      setState("results");
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
      setState("error");
    }
  };

  const handleReset = () => {
    setState("idle");
    setResults(null);
    setError(null);
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="logo-link" onClick={handleReset} title="Back to start">
            <div className="logo-icon">💊</div>
            <div className="logo-text">
              Bill<span>Clear</span>
            </div>
          </div>
          <span className="tagline">Medical bill decoder</span>
          <div className="privacy-badge">
            <span className="privacy-icon">🔒</span>
            Runs locally — your bill never leaves your computer
          </div>
        </div>
      </header>

      <main className="main">
        {state !== "results" && (
          <div className="hero">
            <h1>Understand your medical bill</h1>
            <p>
              Upload a bill or EOB — BillClear reads it, flags billing errors,
              and tells you exactly what you owe and what to do next.
            </p>
          </div>
        )}

        {(state === "idle" || state === "error") && (
          <>
            {state === "error" && (
              <div className="error-card">
                <span className="error-icon">⚠</span>
                <p>{error}</p>
              </div>
            )}
            <UploadZone onAnalyze={handleAnalyze} loading={false} />
          </>
        )}

        {state === "loading" && (
          <div className="loading-card">
            <div className="spinner" />
            <h3>Reading your bill…</h3>
            <p>Extracting charges, checking for errors, building your summary.</p>
          </div>
        )}

        {state === "results" && results && (
          <AnalysisResults data={results} onReset={handleReset} />
        )}
      </main>

      <footer className="footer">
        <p className="disclaimer">
          BillClear is an informational tool and does not constitute medical, legal, or financial advice.
          Always verify findings with your provider and insurer.
          <br />
          <span style={{ marginTop: 4, display: "block" }}>
            Powered by Ollama (llama3.2) · Runs 100% locally · Prototype — synthetic sample data included
          </span>
        </p>
      </footer>
    </div>
  );
}
