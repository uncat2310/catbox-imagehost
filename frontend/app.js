/* Catbox image host */

const Q = s => document.querySelector(s);
const QA = (s, fn) => document.querySelectorAll(s).forEach(fn);

const LS_KEY = 'catbox';
const ENC_MAGIC = 'CATBOX_ENC_V1:';
const THEMES = new Set(['auto', 'light', 'dark']);
const JSON_HEADERS = { 'Content-Type': 'application/json' };
const DEFAULT_CONFIG = { webp_enabled: false, webp_quality: 80, upload_concurrency: 3, theme: 'auto' };

const ICON_SUN = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
const ICON_MOON = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
const TYPE_ICON = { image: '', video: '\uD83C\uDFAC', audio: '\uD83C\uDFB5' };
const ICON_FILE = '\uD83D\uDCC4';

const el = {
  dropZone: Q('#drop-zone'),
  fileInput: Q('#file-input'),
  uploading: Q('#uploading'),
  progressBar: Q('#progress-bar'),
  progressLabel: Q('#progress-label'),
  resultCard: Q('#result-card'),
  resultCount: Q('#result-count'),
  resultList: Q('#result-list'),
  btnCopyUrls: Q('#btn-copy-urls'),
  btnCopyMd: Q('#btn-copy-md'),
  btnUploadMore: Q('#btn-upload-more'),
  historyBtn: Q('#btn-history'),
  historyOverlay: Q('#history-overlay'),
  historyPanel: Q('#history-panel'),
  historyList: Q('#history-list'),
  historyToolbar: Q('#history-toolbar'),
  historyNote: Q('#history-note'),
  historySubtitle: Q('#history-subtitle'),
  historyClose: Q('[data-close="history-panel"]'),
  selectAll: Q('#check-select-all'),
  btnBatchCopy: Q('#btn-batch-copy'),
  btnBatchDel: Q('#btn-batch-del'),
  settingsSheet: Q('#settings-sheet'),
  sheet: Q('#settings-sheet .sheet'),
  sheetHandle: Q('#settings-sheet .sheet-handle'),
  settingsBtn: Q('#btn-settings'),
  closeSheetBtn: Q('#btn-close-sheet'),
  themeBtn: Q('#btn-theme'),
  iconTheme: Q('#icon-theme'),
  themeMenu: Q('#theme-menu'),
  userhashInput: Q('#input-userhash'),
  userhashBadge: Q('#userhash-badge'),
  noUserhashWarn: Q('#no-userhash-warn'),
  webpEnabled: Q('#input-webp-enabled'),
  webpQuality: Q('#input-webp-quality'),
  qualityValue: Q('#quality-value'),
  uploadConcurrency: Q('#input-upload-concurrency'),
  concurrencyValue: Q('#concurrency-value'),
  saveUserhashBtn: Q('#btn-save-userhash'),
  saveImageSettingsBtn: Q('#btn-save-image-settings'),
  encryptPass: Q('#input-encrypt-pass'),
  exportBtn: Q('#btn-export'),
  importBtn: Q('#btn-import'),
  importFile: Q('#import-file'),
  toast: Q('#toast'),
};

const state = {
  batchResults: [],
  config: { ...DEFAULT_CONFIG },
  historyOpening: false,
  historyLoadTimer: 0,
  sheetDrag: { active: false, pointerId: null, startY: 0, currentY: 0 },
};

const ls = {
  get: key => localStorage.getItem(`${LS_KEY}-${key}`) || '',
  set: (key, value) => localStorage.setItem(`${LS_KEY}-${key}`, value),
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function normalizeTheme(theme) {
  return THEMES.has(theme) ? theme : 'auto';
}

function normalizeConfig(cfg = {}) {
  const quality = Number.parseInt(cfg.webp_quality, 10);
  const concurrency = Number.parseInt(cfg.upload_concurrency, 10);
  return {
    webp_enabled: Boolean(cfg.webp_enabled),
    webp_quality: Number.isFinite(quality) ? clamp(quality, 1, 100) : DEFAULT_CONFIG.webp_quality,
    upload_concurrency: Number.isFinite(concurrency) ? clamp(concurrency, 1, 6) : DEFAULT_CONFIG.upload_concurrency,
    theme: normalizeTheme(cfg.theme || DEFAULT_CONFIG.theme),
  };
}

function iconFor(type) {
  return TYPE_ICON[type] || ICON_FILE;
}

function getTheme() {
  return document.documentElement.dataset.theme || 'auto';
}

function postConfig(data) {
  return fetch('/api/config', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(data) }).catch(() => {});
}

