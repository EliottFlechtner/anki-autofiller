import {expect, test} from '@playwright/test';

function bootstrapPayload() {
  return {
    defaults: {
      words: '',
      inbox_item_ids: '',
      pause_seconds: '0',
      candidate_limit: '2',
      sentence_count: '1',
      max_workers: '2',
      pitch_accent_theme: 'dark',
      furigana_format: 'ruby',
      anki_url: 'http://127.0.0.1:8765',
      deck_name: 'Default',
      model_name: 'Jisho2Anki::Vocab (Kanji-Reading-Translation)',
      tags: 'jisho2anki',
      field_word: 'Word',
      field_meaning: 'Translation',
      field_reading: 'Reading',
      sentence_deck_name: 'Default',
      sentence_model_name: 'Basic',
      sentence_front_field: 'Front',
      sentence_back_field: 'Back',
      include_header: false,
      include_sentences: false,
      separate_sentence_cards: false,
      include_pitch_accent: false,
      include_furigana: false,
      anki_connect: true,
      review_before_anki: true,
      allow_duplicates: false,
    },
    presets: [],
  };
}

async function stubBaseEndpoints(page, {inboxItems = [], ankiOptions} = {}) {
  let pendingItems = [...inboxItems];

  await page.route('**/api/bootstrap', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(bootstrapPayload()),
    });
  });

  await page.route('**/api/anki-options**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
          ankiOptions || {
            models: [
              'Jisho2Anki::Vocab (Kanji-Reading-Translation)',
              'Another Model',
            ],
            decks: ['Default', 'Mining'],
          },
          ),
    });
  });

  await page.route('**/api/inbox/pending', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({items: pendingItems}),
    });
  });

  await page.route('**/api/inbox/delete/*', async (route) => {
    const id =
        Number.parseInt(route.request().url().split('/').pop() || '', 10);
    pendingItems = pendingItems.filter((item) => item.id !== id);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ok: true}),
    });
  });
}

test(
    'loads Anki model/deck options into destination fields', async ({page}) => {
      await stubBaseEndpoints(page, {
        ankiOptions: {
          models: ['Model Alpha', 'Model Beta'],
          decks: ['Default', 'Core2k'],
        },
      });

      await page.goto('/');

      await expect(page.getByText('Loaded Anki model/deck lists.'))
          .toBeVisible();

      const modelSelect = page.getByLabel('Model name');
      await expect(modelSelect).toContainText('Model Alpha');
      await expect(modelSelect).toContainText('Model Beta');

      await expect(page.getByLabel('Deck name (destination)'))
          .toHaveValue('Default');
    });

test('generate, review, and confirm sends selected choices', async ({page}) => {
  await stubBaseEndpoints(page);

  let confirmRequestBody = null;

  await page.route('**/api/start', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({job_id: 'job-1'}),
    });
  });

  await page.route('**/api/status/job-1', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'done',
        completed: 2,
        total: 2,
        message: 'Built 2 rows',
        anki_summary: 'Queued review confirmation.',
        requires_confirmation: true,
        preview: [
          {word: '食べる', meaning: 'to eat', reading: 'たべる'},
          {word: '勉強', meaning: 'study', reading: 'べんきょう'},
        ],
        review_items: [
          {
            word: '食べる',
            source_word: '食べる',
            selected_index: 0,
            options: [
              {meaning: 'to eat', reading: 'たべる', reading_preview: 'たべる'},
              {
                meaning: 'to consume food',
                reading: 'たべる',
                reading_preview: 'たべる'
              },
            ],
            related_words: [],
          },
          {
            word: '勉強',
            source_word: '勉強',
            selected_index: 0,
            options: [
              {
                meaning: 'study',
                reading: 'べんきょう',
                reading_preview: 'べんきょう'
              },
            ],
            related_words: [],
          },
        ],
      }),
    });
  });

  await page.route('**/api/confirm/job-1', async (route) => {
    confirmRequestBody = JSON.parse(route.request().postData() || '{}');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({anki_summary: 'Added 2 vocab notes.'}),
    });
  });

  await page.goto('/');

  await page.getByLabel('Words (one per line)').fill('食べる\n勉強');
  await page.getByRole('button', {name: 'Generate Cards'}).click();

  await expect(page.getByRole('heading', {
    name: 'Choose the right definition for each word'
  })).toBeVisible();

  await page.getByRole('button', {name: /to consume food/}).click();
  await page
      .getByRole('button', {name: 'Confirm and Add Reviewed Notes to Anki'})
      .click();

  await expect(page.getByText('Added 2 vocab notes.')).toBeVisible();
  await expect(page.getByText('Reviewed notes were added to Anki.'))
      .toBeVisible();

  expect(confirmRequestBody).not.toBeNull();
  expect(confirmRequestBody.only_add_valid_rows).toBe(true);
  expect(confirmRequestBody.choices).toEqual([1, 0]);
});

test('inbox overlay supports delete and import flows', async ({page}) => {
  await stubBaseEndpoints(page, {
    inboxItems: [
      {id: 101, text: '団地', source: 'phone'},
      {id: 102, text: '通快', source: 'phone'},
    ],
  });

  await page.goto('/');

  const openInbox = page.getByRole('button', {name: /Open inbox/});
  await expect(openInbox).toBeVisible();
  await openInbox.click();

  await expect(page.getByRole('dialog', {
    name: 'Pending inbox items'
  })).toBeVisible();

  await page.getByLabel('Delete inbox item').first().click();
  await expect(page.getByText('Deleted inbox item 101.')).toBeVisible();

  await page.getByRole('button', {name: 'Import'}).click();

  await expect(page.getByText('Imported 1 new word(s) from inbox.'))
      .toBeVisible();
  await expect(page.getByLabel('Words (one per line)')).toHaveValue('通快');
});
