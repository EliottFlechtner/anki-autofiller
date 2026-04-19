export default function SettingsColumn({
  startGeneration,
  formState,
  updateField,
  showInboxOverlay,
  inboxItems,
  loadingInbox,
  handleInboxBellClick,
  importPendingInboxToWords,
  deleteInboxItem,
  showSentenceCardSettings,
  showAnkiUrl,
  setShowAnkiUrl,
  ankiDecks,
  ankiModels,
  loadingAnkiOptions,
  jobId,
}) {
  return (
    <form onSubmit={startGeneration} className="stack settings-column">
      <div className="settings-grid">
        <div className="settings-subcolumn">
          <section className="card input-output-card">
            <div className="card-title-row">
              <h2>Input & Output</h2>
              <button
                type="button"
                className={`inbox-bell ${inboxItems.length === 0 ? 'is-empty' : ''}`}
                aria-label={`Open inbox (${inboxItems.length} pending)`}
                onClick={handleInboxBellClick}
                disabled={loadingInbox}
              >
                <span className="inbox-bell-icon" aria-hidden="true">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-hidden="true" focusable="false">
                    <rect width="256" height="256" fill="none"/>
                    <path d="M221.8,175.94C216.25,166.38,208,139.33,208,104a80,80,0,1,0-160,0c0,35.34-8.26,62.38-13.81,71.94A16,16,0,0,0,48,200H88.81a40,40,0,0,0,78.38,0H208a16,16,0,0,0,13.8-24.06ZM128,216a24,24,0,0,1-22.62-16h45.24A24,24,0,0,1,128,216Z"/>
                  </svg>
                </span>
                {inboxItems.length > 0 ? <span className="inbox-bell-count">{inboxItems.length}</span> : null}
              </button>
            </div>
            <div className="grid two">
              <label className="full">Words (one per line)
                <textarea
                  className="words-textarea"
                  value={formState.words}
                  onChange={(e) => updateField('words', e.target.value)}
                  placeholder={'食べる\n勉強\n試合'}
                />
              </label>

            </div>

            {showInboxOverlay && inboxItems.length > 0 ? (
              <div className="inbox-overlay" role="dialog" aria-label="Pending inbox items">
                <div className="inbox-head">
                  <strong>Inbox</strong>
                  <span className="hint">{inboxItems.length} pending</span>
                </div>
                <div className="inbox-actions">
                  <button type="button" className="ghost" onClick={importPendingInboxToWords} disabled={inboxItems.length === 0}>
                    Import
                  </button>
                </div>
                <div className="inbox-list">
                  {inboxItems.slice(0, 12).map((item) => (
                    <div key={item.id} className="inbox-item">
                      <span className="inbox-item-text">{item.text}</span>
                      <button
                        type="button"
                        className="inbox-item-delete"
                        aria-label="Delete inbox item"
                        onClick={() => deleteInboxItem(item.id)}
                        title="Delete item"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-hidden="true" focusable="false">
                          <rect width="256" height="256" fill="none"/>
                          <path d="M216,48H176V40a24,24,0,0,0-24-24H104A24,24,0,0,0,80,40v8H40a8,8,0,0,0,0,16h8V208a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V64h8a8,8,0,0,0,0-16ZM112,168a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Zm48,0a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Zm0-120H96V40a8,8,0,0,1,8-8h48a8,8,0,0,1,8,8Z" fill="currentColor"/>
                        </svg>
                      </button>
                    </div>
                  ))}
                  {inboxItems.length > 12 ? <p className="hint">Showing first 12 items.</p> : null}
                </div>
              </div>
            ) : null}
          </section>

          <section className="card">
            <h2>Content Options</h2>
            <div className="toggle-list">
              <label className="toggle">
                <input type="checkbox" checked={formState.include_sentences} onChange={(e) => updateField('include_sentences', e.target.checked)} />
                Include example sentences
              </label>
              <label className="toggle">
                <input type="checkbox" checked={formState.include_pitch_accent} onChange={(e) => updateField('include_pitch_accent', e.target.checked)} />
                Include pitch accent SVG
              </label>
              <label className="toggle">
                <input type="checkbox" checked={formState.include_furigana} onChange={(e) => updateField('include_furigana', e.target.checked)} />
                Add furigana to word field
              </label>
            </div>

            <div className="inline-options">
              {formState.include_pitch_accent ? (
                <div className="pitch-theme-row">
                  <span className="pitch-theme-label">Pitch Accent SVG Color</span>
                  <select
                    className="pitch-theme-select"
                    value={formState.pitch_accent_theme}
                    onChange={(e) => updateField('pitch_accent_theme', e.target.value)}
                  >
                    <option value="dark">light</option>
                    <option value="light">dark</option>
                  </select>
                </div>
              ) : null}
              {formState.include_furigana ? (
                <label>Furigana format
                  <select value={formState.furigana_format} onChange={(e) => updateField('furigana_format', e.target.value)}>
                    <option value="ruby">ruby</option>
                    <option value="anki">anki</option>
                  </select>
                </label>
              ) : null}
            </div>
            {formState.include_pitch_accent ? (
              <p className="hint">Foreground only; background stays transparent.</p>
            ) : null}

            {formState.include_sentences ? (
              <div className="inline-options">
                <label>Sentence count per word
                  <input type="number" min="0" step="1" value={formState.sentence_count} onChange={(e) => updateField('sentence_count', e.target.value)} />
                </label>
                <label className="toggle">
                  <input type="checkbox" checked={formState.separate_sentence_cards} onChange={(e) => updateField('separate_sentence_cards', e.target.checked)} />
                  Create separate sentence cards
                </label>
              </div>
            ) : null}
          </section>
        </div>

        <div className="settings-subcolumn">
          <section className="card">
            <h2>Destination</h2>
            <label className="toggle">
              <input type="checkbox" checked={formState.anki_connect} onChange={(e) => updateField('anki_connect', e.target.checked)} />
              Send notes directly to AnkiConnect
            </label>

            {formState.anki_connect ? (
              <>
                <label className="toggle">
                  <input type="checkbox" checked={showAnkiUrl} onChange={(e) => setShowAnkiUrl(e.target.checked)} />
                  Use custom AnkiConnect URL
                </label>

                <div className="grid two">
                  {showAnkiUrl ? (
                    <label>AnkiConnect URL
                      <input value={formState.anki_url} onChange={(e) => updateField('anki_url', e.target.value)} />
                    </label>
                  ) : null}
                  <label>Deck name (destination)
                    <input
                      value={formState.deck_name}
                      onChange={(e) => updateField('deck_name', e.target.value)}
                      list="deck-name-options"
                    />
                    <datalist id="deck-name-options">
                      {[...new Set(ankiDecks)].filter(Boolean).map((deck) => (
                        <option key={deck} value={deck} />
                      ))}
                    </datalist>
                  </label>
                  <label>Model name
                    <select value={formState.model_name} onChange={(e) => updateField('model_name', e.target.value)}>
                      {[...new Set([formState.model_name, ...ankiModels])].filter(Boolean).map((model) => (
                        <option key={model} value={model}>{model}</option>
                      ))}
                    </select>
                  </label>
                  <label>Tags (comma-separated)
                    <input value={formState.tags} onChange={(e) => updateField('tags', e.target.value)} />
                  </label>
                </div>
                {loadingAnkiOptions ? <p className="hint">Loading model/deck options from Anki...</p> : null}
                <label className="toggle">
                  <input type="checkbox" checked={formState.allow_duplicates} onChange={(e) => updateField('allow_duplicates', e.target.checked)} />
                  Allow duplicates in Anki
                </label>

                <details className="advanced-block">
                  <summary>Edit note field mapping</summary>
                  <div className="grid two">
                    <label>Word field
                      <input value={formState.field_word} onChange={(e) => updateField('field_word', e.target.value)} />
                    </label>
                    <label>Meaning field
                      <input value={formState.field_meaning} onChange={(e) => updateField('field_meaning', e.target.value)} />
                    </label>
                    <label>Reading field
                      <input value={formState.field_reading} onChange={(e) => updateField('field_reading', e.target.value)} />
                    </label>
                  </div>
                </details>

                {showSentenceCardSettings ? (
                  <details className="advanced-block" open>
                    <summary>Sentence card note mapping</summary>
                    <div className="grid two">
                      <label>Sentence deck
                        <input value={formState.sentence_deck_name} onChange={(e) => updateField('sentence_deck_name', e.target.value)} />
                      </label>
                      <label>Sentence model
                        <input value={formState.sentence_model_name} onChange={(e) => updateField('sentence_model_name', e.target.value)} />
                      </label>
                      <label>Sentence front field
                        <input value={formState.sentence_front_field} onChange={(e) => updateField('sentence_front_field', e.target.value)} />
                      </label>
                      <label>Sentence back field
                        <input value={formState.sentence_back_field} onChange={(e) => updateField('sentence_back_field', e.target.value)} />
                      </label>
                    </div>
                  </details>
                ) : null}
              </>
            ) : (
              <p className="hint">Cards will only be written to the TSV file.</p>
            )}
          </section>

          <section className="card advanced-block">
            <h2>Performance tuning</h2>
            <div className="grid three">
              <label>Pause seconds
                <input type="number" min="0" step="0.1" value={formState.pause_seconds} onChange={(e) => updateField('pause_seconds', e.target.value)} />
              </label>
              <label>Candidate limit
                <input type="number" min="1" step="1" value={formState.candidate_limit} onChange={(e) => updateField('candidate_limit', e.target.value)} />
              </label>
              <label>Max workers
                <input type="number" min="1" step="1" value={formState.max_workers} onChange={(e) => updateField('max_workers', e.target.value)} />
              </label>
            </div>
          </section>

          <button className="submit" type="submit" disabled={Boolean(jobId)}>
            {jobId ? 'Generating...' : 'Generate Cards'}
          </button>
        </div>
      </div>
    </form>
  );
}