function setTheme(theme, opts = {}) {
  const { persist = true, sync = true, animate = false } = opts;
  const next = normalizeTheme(theme);
  if (animate) {
    el.themeBtn.classList.remove('theme-flip');
    void el.themeBtn.offsetWidth;
    el.themeBtn.classList.add('theme-flip');
    setTimeout(() => el.themeBtn.classList.remove('theme-flip'), 360);
  }
  document.documentElement.dataset.theme = next;
  el.iconTheme.innerHTML = next === 'dark' ? ICON_MOON : ICON_SUN;
  QA('.theme-option', option => option.classList.toggle('active', option.dataset.theme === next));
  if (persist) ls.set('theme', next);
  if (sync) postConfig({ theme: next });
}

function loadTheme() {
  setTheme(ls.get('theme') || DEFAULT_CONFIG.theme, { sync: false });
}

function setThemeMenu(open) {
  el.themeMenu.classList.toggle('open', open);
  el.themeBtn.classList.toggle('is-open', open);
  el.themeBtn.setAttribute('aria-expanded', String(open));
}

function toast(message, isError = false) {
  const node = el.toast;
  node.textContent = message;
  node.className = `toast${isError ? ' error' : ''}`;
  clearTimeout(node._exitTimer);
  clearTimeout(node._hideTimer);
  node._exitTimer = setTimeout(() => {
    node.classList.add('exit');
    node._hideTimer = setTimeout(() => node.classList.add('hidden'), 200);
  }, 2200);
}

async function copy(text, btn, okMsg) {
  if (!text) {
    toast('没有可复制的内容', true);
    return;
  }

  const done = () => {
    toast(okMsg);
    if (!btn) return;
    const originalText = btn.textContent;
    btn.textContent = '已拷贝';
    btn.classList.add('btn-success');
    setTimeout(() => {
      btn.textContent = originalText;
      btn.classList.remove('btn-success');
    }, 1600);
  };

  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      done();
      return;
    }
  } catch {
    // Fall through to the textarea copy path.
  }
  fallbackCopy(text, done);
}

function fallbackCopy(text, onSuccess) {
  const ta = Object.assign(document.createElement('textarea'), {
    value: text,
    style: 'position:fixed;left:-9999px;top:-9999px;font-size:16px',
  });
  ta.setAttribute('readonly', '');
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, 99999);
  try {
    document.execCommand('copy') ? onSuccess() : toast('拷贝失败，请手动复制', true);
  } catch {
    toast('拷贝失败，请手动复制', true);
  } finally {
    document.body.removeChild(ta);
  }
}

function loadUserhash() {
  const userhash = ls.get('userhash');
  el.userhashInput.value = userhash;
  el.userhashBadge.textContent = userhash ? '已设置' : '未设置';
  el.userhashBadge.className = userhash ? 'badge' : 'badge badge-dim';
  el.noUserhashWarn.classList.toggle('hidden', Boolean(userhash));
}

function saveUserhash() {
  ls.set('userhash', el.userhashInput.value.trim());
  loadUserhash();
  toast('已保存（仅本浏览器生效）');
}

const getUserhash = () => ls.get('userhash');

function renderConfig(cfg = state.config) {
  state.config = normalizeConfig(cfg);
  el.webpEnabled.checked = state.config.webp_enabled;
  el.webpQuality.value = state.config.webp_quality;
  el.qualityValue.textContent = state.config.webp_quality;
  el.uploadConcurrency.value = state.config.upload_concurrency;
  el.concurrencyValue.textContent = state.config.upload_concurrency;
}

