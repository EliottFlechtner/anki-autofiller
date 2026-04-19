export default function StatusColumn({
  statusText,
  progressPct,
  formState,
  updateField,
  reviewSectionVisible,
  reviewSectionReady,
  reviewIndex,
  reviewItems,
  goToReviewIndex,
  currentReviewItem,
  currentReviewChoice,
  setCurrentReviewChoice,
  addedBatchWords,
  addingBatchWords,
  requestRelatedWordInBatch,
  onlyAddValidRows,
  setOnlyAddValidRows,
  hasMappingValidationIssues,
  hasRowValidationIssues,
  reviewValidation,
  blocksSubmit,
  confirmAddToAnki,
  confirmingAdd,
  confirmationJobId,
  result,
  previewRows,
  previewSentenceRows,
}) {
  return (
    <section className="status-column">
      <section className="status-block" aria-live="polite">
        <div className="status-head">{statusText}</div>
        <div className="progress-track"><div className="progress-fill" style={{width: `${progressPct}%`}} /></div>
        {formState.anki_connect ? (
          <label className="toggle" style={{marginTop: '0.45rem'}}>
            <input type="checkbox" checked={formState.review_before_anki} onChange={(e) => updateField('review_before_anki', e.target.checked)} />
            Review generated rows before sending to Anki
          </label>
        ) : null}

        {reviewSectionVisible ? (
          <section className="review-panel review-panel-inline">
            <div className="review-panel-head">
              <div>
                <div className="review-kicker">Review before add</div>
                <h3>Choose the right definition for each word</h3>
                <p className="hint">Pick the candidate you want for this note, then confirm to send the reviewed rows to Anki.</p>
              </div>
              {reviewSectionReady ? (
                <div className="review-progress">
                  {reviewIndex + 1} / {reviewItems.length}
                </div>
              ) : null}
            </div>

            {reviewSectionReady ? (
              <>
                <div className="review-nav">
                  <button type="button" className="ghost" onClick={() => goToReviewIndex(reviewIndex - 1)} disabled={reviewIndex === 0}>
                    Previous
                  </button>
                  <button type="button" className="ghost" onClick={() => goToReviewIndex(reviewIndex + 1)} disabled={reviewIndex >= reviewItems.length - 1}>
                    Next
                  </button>
                </div>

                {currentReviewItem() ? (
                  <article className="review-card">
                    <div className="review-card-top">
                      <div>
                        <div className="review-word-label">Word</div>
                        <div className="review-word" dangerouslySetInnerHTML={{__html: currentReviewItem().word}} />
                        <div className="review-source">Source: {currentReviewItem().source_word}</div>
                      </div>
                      <div className="review-choice-count">
                        {currentReviewChoice() + 1} of {currentReviewItem().options.length}
                      </div>
                    </div>

                    <div className="review-options">
                      {currentReviewItem().options.map((option, optionIndex) => {
                        const isSelected = optionIndex === currentReviewChoice();
                        return (
                          <button
                            key={`${reviewIndex}-${optionIndex}`}
                            type="button"
                            className={`review-option ${isSelected ? 'selected' : ''}`}
                            onClick={() => setCurrentReviewChoice(optionIndex)}
                          >
                            <div className="review-option-head">
                              <span className="review-option-badge">{optionIndex + 1}</span>
                              <span className="review-option-meaning">{option.meaning || '(blank meaning)'}</span>
                            </div>
                            <div className="review-option-reading">{option.reading || '(no reading)'}</div>
                          </button>
                        );
                      })}
                    </div>

                    <div className="review-details">
                      <div><strong>Selected meaning:</strong> {currentReviewItem().options[currentReviewChoice()]?.meaning || '(blank meaning)'}</div>
                      <div><strong>Selected reading:</strong> {currentReviewItem().options[currentReviewChoice()]?.reading || '(no reading)'}</div>
                    </div>

                    {(currentReviewItem().related_words || []).length > 0 ? (
                      <div className="review-related-block">
                        <div className="review-preview-label">Related words from Jisho</div>
                        <div className="review-related-list">
                          {(currentReviewItem().related_words || []).map((related, idx) => (
                            <div className="review-related-item" key={`${currentReviewItem().source_word}-${idx}-${related.word}`}>
                              <div className="review-related-main">
                                <div className="review-related-head"><strong>{related.word}</strong>{related.reading ? ` (${related.reading})` : ''}</div>
                                <div className="review-related-meaning">{related.meaning || '(no meaning)'}</div>
                              </div>
                              {(() => {
                                const isAdded = addedBatchWords.has(related.word);
                                const isAdding = addingBatchWords.has(related.word);
                                return (
                                  <button
                                    type="button"
                                    className={`ghost ${isAdded ? 'disabled' : ''}`}
                                    disabled={isAdded || isAdding}
                                    onClick={() => requestRelatedWordInBatch(related.word)}
                                    style={(isAdded || isAdding) ? {opacity: 0.5, cursor: 'not-allowed'} : {}}
                                  >
                                    {isAdded ? 'Added \u2713' : (isAdding ? 'Adding...' : 'Add To Batch')}
                                  </button>
                                );
                              })()}
                            </div>
                          ))}
                        </div>
                        <p className="hint">Click to fetch Jisho entry and add to your review queue.</p>
                      </div>
                    ) : null}
                  </article>
                ) : null}

                <div className="review-nav review-nav-bottom">
                  <button type="button" className="ghost" onClick={() => goToReviewIndex(reviewIndex - 1)} disabled={reviewIndex === 0}>
                    Previous
                  </button>
                  <button type="button" className="ghost" onClick={() => goToReviewIndex(reviewIndex + 1)} disabled={reviewIndex >= reviewItems.length - 1}>
                    Next
                  </button>
                  <div className="review-submit-options">
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={onlyAddValidRows}
                        onChange={(e) => setOnlyAddValidRows(e.target.checked)}
                      />
                      Only add valid rows (skip invalid)
                    </label>
                    {hasMappingValidationIssues || hasRowValidationIssues ? (
                      <div className="review-validation">
                        <strong>Validation warnings before submit:</strong>
                        {hasMappingValidationIssues ? (
                          <ul className="review-validation-list">
                            {reviewValidation.mappingIssues.map((issue, idx) => (
                              <li key={`mapping-${idx}`}>{issue}</li>
                            ))}
                          </ul>
                        ) : null}
                        {hasRowValidationIssues ? (
                          <ul className="review-validation-list">
                            {reviewValidation.rowIssues.map((issue) => (
                              <li key={`row-${issue.index}`}>
                                <button
                                  type="button"
                                  className="ghost"
                                  onClick={() => goToReviewIndex(issue.index)}
                                >
                                  Row {issue.index + 1} ({issue.word})
                                </button>
                                : {issue.reasons.join(', ')}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        {blocksSubmit ? (
                          <p className="hint">Fix highlighted issues or enable "Only add valid rows" to continue.</p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  <button className="submit" type="button" onClick={confirmAddToAnki} disabled={confirmingAdd || !confirmationJobId || blocksSubmit}>
                    {confirmingAdd ? 'Confirming...' : 'Confirm and Add Reviewed Notes to Anki'}
                  </button>
                </div>
              </>
            ) : (
              <p className="hint">Review mode is enabled, but the reviewed card data has not loaded yet.</p>
            )}
          </section>
        ) : null}

        {result.message ? <p className="result-line">{result.message}</p> : null}
        {result.summary ? <p className="result-line">{result.summary}</p> : null}

        {previewRows.length > 0 && !confirmationJobId ? (
          <details className="advanced-block" open={formState.review_before_anki}>
            <summary>Generated card preview ({previewRows.length} rows)</summary>
            <div className="log-box" style={{maxHeight: '420px', overflow: 'auto'}}>
              {previewRows.map((row, index) => (
                <div key={`${row.word}-${index}`} style={{marginBottom: '1rem', paddingBottom: '0.8rem', borderBottom: '1px solid #e2e8e2'}}>
                  <strong>{index + 1}. <span dangerouslySetInnerHTML={{__html: row.word}} /></strong><br />
                  <div style={{marginTop: '0.35rem'}}>
                    <strong>Reading:</strong>
                    {row.reading && row.reading.includes('<svg') ? (
                      <div dangerouslySetInnerHTML={{__html: row.reading.replace(/color:#f5f5f5/g, 'color:#000000').replace(/fill:#f5f5f5/g, 'fill:#000000').replace(/stroke:#f5f5f5/g, 'stroke:#000000')}} />
                    ) : (
                      <span> {row.reading}</span>
                    )}
                  </div>
                  <div style={{marginTop: '0.2rem'}}>
                    <strong>Meaning:</strong> {row.meaning}
                  </div>
                </div>
              ))}
            </div>
          </details>
        ) : null}

        {previewSentenceRows.length > 0 ? (
          <details className="advanced-block">
            <summary>Generated sentence-card preview ({previewSentenceRows.length} shown)</summary>
            <div className="log-box" style={{maxHeight: '220px', overflow: 'auto'}}>
              {previewSentenceRows.map((row, index) => (
                <div key={`${row.front}-${index}`} style={{marginBottom: '0.7rem'}}>
                  <strong>{index + 1}. {row.front}</strong><br />
                  Back: {row.back}
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </section>
    </section>
  );
}
