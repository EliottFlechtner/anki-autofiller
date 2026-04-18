import {useEffect, useMemo, useState} from 'react';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';
const SUPABASE_INBOX_TABLE = import.meta.env.VITE_SUPABASE_INBOX_TABLE || 'inbox_items';
const CAPTURE_KEY = import.meta.env.VITE_CAPTURE_KEY || '';

const TEXT_FIELDS = [
  'words',
  'inbox_item_ids',
  'output_path',
  'pause_seconds',
  'candidate_limit',
  'sentence_count',
  'max_workers',
  'pitch_accent_theme',
  'furigana_format',
  'anki_url',
  'deck_name',
  'model_name',
  'tags',
  'field_word',
  'field_meaning',
  'field_reading',
  'sentence_deck_name',
  'sentence_model_name',
  'sentence_front_field',
  'sentence_back_field',
];

const CHECK_FIELDS = [
  'include_header',
  'include_sentences',
  'separate_sentence_cards',
  'include_pitch_accent',
  'include_furigana',
  'anki_connect',
  'review_before_anki',
  'allow_duplicates',
];

function parseBoolish(value, fallback = false) {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['1', 'true', 'yes', 'on'].includes(normalized)) {
      return true;
    }
    if (['0', 'false', 'no', 'off'].includes(normalized)) {
      return false;
    }
  }
  return fallback;
}

function buildInitialState(defaults) {
  const state = {};
  for (const key of TEXT_FIELDS) {
    state[key] = key in defaults ? String(defaults[key] ?? '') : '';
  }
  for (const key of CHECK_FIELDS) {
    const fallback = key === 'review_before_anki';
    state[key] = parseBoolish(defaults[key], fallback);
  }
  return state;
}

function toFormData(formState) {
  const data = new FormData();

  for (const key of TEXT_FIELDS) {
    if (key === 'output_path') {
      continue;
    }
    data.append(key, formState[key] ?? '');
  }

  // Send explicit boolean values so unchecked toggles override preset defaults.
  for (const key of CHECK_FIELDS) {
    data.append(key, formState[key] ? 'true' : 'false');
  }

  return data;
}