async function loadConfig({ applyTheme = true } = {}) {
  try {
    const response = await fetch('/api/config');
    const cfg = normalizeConfig(await response.json());
    renderConfig(cfg);
    if (applyTheme && cfg.theme !== getTheme()) setTheme(cfg.theme, { sync: false });
  } catch {
    renderConfig();
  }
  loadUserhash();
}

async function saveImageSettings() {
  const body = normalizeConfig({
    ...state.config,
    webp_enabled: el.webpEnabled.checked,
    webp_quality: el.webpQuality.value,
    upload_concurrency: el.uploadConcurrency.value,
  });

  try {
    const response = await fetch('/api/config', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(body) });
    const data = await response.json();
    if (!data.ok) throw new Error('save failed');
    renderConfig(body);
    toast('上传设置已保存');
  } catch {
    toast('保存失败', true);
  }
}

async function uploadFiles(fileList) {
  const files = [...fileList];
  if (!files.length) return;

  const userhash = getUserhash();
  if (!userhash) {
    toast('请先在设置中填入 Userhash', true);
    openSettings();
    return;
  }

  el.resultCard.classList.add('hidden');
  state.batchResults = [];
  el.uploading.classList.remove('hidden');
  el.progressBar.style.width = '0%';
  el.progressLabel.textContent = `准备上传 ${files.length} 个文件`;

  let done = 0;
  const concurrency = Math.min(state.config.upload_concurrency || DEFAULT_CONFIG.upload_concurrency, files.length);
  const uploadOne = async (file, index) => {
    el.progressLabel.textContent = `上传中 ${done}/${files.length} · 并发 ${concurrency}`;

    const formData = new FormData();
    formData.append('files', file);
    formData.append('userhash', userhash);

    try {
      const response = await fetch('/api/upload', { method: 'POST', body: formData });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || '上传失败');
      const result = data.results?.[0] || (data.errors?.[0] && {
        filename: data.errors[0].filename || file.name,
        url: '',
        type: 'error',
        error: data.errors[0].error || '上传失败',
        size: 0,
      });
      state.batchResults[index] = result || {
        filename: file.name,
        url: '',
        type: 'error',
        error: '上传失败',
        size: 0,
      };
    } catch (error) {
      state.batchResults[index] = { filename: file.name, url: '', type: 'error', error: error.message, size: 0 };
    }

    done += 1;
    el.progressLabel.textContent = `已完成 ${done}/${files.length} · ${file.name}`;
    el.progressBar.style.width = `${(done / files.length) * 100}%`;
  };

  await runPool(files, concurrency, uploadOne);

  el.progressLabel.textContent = `完成 ${files.length} 个`;
  el.progressBar.style.width = '100%';
  setTimeout(() => {
    el.uploading.classList.add('hidden');
    if (state.batchResults.length) showResults();
  }, 420);
}

async function runPool(items, limit, worker) {
  let next = 0;
  const workers = Array.from({ length: limit }, async () => {
    while (next < items.length) {
      const index = next;
      next += 1;
      await worker(items[index], index);
    }
  });
  await Promise.all(workers);
}

function resultMarkup(result, index) {
  if (!result.url) {
    return `<div class="result-item">
      <div class="result-item-thumb">&times;</div>
      <div class="result-item-info">
        <div class="result-item-filename">${h(result.filename)}</div>
        <div class="result-item-url is-error">${h(result.error || '上传失败')}</div>
      </div>
      <div class="result-item-status"><span class="cross">&times;</span></div>
    </div>`;
  }

  const thumb = result.type === 'image'
    ? `<img src="${attr(result.url)}" loading="lazy" alt="">`
    : h(iconFor(result.type));

  return `<div class="result-item">
    <div class="result-item-thumb">${thumb}</div>
    <div class="result-item-info">
      <div class="result-item-filename">${h(result.filename)}</div>
      <div class="result-item-url">${h(result.url)}</div>
    </div>
    <button class="result-item-copy" data-idx="${index}">拷贝</button>
    <div class="result-item-status"><span class="check">✓</span></div>
  </div>`;
}

