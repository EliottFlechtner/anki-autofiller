import {useEffect, useMemo, useState} from 'react';
import CapturePanel from './components/CapturePanel';
import SettingsColumn from './components/SettingsColumn';
import StatusColumn from './components/StatusColumn';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';
const SUPABASE_INBOX_TABLE = import.meta.env.VITE_SUPABASE_INBOX_TABLE || 'inbox_items';
const CAPTURE_TOKEN_HEADER = 'X-J2A-Capture-Token';
const CAPTURE_TOKEN_STORAGE_KEY = 'j2a.capture.token';

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
  const isGitHubPages = typeof window !== 'undefined' && window.location.hostname.includes('github.io');
  const captureMode = isGitHubPages || captureParams?.get('capture') === '1';
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
  const [captureToken, setCaptureToken] = useState(() => {
    if (typeof window === 'undefined') {
      return '';
    }
    return window.localStorage.getItem(CAPTURE_TOKEN_STORAGE_KEY) || '';
  });
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

    if (!String(captureToken || '').trim()) {
      setCaptureStatus('Capture passphrase is required.');
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
          [CAPTURE_TOKEN_HEADER]: String(captureToken || '').trim(),
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
    if (typeof window === 'undefined') {
      return;
    }

    const normalized = String(captureToken || '');
    if (normalized) {
      window.localStorage.setItem(CAPTURE_TOKEN_STORAGE_KEY, normalized);
    } else {
      window.localStorage.removeItem(CAPTURE_TOKEN_STORAGE_KEY);
    }
  }, [captureToken]);

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
    return (
      <CapturePanel
        captureText={captureText}
        setCaptureText={setCaptureText}
        captureSource={captureSource}
        setCaptureSource={setCaptureSource}
        captureToken={captureToken}
        setCaptureToken={setCaptureToken}
        captureSubmitting={captureSubmitting}
        submitCaptureToSupabase={submitCaptureToSupabase}
        captureStatus={captureStatus}
        hasSupabaseConfig={Boolean(SUPABASE_URL && SUPABASE_ANON_KEY)}
      />
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
          <StatusColumn
            statusText={statusText}
            progressPct={progressPct}
            formState={formState}
            updateField={updateField}
            reviewSectionVisible={reviewSectionVisible}
            reviewSectionReady={reviewSectionReady}
            reviewIndex={reviewIndex}
            reviewItems={reviewItems}
            goToReviewIndex={goToReviewIndex}
            currentReviewItem={currentReviewItem}
            currentReviewChoice={currentReviewChoice}
            setCurrentReviewChoice={setCurrentReviewChoice}
            addedBatchWords={addedBatchWords}
            addingBatchWords={addingBatchWords}
            requestRelatedWordInBatch={requestRelatedWordInBatch}
            onlyAddValidRows={onlyAddValidRows}
            setOnlyAddValidRows={setOnlyAddValidRows}
            hasMappingValidationIssues={hasMappingValidationIssues}
            hasRowValidationIssues={hasRowValidationIssues}
            reviewValidation={reviewValidation}
            blocksSubmit={blocksSubmit}
            confirmAddToAnki={confirmAddToAnki}
            confirmingAdd={confirmingAdd}
            confirmationJobId={confirmationJobId}
            result={result}
            previewRows={previewRows}
            previewSentenceRows={previewSentenceRows}
          />

          <SettingsColumn
            startGeneration={startGeneration}
            formState={formState}
            updateField={updateField}
            showInboxOverlay={showInboxOverlay}
            inboxItems={inboxItems}
            loadingInbox={loadingInbox}
            handleInboxBellClick={handleInboxBellClick}
            importPendingInboxToWords={importPendingInboxToWords}
            deleteInboxItem={deleteInboxItem}
            showSentenceCardSettings={showSentenceCardSettings}
            showAnkiUrl={showAnkiUrl}
            setShowAnkiUrl={setShowAnkiUrl}
            ankiDecks={ankiDecks}
            ankiModels={ankiModels}
            loadingAnkiOptions={loadingAnkiOptions}
            jobId={jobId}
          />
        </div>
      </main>
    </div>
  );
}
