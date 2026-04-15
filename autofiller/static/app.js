const h = document.querySelector('form[data-app="anki-autofiller"]');
document.getElementById('progress-wrap');
const s = document.getElementById('progress-text'),
      m = document.getElementById('progress-fill'),
      u = document.getElementById('progress-log'),
      r = document.getElementById('preset'),
      c = document.getElementById('env_file'),
      _ = document.getElementById('load-preset'),
      p = document.getElementById('preset-status'),
      y = document.querySelectorAll('.tab-btn'), w = {
        basic: document.getElementById('tab-basic'),
        advanced: document.getElementById('tab-advanced')
      },
      I =
          [
            'output_path', 'pause_seconds', 'candidate_limit', 'sentence_count',
            'max_workers', 'anki_url', 'deck_name', 'model_name', 'tags',
            'field_word', 'field_meaning', 'field_reading',
            'sentence_deck_name', 'sentence_model_name', 'sentence_front_field',
            'sentence_back_field'
          ],
      b = [
        'include_header', 'include_sentences', 'separate_sentence_cards',
        'include_pitch_accent', 'anki_connect', 'allow_duplicates'
      ];
function l(t, e = !1) {
  p && (p.textContent = t, p.style.color = e ? '#8a2e15' : '')
}
function x(t) {
  for (const e of I) {
    const n = document.getElementById(e);
    !n || !(e in t) || (n.value = t[e] ?? '')
  }
  for (const e of b) {
    const n = document.getElementById(e);
    !n || !(e in t) || (n.checked = !!t[e])
  }
}
function B() {
  return {
    preset: r ? r.value : '', env_file: c ? c.value : ''
  }
}
async function v() {
  l('Loading preset defaults...');
  try {
    const t = B(),
          e = await fetch('/api/settings-preview', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
            },
            body: new URLSearchParams(t)
          });
    if (!e.ok) throw new Error(`HTTP ${e.status}`);
    const n = await e.json();
    x(n.settings || {});
    const i = n.preset || '', o = n.env_file || '', d = [
      i ? `preset ${i}` : 'base defaults', o ? `env file ${o}` : null
    ].filter(Boolean).join(' + ');
    l(`Loaded ${d}. The visible fields now match what will be submitted.`)
  } catch (t) {
    l(`Could not load preset defaults: ${t}`, !0)
  }
}
async function $() {
  s.textContent = 'Starting job...', m.style.width = '0%', u.textContent = '';
  const t = new FormData(h),
        e = await fetch('/api/start', {method: 'POST', body: t});
  if (!e.ok) throw new Error(`HTTP ${e.status}`);
  const i = (await e.json()).job_id,
        o = setInterval(async () => {
          try {
            const a = await (await fetch(`/api/status/${i}`)).json(),
                  f = Math.max(0, a.total || 0),
                  g = Math.max(0, a.completed || 0),
                  E = f > 0 ? Math.floor(g / f * 100) : 0;
            s.textContent = `Status: ${a.status} (${g}/${f})`,
            m.style.width = `${Math.min(100, E)}%`,
            u.textContent = (a.log || []).join(`
`),
            u.scrollTop = u.scrollHeight,
            a.status === 'done' ?
                (clearInterval(o),
                 s.textContent = `${a.message} ${a.anki_summary || ''}`.trim(),
                 m.style.width = '100%') :
                a.status === 'error' &&
                    (clearInterval(o),
                     s.textContent = `Error: ${a.error || 'unknown error'}`)
          } catch (d) {
            clearInterval(o), s.textContent = `Polling error: ${d}`
          }
        }, 700)
}
y.forEach(t => {t.addEventListener('click', () => {
            y.forEach(e => e.classList.remove('active')),
            Object.values(w).forEach(e => e.classList.remove('active')),
            t.classList.add('active'),
            w[t.dataset.tab].classList.add('active')
          })});
_ && _.addEventListener('click', () => {v()});
r && r.addEventListener('change', () => {v()});
c && c.addEventListener('change', () => {
  if (r && !r.value && !c.value.trim()) {
    l('Base defaults are active. Choose a preset or env file to repopulate the form.');
    return
  }
  v()
});
h && h.addEventListener('submit', async t => {
  t.preventDefault();
  try {
    await $()
  } catch (e) {
    s.textContent = `Failed to start: ${e}`
  }
});
l('Base defaults are active. Choose a preset or env file, then load it to repopulate the form.');