function showResults() {
  el.resultCard.classList.remove('hidden');
  const good = state.batchResults.filter(result => result.url).length;
  const bad = state.batchResults.length - good;
  el.resultCount.textContent = `共 ${state.batchResults.length} 个，${good} 成功${bad ? `，${bad} 失败` : ''}`;
  el.resultList.innerHTML = state.batchResults.map(resultMarkup).join('');

  QA('.result-item-copy', button => button.addEventListener('click', () => {
    const item = state.batchResults[Number(button.dataset.idx)];
    if (item?.url) copy(item.url, button, '已拷贝');
  }));

  el.btnCopyUrls.textContent = '拷贝直链';
  el.btnCopyUrls.className = 'btn btn-primary flex-fill';
  el.btnCopyMd.textContent = '拷贝 Markdown';
  el.btnCopyMd.className = 'btn btn-secondary flex-fill';
  el.dropZone.style.display = 'none';
}

function resetUpload() {
  el.resultCard.classList.add('hidden');
  state.batchResults = [];
  el.dropZone.style.display = '';
  el.fileInput.value = '';
}

async function loadHistory() {
  try {
    const response = await fetch('/api/history');
    const data = await response.json();
    const history = Array.isArray(data.history) ? data.history : [];

    if (!history.length) {
      el.historyList.innerHTML = '<p class="empty-state">暂无记录</p>';
      el.historyToolbar.classList.add('hidden');
      el.historyNote.classList.add('hidden');
      el.historySubtitle.textContent = '暂无本地记录';
      return;
    }

    el.historyToolbar.classList.remove('hidden');
    el.historyNote.classList.remove('hidden');
    el.selectAll.checked = false;
    el.historyList.innerHTML = history.map(historyItemMarkup).join('');
    el.historySubtitle.textContent = `${history.length} 条本地记录`;
    updateBatchUI();
  } catch {
    el.historyList.innerHTML = '<p class="empty-state is-error">加载失败</p>';
    el.historyToolbar.classList.add('hidden');
    el.historyNote.classList.add('hidden');
    el.selectAll.checked = false;
    el.historySubtitle.textContent = '加载失败';
  }
}

function renderHistoryLoading() {
  el.historySubtitle.textContent = '正在加载';
  el.historyToolbar.classList.add('hidden');
  el.historyNote.classList.add('hidden');
  el.selectAll.checked = false;
  el.historyList.innerHTML = '<p class="empty-state">正在加载...</p>';
}

function historyItemMarkup(item) {
  const thumb = item.type === 'image' && item.url
    ? `<img src="${attr(item.url)}" alt="" loading="lazy">`
    : h(iconFor(item.type));

  return `<div class="history-item">
    <div class="item-check"><input type="checkbox" class="check-label" data-url="${attr(item.url)}"></div>
    <div class="history-thumb">${thumb}</div>
    <div class="history-info">
      <div class="history-filename">${h(item.filename)}</div>
      <div class="history-url">${h(item.url)}</div>
      <div class="history-time">${formatTime(item.time)}</div>
    </div>
    <div class="history-actions">
      <button class="btn btn-sm btn-secondary" data-copy="${attr(item.url)}">拷贝</button>
      <button class="btn btn-sm btn-danger" data-delete="${attr(item.url)}">清除</button>
    </div>
  </div>`;
}

function updateBatchUI() {
  const count = document.querySelectorAll('#history-list .item-check input:checked').length;
  el.btnBatchDel.textContent = count ? `清除选中 (${count})` : '清除选中';
  el.btnBatchCopy.textContent = count ? `复制选中 (${count})` : '复制选中';
}

function getCheckedUrls() {
  return [...document.querySelectorAll('#history-list .item-check input:checked')]
    .map(input => input.dataset.url)
    .filter(Boolean);
}

function toggleAllChecks() {
  QA('#history-list .item-check input[type="checkbox"]', input => {
    input.checked = el.selectAll.checked;
  });
  updateBatchUI();
}

async function toggleHistory() {
  if (el.historyOverlay.classList.contains('open')) {
    closeHistory();
    return;
  }
  openHistory();
}