export default function App() {
  const captureParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const captureMode = captureParams?.get('capture') === '1';
  const captureRequestKey = (captureParams?.get('k') || '').trim();
  const captureAuthorized = !captureMode || !CAPTURE_KEY || captureRequestKey === CAPTURE_KEY;
  const [bootLoaded, setBootLoaded] = useState(false);
  const [formState, setFormState] = useState(() => buildInitialState({}));
  const [statusText, setStatusText] = useState('Bootstrapping settings...');
  const [progress, setProgress] = useState({status: 'idle', completed: 0, total: 0, log: []});
  const [result, setResult] = useState({message: '', summary: ''});
  const [previewRows, setPreviewRows] = useState([]);
  const [previewSentenceRows, setPreviewSentenceRows] = useState([]);
  const [reviewItems, setReviewItems] = useState([]);
  const [reviewChoices, setReviewChoices] = useState([]);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [addedBatchWords, setAddedBatchWords] = useState(new Set());
  const [addingBatchWords, setAddingBatchWords] = useState(new Set());
  const [confirmationJobId, setConfirmationJobId] = useState('');
  const [confirmingAdd, setConfirmingAdd] = useState(false);
  const [onlyAddValidRows, setOnlyAddValidRows] = useState(true);
  const [jobId, setJobId] = useState('');

  const [showAnkiUrl, setShowAnkiUrl] = useState(false);
  const [ankiModels, setAnkiModels] = useState([]);
  const [ankiDecks, setAnkiDecks] = useState([]);
  const [loadingAnkiOptions, setLoadingAnkiOptions] = useState(false);
  const [inboxItems, setInboxItems] = useState([]);
  const [importedInboxIds, setImportedInboxIds] = useState(new Set());
  const [showInboxOverlay, setShowInboxOverlay] = useState(false);
  const [loadingInbox, setLoadingInbox] = useState(false);
  const [captureText, setCaptureText] = useState('');
  const [captureSource, setCaptureSource] = useState('phone');
  const [captureStatus, setCaptureStatus] = useState('');
  const [captureSubmitting, setCaptureSubmitting] = useState(false);

  function stripHtmlText(value) {
    if (!value) {
      return '';
    }
    return String(value).replace(/<[^>]*>/g, '').trim();
  }

  function buildFallbackReviewItems(rows) {
    if (!Array.isArray(rows) || rows.length === 0) {
      return [];
    }
    return rows.map((row) => {
      const word = String(row.word || '');
      const reading = String(row.reading || '');
      const meaning = String(row.meaning || '');
      return {
        word,
        source_word: stripHtmlText(word),
        selected_index: 0,
        options: [
          {
            meaning,
            reading: stripHtmlText(reading),
            reading_preview: reading,
          },
        ],
      };
    });
  }

  async function submitCaptureToSupabase(event) {
    event.preventDefault();
    if (!captureAuthorized) {
      setCaptureStatus('Capture is locked. Add the correct key in URL (?capture=1&k=...).');
      return;
    }

    const lines = String(captureText || '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);

    if (lines.length === 0) {
      setCaptureStatus('Enter at least one word.');
      return;
    }

    if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
      setCaptureStatus('Supabase config missing. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY, then rebuild.');
      return;
    }

    setCaptureSubmitting(true);
    setCaptureStatus('Saving to inbox...');

    try {
      const payload = lines.map((text) => ({
        text,
        source: captureSource || 'phone',
        received_at_ms: Date.now(),
        created_at_ms: Date.now(),
        status: 'pending',
      }));

      const resp = await fetch(`${SUPABASE_URL.replace(/\/$/, '')}/rest/v1/${SUPABASE_INBOX_TABLE}`, {
        method: 'POST',
        headers: {
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
          'Content-Type': 'application/json',
          Prefer: 'return=minimal',
        },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.message || body.error || `HTTP ${resp.status}`);
      }

      setCaptureStatus(`Saved ${lines.length} item(s).`);
      setCaptureText('');
    } catch (error) {
      setCaptureStatus(`Save failed: ${error}`);
    } finally {
      setCaptureSubmitting(false);
    }
  }

  useEffect(() => {
    let isMounted = true;
    fetch('/api/bootstrap')
        .then((resp) => resp.json())
        .then((payload) => {
          if (!isMounted) {
            return;
          }
          const defaults = payload.defaults || {};
          const state = buildInitialState(defaults);
          state.words = '';
          state.inbox_item_ids = '';
          state.review_before_anki = true;
          setFormState(state);
          setStatusText('Base defaults loaded.');
          setBootLoaded(true);
        })
        .catch((error) => {
          if (!isMounted) {
            return;
          }
          setStatusText(`Failed to load defaults: ${error}`);
          setBootLoaded(true);
        });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const resp = await fetch(`/api/status/${jobId}`);
        const data = await resp.json();
        const total = Math.max(0, data.total || 0);
        const completed = Math.max(0, data.completed || 0);
        const log = data.log || [];

        setProgress({
          status: data.status || 'running',
          completed,
          total,
          log,
        });

        if (data.status === 'done') {
          const statusPreviewRows = Array.isArray(data.preview) ? data.preview : [];
          const statusReviewItems = Array.isArray(data.review_items) ? data.review_items : [];
          let effectiveReviewItems = statusReviewItems;

          if (data.requires_confirmation && effectiveReviewItems.length === 0) {
            try {
              const reviewResp = await fetch(`/api/review-items/${jobId}`);
              const reviewPayload = await reviewResp.json();
              if (reviewResp.ok && Array.isArray(reviewPayload.review_items) && reviewPayload.review_items.length > 0) {
                effectiveReviewItems = reviewPayload.review_items;
              }
            } catch (_error) {
              // Fall through to local fallback below.
            }
          }

          if (data.requires_confirmation && effectiveReviewItems.length === 0 && statusPreviewRows.length > 0) {
            effectiveReviewItems = buildFallbackReviewItems(statusPreviewRows);
          }

          setResult({message: data.message || '', summary: data.anki_summary || ''});
          setPreviewRows(statusPreviewRows);
          setPreviewSentenceRows(data.sentence_preview || []);
          setReviewItems(effectiveReviewItems);
          setReviewChoices(effectiveReviewItems.map((item) => item.selected_index || 0));
          setReviewIndex(0);
          setAddedBatchWords(new Set());
          setAddingBatchWords(new Set());
          setConfirmationJobId(data.requires_confirmation ? jobId : '');
          if (!data.requires_confirmation) {
            setFormState((prev) => ({...prev, inbox_item_ids: ''}));
            fetchInboxPending();
          }
          setStatusText('Generation complete.');
          setJobId('');
        }

        if (data.status === 'error') {
          setResult({message: `Error: ${data.error || 'unknown error'}`, summary: ''});
          setPreviewRows([]);
          setPreviewSentenceRows([]);
          setReviewItems([]);
          setReviewChoices([]);
          setReviewIndex(0);
          setAddedBatchWords(new Set());
          setAddingBatchWords(new Set());
          setConfirmationJobId('');
          setStatusText('Generation failed.');
          setJobId('');
        }
      } catch (error) {
        setResult({message: `Polling error: ${error}`, summary: ''});
        setStatusText('Polling failed.');
        setJobId('');
      }
    }, 700);

    return () => clearInterval(interval);
  }, [jobId]);

  const progressPct = useMemo(() => {
    if (!progress.total) {
      return 0;
    }
    return Math.min(100, Math.floor((progress.completed / progress.total) * 100));
  }, [progress.completed, progress.total]);

  function updateField(key, value) {
    setFormState((prev) => ({...prev, [key]: value}));
  }

  async function startGeneration(event) {
    event.preventDefault();

    if (!formState.words.trim()) {
      setStatusText('Please add at least one word.');
      return;
    }

    setResult({message: '', summary: ''});
    setPreviewRows([]);
    setPreviewSentenceRows([]);
    setReviewItems([]);
    setReviewChoices([]);
    setReviewIndex(0);
    setAddedBatchWords(new Set());
    setAddingBatchWords(new Set());
    setConfirmationJobId('');
    setProgress({status: 'starting', completed: 0, total: 0, log: []});
    setStatusText('Starting generation...');

    try {
      const resp = await fetch('/api/start', {
        method: 'POST',
        body: toFormData(formState),
      });
      const payload = await resp.json();
      setJobId(payload.job_id || '');
      setStatusText('Generation in progress...');
    } catch (error) {
      setStatusText(`Failed to start generation: ${error}`);
    }
  }

  async function fetchInboxPending({silent = false} = {}) {
    if (!silent) {
      setLoadingInbox(true);
    }
    try {
      const resp = await fetch('/api/inbox/pending');
      const payload = await resp.json();
      if (!resp.ok) {
        throw new Error(payload.error || 'failed to fetch inbox');
      }
      const rows = Array.isArray(payload.items) ? payload.items : [];
      const items = rows.filter((item) => {
        const id = Number.parseInt(String(item.id), 10);
        return Number.isInteger(id) && id > 0 && !importedInboxIds.has(id);
      });
      setInboxItems(items);
      return items;
    } catch (error) {
      setStatusText(`Could not load inbox: ${error}`);
      setInboxItems([]);
      return [];
    } finally {
      if (!silent) {
        setLoadingInbox(false);
      }
    }
  }

  async function handleInboxBellClick() {
    if (!showInboxOverlay) {
      const items = await fetchInboxPending({silent: true});
      if (!Array.isArray(items) || items.length === 0) {
        setShowInboxOverlay(false);
        return;
      }
    }
    setShowInboxOverlay((prev) => !prev);
  }

  function importPendingInboxToWords() {
    if (!Array.isArray(inboxItems) || inboxItems.length === 0) {
      setStatusText('Inbox empty.');
      return;
    }

    const itemsToImport = [...inboxItems];
    const incomingWords = itemsToImport
      .map((item) => String(item.text || '').trim())
      .filter(Boolean);
    const incomingIds = itemsToImport
      .map((item) => Number.parseInt(String(item.id), 10))
      .filter((value) => Number.isInteger(value) && value > 0);

    setFormState((prev) => {
      const currentWords = String(prev.words || '')
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
      const existingSet = new Set(currentWords);

      const uniqueIncoming = incomingWords.filter((word) => !existingSet.has(word));
      const mergedWords = [...currentWords, ...uniqueIncoming];

      const existingIds = String(prev.inbox_item_ids || '')
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean)
        .map((part) => Number.parseInt(part, 10))
        .filter((value) => Number.isInteger(value) && value > 0);
      const mergedIds = Array.from(new Set([...existingIds, ...incomingIds]));

      setStatusText(`Imported ${uniqueIncoming.length} new word(s) from inbox.`);
      return {
        ...prev,
        words: mergedWords.join('\n'),
        inbox_item_ids: mergedIds.join(','),
      };
    });

    // Hide imported rows from inbox UI immediately and keep unselected items.
    setImportedInboxIds((prev) => new Set([...prev, ...incomingIds]));
    setInboxItems((prev) => prev.filter((item) => {
      const id = Number.parseInt(String(item.id), 10);
      return !(Number.isInteger(id) && id > 0 && incomingIds.includes(id));
    }));
  }

  async function deleteInboxItem(itemId) {
    try {
      const resp = await fetch(`/api/inbox/delete/${itemId}`, {
        method: 'DELETE',
      });
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        throw new Error(payload.error || `HTTP ${resp.status}`);
      }
      setInboxItems((prev) => prev.filter((item) => item.id !== itemId));
      setStatusText(`Deleted inbox item ${itemId}.`);
    } catch (error) {
      setStatusText(`Could not delete inbox item: ${error}`);
    }
  }

  async function confirmAddToAnki() {
    if (!confirmationJobId) {
      return;
    }

    setConfirmingAdd(true);
    setStatusText('Submitting reviewed notes to Anki...');
    try {
      const resp = await fetch(`/api/confirm/${confirmationJobId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          choices: reviewChoices,
          only_add_valid_rows: onlyAddValidRows,
        }),
      });
      const payload = await resp.json();
      if (!resp.ok) {
        throw new Error(payload.error || 'confirm request failed');
      }
      setResult((prev) => ({...prev, summary: payload.anki_summary || prev.summary}));
      setConfirmationJobId('');
      setReviewItems([]);
      setReviewChoices([]);
      setReviewIndex(0);
      setAddedBatchWords(new Set());
      setAddingBatchWords(new Set());
      setFormState((prev) => ({...prev, inbox_item_ids: ''}));
      fetchInboxPending();
      setStatusText('Reviewed notes were added to Anki.');
    } catch (error) {
      setStatusText(`Could not confirm add: ${error}`);
    } finally {
      setConfirmingAdd(false);
    }
  }

  async function fetchAnkiOptions() {
    setLoadingAnkiOptions(true);
    try {
      const query = new URLSearchParams({anki_url: formState.anki_url || ''});
      const resp = await fetch(`/api/anki-options?${query.toString()}`);
      const payload = await resp.json();
      if (!resp.ok) {
        throw new Error(payload.error || 'could not fetch Anki options');
      }
      setAnkiModels(payload.models || []);
      setAnkiDecks(payload.decks || []);
      setStatusText('Loaded Anki model/deck lists.');
    } catch (error) {
      setStatusText(`Could not load Anki options: ${error}`);
      setAnkiModels([]);
      setAnkiDecks([]);
    } finally {
      setLoadingAnkiOptions(false);
    }
  }

  useEffect(() => {
    if (confirmationJobId && !formState.review_before_anki && reviewItems.length > 0 && reviewChoices.length > 0) {
      confirmAddToAnki();
    }
  }, [confirmationJobId, formState.review_before_anki, reviewItems.length, reviewChoices.length]);

  useEffect(() => {
    if (!formState.anki_connect) {
      setAnkiModels([]);
      setAnkiDecks([]);
      return;
    }
    fetchAnkiOptions();
  }, [formState.anki_connect, formState.anki_url, showAnkiUrl]);

  useEffect(() => {
    fetchInboxPending({silent: true});
    const interval = setInterval(() => {
      fetchInboxPending({silent: true});
    }, 2000);
    return () => clearInterval(interval);
  }, [importedInboxIds]);

  useEffect(() => {
    if (inboxItems.length === 0) {
      setShowInboxOverlay(false);
    }
  }, [inboxItems.length]);

  function updateReviewChoice(rowIndex, selectedIndex) {
    setReviewChoices((prev) => {
      const next = [...prev];
      next[rowIndex] = selectedIndex;
      return next;
    });
  }

  function selectedOptionForRow(rowIndex) {
    const item = reviewItems[rowIndex];
    if (!item || !item.options || item.options.length === 0) {
      return null;
    }
    const selectedIndex = Number.isInteger(reviewChoices[rowIndex]) ? reviewChoices[rowIndex] : (item.selected_index || 0);
    if (selectedIndex < 0 || selectedIndex >= item.options.length) {
      return item.options[0];
    }
    return item.options[selectedIndex];
  }

  function currentReviewItem() {
    return reviewItems[reviewIndex] || null;
  }

  function currentReviewChoice() {
    const item = currentReviewItem();
    if (!item || !item.options || item.options.length === 0) {
      return 0;
    }
    const selectedIndex = Number.isInteger(reviewChoices[reviewIndex])
      ? reviewChoices[reviewIndex]
      : (item.selected_index || 0);
    if (selectedIndex < 0 || selectedIndex >= item.options.length) {
      return 0;
    }
    return selectedIndex;
  }

  function setCurrentReviewChoice(selectedIndex) {
    updateReviewChoice(reviewIndex, selectedIndex);
  }

  function goToReviewIndex(nextIndex) {
    const clamped = Math.max(0, Math.min(reviewItems.length - 1, nextIndex));
    setReviewIndex(clamped);
  }



  async function requestRelatedWordInBatch(word) {
    const cleanWord = String(word || '').trim();
    if (!cleanWord) {
      return;
    }
    if (addedBatchWords.has(cleanWord)) {
      setStatusText(`Already added to batch: ${cleanWord}`);
      return;
    }
    if (addingBatchWords.has(cleanWord)) {
      return;
    }
    if (!confirmationJobId) {
      setStatusText('Cannot add to batch right now. Please regenerate and try again.');
      return;
    }

    setAddingBatchWords((prev) => new Set([...prev, cleanWord]));
    setStatusText(`Adding to review batch: ${cleanWord}`);

    try {
      const resp = await fetch(`/api/review-add-word/${confirmationJobId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({word: cleanWord}),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || `HTTP ${resp.status}`);
      }

      if (!data.review_item) {
        setStatusText(`No Jisho entry found for: ${cleanWord}`);
        return;
      }

      const selectedIndex = Number.isInteger(data.selected_index) ? data.selected_index : 0;
      const selectedOption = data.review_item.options?.[selectedIndex] || data.review_item.options?.[0] || {meaning: '', reading_preview: '', reading: ''};

      setReviewItems((prev) => [...prev, data.review_item]);
      setReviewChoices((prev) => [...prev, selectedIndex]);
      setPreviewRows((prev) => [
        ...prev,
        {
          word: data.review_item.word || cleanWord,
          meaning: selectedOption.meaning || '',
          reading: selectedOption.reading_preview || selectedOption.reading || '',
        },
      ]);
      setAddedBatchWords((prev) => new Set([...prev, cleanWord]));
      setStatusText(`Added to batch: ${cleanWord}`);
    } catch (error) {
      setStatusText(`Error adding ${cleanWord} to batch: ${error}`);
    } finally {
      setAddingBatchWords((prev) => {
        const next = new Set(prev);
        next.delete(cleanWord);
        return next;
      });
    }
  }

  function sanitizeLogLine(line) {
    return line.replace(/<!-- accent_start -->[\s\S]*?<!-- accent_end -->/g, '[pitch SVG omitted]');
  }

  const showSentenceCardSettings = formState.include_sentences && formState.separate_sentence_cards;
  const reviewSectionVisible = formState.review_before_anki && previewRows.length > 0;
  const reviewSectionReady = reviewSectionVisible && reviewItems.length > 0;
  const reviewValidation = useMemo(() => {
    const mappingIssues = [];
    if (formState.anki_connect) {
      if (!String(formState.field_word || '').trim()) {
        mappingIssues.push('Word field mapping is empty.');
      }
      if (!String(formState.field_meaning || '').trim()) {
        mappingIssues.push('Meaning field mapping is empty.');
      }
      if (!String(formState.field_reading || '').trim()) {
        mappingIssues.push('Reading field mapping is empty.');
      }
      if (showSentenceCardSettings) {
        if (!String(formState.sentence_front_field || '').trim()) {
          mappingIssues.push('Sentence front field mapping is empty.');
        }
        if (!String(formState.sentence_back_field || '').trim()) {
          mappingIssues.push('Sentence back field mapping is empty.');
        }
      }
    }

    const rowIssues = [];
    for (let index = 0; index < reviewItems.length; index += 1) {
      const item = reviewItems[index] || {};
      const options = Array.isArray(item.options) ? item.options : [];
      if (options.length === 0) {
        rowIssues.push({
          index,
          word: String(item.source_word || item.word || `Row ${index + 1}`),
          reasons: ['no candidate options'],
        });
        continue;
      }

      const selectedIndexRaw = Number.isInteger(reviewChoices[index])
        ? reviewChoices[index]
        : (item.selected_index || 0);
      const selectedIndex = (selectedIndexRaw >= 0 && selectedIndexRaw < options.length)
        ? selectedIndexRaw
        : 0;
      const selectedOption = options[selectedIndex] || {};

      const reasons = [];
      if (!String(selectedOption.meaning || '').trim()) {
        reasons.push('missing meaning');
      }
      if (!String(selectedOption.reading || '').trim()) {
        reasons.push('missing reading');
      }

      if (reasons.length > 0) {
        rowIssues.push({
          index,
          word: String(item.source_word || item.word || `Row ${index + 1}`),
          reasons,
        });
      }
    }

    return {mappingIssues, rowIssues};
  }, [
    formState.anki_connect,
    formState.field_word,
    formState.field_meaning,
    formState.field_reading,
    formState.sentence_front_field,
    formState.sentence_back_field,
    showSentenceCardSettings,
    reviewItems,
    reviewChoices,
  ]);
  const hasRowValidationIssues = reviewValidation.rowIssues.length > 0;
  const hasMappingValidationIssues = reviewValidation.mappingIssues.length > 0;
  const blocksSubmit = hasMappingValidationIssues || (!onlyAddValidRows && hasRowValidationIssues);

  if (captureMode) {
    if (!captureAuthorized) {
      return (
        <div className="shell">
          <main className="panel capture-panel">
            <header className="hero">
              <p className="eyebrow">Inbox Capture</p>
              <h1>Capture is locked</h1>
              <p className="sub">This page requires a valid capture key in the URL.</p>
            </header>

            <section className="card capture-card">
              <p className="hint">Use <code>?capture=1&amp;k=YOUR_KEY</code>.</p>
            </section>
          </main>
        </div>
      );
    }

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

              <button className="submit" type="submit" disabled={captureSubmitting}>
                {captureSubmitting ? 'Saving...' : 'Save To Inbox'}
              </button>
            </form>

            <div className="capture-hints">
              <p className="hint">Setup needs Supabase URL + anon key in build env.</p>
              <p className="hint">Optional lock: set <code>VITE_CAPTURE_KEY</code> and open with <code>?capture=1&amp;k=YOUR_KEY</code>.</p>
              <p className="hint">Use this page from GitHub Pages or any static host: add <code>?capture=1</code> to URL.</p>
              <p className="hint">Example capture URL: <code>https://YOUR_SITE/?capture=1</code></p>
            </div>

            {captureStatus ? <p className="result-line">{captureStatus}</p> : null}

            {!SUPABASE_URL || !SUPABASE_ANON_KEY ? (
              <details className="advanced-block" open>
                <summary>Missing Supabase config</summary>
                <div className="hint-box">
                  Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` before building the static capture site.
                  Then enable RLS insert policy for pending inbox rows in Supabase.
                </div>
              </details>
            ) : null}
          </section>
        </main>
      </div>
    );
  }

  if (!bootLoaded) {
    return <div className="shell"><div className="status">Loading app...</div></div>;
  }

  return (
    <div className="shell">
      <main className="panel">
        <header className="hero">
          <p className="eyebrow">Jisho2Anki</p>
          <h1>Simple Japanese Card Generator</h1>
        </header>

        <div className="main-columns">
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
        </div>
      </main>
    </div>
  );
}
