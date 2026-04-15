const form = document.querySelector('form[data-app="anki-autofiller"]');
const progressWrap = document.getElementById('progress-wrap');
const progressText = document.getElementById('progress-text');
const progressFill = document.getElementById('progress-fill');
const progressLog = document.getElementById('progress-log');
const presetSelect = document.getElementById('preset');
const envFileInput = document.getElementById('env_file');
const loadPresetButton = document.getElementById('load-preset');
const presetStatus = document.getElementById('preset-status');
const buttons = document.querySelectorAll('.tab-btn');
const panels = {
  basic: document.getElementById('tab-basic'),
  advanced: document.getElementById('tab-advanced'),
};

const textFieldIds = [
  'output_path',
  'pause_seconds',
  'candidate_limit',
  'sentence_count',
  'max_workers',
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

const checkboxFieldIds = [
  'include_header',
  'include_sentences',
  'separate_sentence_cards',
  'include_pitch_accent',
  'anki_connect',
  'allow_duplicates',
];

function setStatus(message, isError = false) {
  if (!presetStatus) {
    return;
  }
  presetStatus.textContent = message;
  presetStatus.style.color = isError ? '#8a2e15' : '';
}

function applySettings(settings) {
  for (const fieldId of textFieldIds) {
    const element = document.getElementById(fieldId);
    if (!element || !(fieldId in settings)) {
      continue;
    }
    element.value = settings[fieldId] ?? '';
  }

  for (const fieldId of checkboxFieldIds) {
    const element = document.getElementById(fieldId);
    if (!element || !(fieldId in settings)) {
      continue;
    }
    element.checked = Boolean(settings[fieldId]);
  }
}

function selectedConfig() {
  return {
    preset: presetSelect ? presetSelect.value : '',
    env_file: envFileInput ? envFileInput.value : '',
  };
}

async function loadPresetDefaults() {
  setStatus('Loading preset defaults...');

  try {
    const config = selectedConfig();
    const response = await fetch('/api/settings-preview', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
      body: new URLSearchParams(config),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    applySettings(data.settings || {});

    const appliedPreset = data.preset || '';
    const appliedEnvFile = data.env_file || '';
    const sourceText = [
      appliedPreset ? `preset ${appliedPreset}` : 'base defaults',
      appliedEnvFile ? `env file ${appliedEnvFile}` : null,
    ].filter(Boolean).join(' + ');

    setStatus(`Loaded ${
        sourceText}. The visible fields now match what will be submitted.`);
  } catch (error) {
    setStatus(`Could not load preset defaults: ${error}`, true);
  }
}

async function startJob() {
  progressText.textContent = 'Starting job...';
  progressFill.style.width = '0%';
  progressLog.textContent = '';

  const formData = new FormData(form);
  const startResp = await fetch('/api/start', {
    method: 'POST',
    body: formData,
  });

  if (!startResp.ok) {
    throw new Error(`HTTP ${startResp.status}`);
  }

  const startData = await startResp.json();
  const jobId = startData.job_id;

  const poll = setInterval(async () => {
    try {
      const resp = await fetch(`/api/status/${jobId}`);
      const data = await resp.json();

      const total = Math.max(0, data.total || 0);
      const completed = Math.max(0, data.completed || 0);
      const pct = total > 0 ? Math.floor((completed / total) * 100) : 0;

      progressText.textContent =
          `Status: ${data.status} (${completed}/${total})`;
      progressFill.style.width = `${Math.min(100, pct)}%`;
      progressLog.textContent = (data.log || []).join('\n');
      progressLog.scrollTop = progressLog.scrollHeight;

      if (data.status === 'done') {
        clearInterval(poll);
        progressText.textContent =
            `${data.message} ${data.anki_summary || ''}`.trim();
        progressFill.style.width = '100%';
      } else if (data.status === 'error') {
        clearInterval(poll);
        progressText.textContent = `Error: ${data.error || 'unknown error'}`;
      }
    } catch (error) {
      clearInterval(poll);
      progressText.textContent = `Polling error: ${error}`;
    }
  }, 700);
}

buttons.forEach((button) => {
  button.addEventListener('click', () => {
    buttons.forEach((other) => other.classList.remove('active'));
    Object.values(panels).forEach((panel) => panel.classList.remove('active'));
    button.classList.add('active');
    panels[button.dataset.tab].classList.add('active');
  });
});

if (loadPresetButton) {
  loadPresetButton.addEventListener('click', () => {
    void loadPresetDefaults();
  });
}

if (presetSelect) {
  presetSelect.addEventListener('change', () => {
    void loadPresetDefaults();
  });
}

if (envFileInput) {
  envFileInput.addEventListener('change', () => {
    if (presetSelect && !presetSelect.value && !envFileInput.value.trim()) {
      setStatus(
          'Base defaults are active. Choose a preset or env file to repopulate the form.');
      return;
    }
    void loadPresetDefaults();
  });
}

if (form) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    try {
      await startJob();
    } catch (error) {
      progressText.textContent = `Failed to start: ${error}`;
    }
  });
}

setStatus(
    'Base defaults are active. Choose a preset or env file, then load it to repopulate the form.');