async function openHistory() {
  if (state.historyOpening) return;
  state.historyOpening = true;
  setThemeMenu(false);
  renderHistoryLoading();
  el.historyOverlay.classList.add('open');
  el.historyBtn.classList.add('is-open');
  el.historyBtn.setAttribute('aria-expanded', 'true');
  clearTimeout(state.historyLoadTimer);
  state.historyLoadTimer = setTimeout(async () => {
    el.historyBtn.classList.add('is-busy');
    try {
      await loadHistory();
    } finally {
      state.historyOpening = false;
      el.historyBtn.classList.remove('is-busy');
    }
  }, 190);
}

function closeHistory() {
  clearTimeout(state.historyLoadTimer);
  state.historyOpening = false;
  el.historyOverlay.classList.remove('open');
  el.selectAll.checked = false;
  QA('#history-list .item-check input[type="checkbox"]', input => {
    input.checked = false;
  });
  updateBatchUI();
  el.historyBtn.classList.remove('is-open', 'is-busy');
  el.historyBtn.setAttribute('aria-expanded', 'false');
}

function onHistoryChange(event) {
  if (!event.target.matches('.item-check input[type="checkbox"]')) return;
  updateBatchUI();
  const inputs = [...document.querySelectorAll('#history-list .item-check input[type="checkbox"]')];
  el.selectAll.checked = inputs.length > 0 && inputs.every(input => input.checked);
}

function onHistoryClick(event) {
  const button = event.target.closest('[data-copy],[data-delete]');
  if (!button) return;
  if (button.dataset.copy) copy(button.dataset.copy, button, '已拷贝');
  if (button.dataset.delete) deleteSingle(button.dataset.delete);
}

async function batchCopyHistory() {
  const urls = getCheckedUrls();
  if (!urls.length) return toast('请先勾选记录', true);
  return copy(urls.join('\n'), el.btnBatchCopy, `已复制 ${urls.length} 条`);
}

async function batchDeleteHistory() {
  const urls = getCheckedUrls();
  if (!urls.length) return toast('请先勾选记录', true);
  if (!confirm(`清除 ${urls.length} 条本地历史记录？`)) return;
  await deleteHistory(urls, `已清除 ${urls.length} 条`);
}

function deleteSingle(url) {
  if (!confirm('清除这条历史记录？')) return;
  deleteHistory([url], '已清除');
}

async function deleteHistory(urls, okMsg) {
  try {
    const response = await fetch('/api/history/delete', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ urls }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error('delete failed');
    toast(okMsg || `已清除 ${data.deleted || 0} 条`);
    loadHistory();
  } catch {
    toast('操作失败', true);
  }
}

async function buildExport() {
  const data = await (await fetch('/api/export')).json();
  data.client = { userhash: ls.get('userhash'), theme: ls.get('theme') };
  return data;
}

async function encrypt(plain, password) {
  const encoder = new TextEncoder();
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const material = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: 200000, hash: 'SHA-256' },
    material,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt'],
  );
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoder.encode(plain));
  const bytes = new Uint8Array(salt.length + iv.length + encrypted.byteLength);
  bytes.set(salt, 0);
  bytes.set(iv, salt.length);
  bytes.set(new Uint8Array(encrypted), salt.length + iv.length);
  return ENC_MAGIC + bytesToBase64(bytes);
}

async function decrypt(payload, password) {
  if (!payload.startsWith(ENC_MAGIC)) throw new Error('非加密文件');
  const raw = base64ToBytes(payload.slice(ENC_MAGIC.length));
  const salt = raw.slice(0, 16);
  const iv = raw.slice(16, 28);
  const encrypted = raw.slice(28);
  const encoder = new TextEncoder();
  const material = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: 200000, hash: 'SHA-256' },
    material,
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt'],
  );
  return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, encrypted));
}

function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function exportData() {
  try {
    const json = JSON.stringify(await buildExport(), null, 2);
    const pass = el.encryptPass.value;
    if (pass) {
      if (pass.length < 4) return toast('密码至少 4 位', true);
      download(`catbox_enc_${today()}.json`, await encrypt(json, pass), 'text/plain');
      toast('加密备份已下载');
    } else {
      download(`catbox_backup_${today()}.json`, json, 'application/json');
      toast('导出完成（明文）');
    }
  } catch {
    toast('导出失败', true);
  }
}

