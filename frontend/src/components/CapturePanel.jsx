export default function CapturePanel({
  captureText,
  setCaptureText,
  captureSource,
  setCaptureSource,
  captureToken,
  setCaptureToken,
  captureSubmitting,
  submitCaptureToSupabase,
  captureStatus,
  hasSupabaseConfig,
}) {
  return (
    <div className="shell">
      <main className="panel capture-panel">
        <header className="hero">
          <p className="eyebrow">Inbox Capture</p>
          <h1>Save vocab from phone</h1>
          <p className="sub">Send words now. Sync on PC later. No same-network requirement.</p>
        </header>

        <section className="card capture-card">
          <form className="stack" onSubmit={submitCaptureToSupabase}>
            <label className="full">Words / expressions (one per line)
              <textarea value={captureText} onChange={(e) => setCaptureText(e.target.value)} placeholder={"団地\n通快\n頑張る"} rows={8} />
            </label>

            <label>Source tag
              <input value={captureSource} onChange={(e) => setCaptureSource(e.target.value)} placeholder="phone" />
            </label>

            <label>Capture passphrase
              <input
                type="password"
                value={captureToken}
                onChange={(e) => setCaptureToken(e.target.value)}
                placeholder="shared secret"
                autoComplete="current-password"
              />
            </label>

            <button className="submit" type="submit" disabled={captureSubmitting}>
              {captureSubmitting ? 'Saving...' : 'Save To Inbox'}
            </button>
          </form>

          <div className="capture-hints">
            <p className="hint">Setup needs Supabase URL + anon key in build env.</p>
            <p className="hint">Set a shared passphrase and enforce it with Supabase RLS on header <code>X-J2A-Capture-Token</code>.</p>
            <p className="hint">Use this page from GitHub Pages or any static host: add <code>?capture=1</code> to URL.</p>
            <p className="hint">Example capture URL: <code>https://YOUR_SITE/?capture=1</code></p>
          </div>

          {captureStatus ? <p className="result-line">{captureStatus}</p> : null}

          {!hasSupabaseConfig ? (
            <details className="advanced-block" open>
              <summary>Missing Supabase config</summary>
              <div className="hint-box">
                Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` before building the static capture site.
                Then enable RLS policy in Supabase requiring request header `x-j2a-capture-token`.
              </div>
            </details>
          ) : null}
        </section>
      </main>
    </div>
  );
}
