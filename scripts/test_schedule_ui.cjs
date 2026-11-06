const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

// Execute the actual schedule controller with a small DOM, fixed clock and feeds.
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const source = html.slice(html.indexOf('  var scheduleRequest = null;'), html.indexOf('\n  function activate()'));
const now = Date.parse('2026-11-06T01:40:00Z');
const primary = 'https://raw.githubusercontent.com/alexjunholee/alexjunholee.github.io/schedule-data/schedule.json';
const key = 'public-schedule.v1';

class Element {
  constructor(tag = 'div') {
    this.tag = tag;
    this.children = [];
    this.attributes = {};
    this.hidden = true;
    this.className = '';
    this.textContent = '';
  }
  appendChild(child) { this.children.push(child); }
  replaceChildren(fragment) { this.children = fragment.children.slice(); }
  setAttribute(name, value) { this.attributes[name] = value; }
}

function snapshot(generatedAt = '2026-11-06T01:35:00Z', overrides = {}) {
  return {
    generatedAt,
    windowStart: '2026-11-02T00:00:00+09:00',
    windowEnd: '2026-12-07T00:00:00+09:00',
    busy: [{start: '2026-11-06T04:00:00Z', end: '2026-11-06T08:00:00Z', allDay: false}],
    ...overrides,
  };
}

function browser({saved, storageUnavailable = false} = {}) {
  const grid = new Element();
  const notice = new Element('p');
  const storage = new Map(saved ? [[key, JSON.stringify(saved)]] : []);
  let feeds = {};
  const context = vm.createContext({
    document: {
      getElementById: id => id === 'schedule-grid' ? grid : notice,
      createElement: tag => new Element(tag),
      createDocumentFragment: () => new Element('fragment'),
    },
    Date: class extends Date { static now() { return now; } },
    localStorage: {
      getItem(name) {
        if (storageUnavailable) throw Error('storage unavailable');
        return storage.get(name) || null;
      },
      setItem(name, value) {
        if (storageUnavailable) throw Error('storage unavailable');
        storage.set(name, value);
      },
    },
    fetch: async url => {
      const value = await feeds[url];
      if (value instanceof Error || value === undefined) throw value || Error('offline');
      return {ok: true, json: async () => value};
    },
    AbortController, setTimeout, clearTimeout,
  });
  vm.runInContext(source, context);
  return {
    grid, notice, storage,
    start(next) {
      feeds = next;
      vm.runInContext('loadSchedule()', context);
      return vm.runInContext('scheduleRequest', context);
    },
  };
}

function descendants(element) {
  return element.children.flatMap(child => [child, ...descendants(child)]);
}
function events(page) { return descendants(page.grid).filter(el => el.className === 'schedule-event'); }

test('a valid snapshot older than six hours remains visible with its update time', async () => {
  const page = browser();
  await page.start({[primary]: snapshot('2026-11-05T09:40:00Z')});
  assert.equal(page.grid.hidden, false);
  assert.equal(events(page).length, 1);
  assert.match(page.notice.textContent, /갱신이 지연/);
  assert.match(page.notice.textContent, /2026\.11\.05 18:40/);
});

test('a failed refresh preserves the already rendered schedule', async () => {
  const page = browser();
  await page.start({[primary]: snapshot()});
  const before = events(page).map(el => el.attributes['aria-label']);
  const pending = page.start({});
  assert.equal(page.grid.hidden, false);
  await pending;
  assert.deepEqual(events(page).map(el => el.attributes['aria-label']), before);
  assert.match(page.notice.textContent, /마지막으로 확인한 일정/);
});

test('saved data renders immediately and survives a completely offline revisit', async () => {
  const page = browser({saved: snapshot()});
  const pending = page.start({});
  assert.equal(page.grid.hidden, false);
  assert.equal(events(page).length, 1);
  await pending;
  assert.match(page.notice.textContent, /불러오지 못해/);
});

test('the deployed JSON is available as a fallback on the first visit', async () => {
  const page = browser();
  await page.start({'schedule.json': snapshot()});
  assert.equal(events(page).length, 1);
  assert.equal(page.grid.hidden, false);
  assert.match(page.notice.textContent, /불러오지 못해/);
});

test('a slower, older deployed response cannot overwrite the current snapshot', async () => {
  const page = browser();
  let finish;
  const delayed = new Promise(resolve => { finish = resolve; });
  const pending = page.start({[primary]: snapshot(), 'schedule.json': delayed});
  finish(snapshot('2026-11-05T09:40:00Z', {busy: []}));
  await pending;
  assert.equal(events(page).length, 1);
  assert.equal(JSON.parse(page.storage.get(key)).generatedAt, '2026-11-06T01:35:00Z');
});

test('an invalid replacement cannot erase the last valid snapshot', async () => {
  for (const changes of [
    {windowStart: 'bad date'},
    {windowEnd: 'bad date'},
    {generatedAt: '2026-11-07T01:40:00Z'},
    {busy: [{start: 'bad date', end: 'bad date', allDay: false}]},
    {busy: null},
  ]) {
    const page = browser({saved: snapshot()});
    await page.start({[primary]: snapshot(undefined, changes)});
    assert.equal(events(page).length, 1);
    assert.equal(page.grid.hidden, false);
    assert.match(page.notice.textContent, /불러오지 못해/);
  }
});

test('dates outside the stored coverage are marked as unknown', async () => {
  const page = browser();
  await page.start({[primary]: snapshot('2026-10-31T01:35:00Z', {windowEnd: '2026-11-09T00:00:00+09:00'})});
  const unknown = descendants(page.grid).filter(el => el.className.includes('schedule-day--unknown'));
  assert.equal(unknown.length, 15);
  assert.ok(unknown.every(day => day.children.some(el => el.textContent === '확인 필요')));
  assert.equal(events(page).length, 1);
});

test('browser storage retains time fields only', async () => {
  const data = snapshot();
  data.summary = 'private';
  data.busy[0].summary = 'private';
  const page = browser();
  await page.start({[primary]: data});
  assert.doesNotMatch(page.storage.get(key), /private|summary/);
});

test('disabled storage still permits live display', async () => {
  const page = browser({storageUnavailable: true});
  await page.start({[primary]: snapshot()});
  assert.equal(page.grid.hidden, false);
  assert.equal(events(page).length, 1);
});

test('without any valid snapshot, the page shows an error rather than empty availability', async () => {
  const page = browser();
  await page.start({});
  assert.equal(page.grid.hidden, true);
  assert.match(page.notice.textContent, /일정을 불러오지 못했습니다/);
});