async function importData() {
  const file = el.importFile.files[0];
  if (!file) {
    el.importFile.value = '';
    return;
  }

  try {
    const text = await file.text();
    const json = await parseBackup(text);
    const response = await fetch('/api/import', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(json) });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.detail || '导入失败');

    if (json.client?.userhash) ls.set('userhash', json.client.userhash);
    if (json.client?.theme) setTheme(json.client.theme);
    await loadConfig();
    toast(`导入成功：${data.imported_history || 0} 条`);
  } catch (error) {
    toast(error.message || '导入失败', true);
  } finally {
    el.importFile.value = '';
  }
}

async function parseBackup(text) {
  if (!text.startsWith(ENC_MAGIC)) return JSON.parse(text);
  const pass = prompt('这是加密备份，请输入密码：');
  if (!pass) throw new Error('已取消');
  try {
    return JSON.parse(await decrypt(text, pass));
  } catch {
    throw new Error('密码错误');
  }
}

function openSettings() {
  if (el.settingsSheet.classList.contains('open')) return;
  document.body.classList.add('settings-open');
  el.settingsBtn.setAttribute('aria-expanded', 'true');
  el.settingsSheet.classList.add('open');
  document.documentElement.style.overflow = 'hidden';
  loadUserhash();
  renderConfig();
  requestAnimationFrame(() => loadConfig({ applyTheme: false }));
}

function closeSettings() {
  if (!el.settingsSheet.classList.contains('open')) return;
  resetSheetDragStyles();
  document.body.classList.remove('settings-open');
  el.settingsBtn.setAttribute('aria-expanded', 'false');
  el.settingsSheet.classList.remove('open');
  document.documentElement.style.overflow = '';
}

function resetSheetDragStyles() {
  el.sheet.classList.remove('dragging');
  el.sheet.style.transform = '';
  el.sheet.style.transition = '';
}

function bindSheetDrag() {
  el.sheetHandle.addEventListener('pointerdown', startSheetDrag);
  el.sheetHandle.addEventListener('pointermove', moveSheetDrag);
  el.sheetHandle.addEventListener('pointerup', endSheetDrag);
  el.sheetHandle.addEventListener('pointercancel', endSheetDrag);
}

function startSheetDrag(event) {
  if (!el.settingsSheet.classList.contains('open')) return;
  const drag = state.sheetDrag;
  drag.active = true;
  drag.pointerId = event.pointerId;
  drag.startY = event.clientY;
  drag.currentY = 0;
  el.sheet.classList.add('dragging');
  el.sheetHandle.setPointerCapture(event.pointerId);
}

function moveSheetDrag(event) {
  const drag = state.sheetDrag;
  if (!drag.active || event.pointerId !== drag.pointerId) return;
  drag.currentY = Math.max(0, event.clientY - drag.startY);
  el.sheet.style.transform = `translate3d(0, ${drag.currentY}px, 0)`;
}

function endSheetDrag(event) {
  const drag = state.sheetDrag;
  if (!drag.active || event.pointerId !== drag.pointerId) return;
  drag.active = false;
  el.sheet.classList.remove('dragging');

  const threshold = Math.min(140, Math.max(80, el.sheet.offsetHeight * .16));
  if (drag.currentY > threshold) {
    el.sheet.style.transition = 'transform .22s cubic-bezier(.22, 1, .36, 1)';
    el.sheet.style.transform = 'translate3d(0, 100%, 0)';
    setTimeout(closeSettings, 220);
  } else {
    el.sheet.style.transform = '';
  }
}

function bindKB() {
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (el.settingsSheet.classList.contains('open')) closeSettings();
    if (el.historyOverlay.classList.contains('open')) closeHistory();
    setThemeMenu(false);
  });

  document.addEventListener('paste', event => {
    if (!event.clipboardData?.files.length || isInputFocused()) return;
    event.preventDefault();
    uploadFiles(event.clipboardData.files);
  });
}

function bindEvents() {
  el.themeBtn.addEventListener('click', event => {
    event.stopPropagation();
    setThemeMenu(!el.themeMenu.classList.contains('open'));
  });
  el.themeMenu.addEventListener('click', event => event.stopPropagation());
  QA('.theme-option', option => option.addEventListener('click', () => {
    setTheme(option.dataset.theme, { animate: true });
    setThemeMenu(false);
  }));
  document.addEventListener('click', () => setThemeMenu(false));

  el.dropZone.addEventListener('click', () => el.fileInput.click());
  el.fileInput.addEventListener('change', event => {
    if (event.target.files.length) uploadFiles(event.target.files);
    el.fileInput.value = '';
  });
  el.dropZone.addEventListener('dragover', event => {
    event.preventDefault();
    el.dropZone.classList.add('drag-over');
  });
  el.dropZone.addEventListener('dragleave', () => el.dropZone.classList.remove('drag-over'));
  el.dropZone.addEventListener('drop', event => {
    event.preventDefault();
    el.dropZone.classList.remove('drag-over');
    if (event.dataTransfer.files.length) uploadFiles(event.dataTransfer.files);
  });

  el.btnCopyUrls.addEventListener('click', () => copy(goodResults().map(result => result.url).join('\n'), el.btnCopyUrls, '直链已拷贝'));
  el.btnCopyMd.addEventListener('click', () => copy(goodResults().map(result => `![](${result.url})`).join('\n'), el.btnCopyMd, 'Markdown 已拷贝'));
  el.btnUploadMore.addEventListener('click', resetUpload);

  el.historyBtn.addEventListener('click', toggleHistory);
  el.historyClose.addEventListener('click', closeHistory);
  el.historyOverlay.addEventListener('click', event => {
    if (event.target === el.historyOverlay) closeHistory();
  });
  el.historyList.addEventListener('change', onHistoryChange);
  el.historyList.addEventListener('click', onHistoryClick);
  el.selectAll.addEventListener('change', toggleAllChecks);
  el.btnBatchCopy.addEventListener('click', batchCopyHistory);
  el.btnBatchDel.addEventListener('click', batchDeleteHistory);

  el.settingsBtn.addEventListener('click', openSettings);
  el.closeSheetBtn.addEventListener('click', closeSettings);
  el.settingsSheet.addEventListener('click', event => {
    if (event.target === el.settingsSheet) closeSettings();
  });

  el.saveUserhashBtn.addEventListener('click', saveUserhash);
  el.saveImageSettingsBtn.addEventListener('click', saveImageSettings);
  el.webpQuality.addEventListener('input', () => {
    el.qualityValue.textContent = el.webpQuality.value;
  });
  el.uploadConcurrency.addEventListener('input', () => {
    el.concurrencyValue.textContent = el.uploadConcurrency.value;
  });

  el.exportBtn.addEventListener('click', exportData);
  el.importBtn.addEventListener('click', () => el.importFile.click());
  el.importFile.addEventListener('change', importData);
}

function goodResults() {
  return state.batchResults.filter(result => result.url);
}

const today = () => new Date().toISOString().slice(0, 10);

function h(value) {
  const div = document.createElement('div');
  div.textContent = value || '';
  return div.innerHTML;
}

function attr(value) {
  return h(value).replace(/'/g, '&#39;');
}

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN');
}

function bytesToBase64(bytes) {
  let binary = '';
  const size = 0x8000;
  for (let i = 0; i < bytes.length; i += size) {
    binary += String.fromCharCode(...bytes.slice(i, i + size));
  }
  return btoa(binary);
}

function base64ToBytes(value) {
  return Uint8Array.from(atob(value), char => char.charCodeAt(0));
}

function isInputFocused() {
  const active = document.activeElement;
  return Boolean(active && (/^(INPUT|TEXTAREA)$/.test(active.tagName) || active.isContentEditable));
}

document.addEventListener('DOMContentLoaded', () => {
  loadTheme();
  loadConfig();
  bindEvents();
  bindKB();
  bindSheetDrag();
});
