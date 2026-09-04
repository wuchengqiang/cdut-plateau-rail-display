const loginPanel = document.querySelector('#login-panel');
const editorPanel = document.querySelector('#editor-panel');
const loginForm = document.querySelector('#login-form');
const passwordInput = document.querySelector('#password');
const actionsContainer = document.querySelector('#actions');
const message = document.querySelector('#message');
const actionsHash = document.querySelector('#actions-hash');
const saveButton = document.querySelector('#save-button');
const reloadButton = document.querySelector('#reload-button');

let actions = [];

const blockedPhrases = ['<script', 'javascript:', 'ignore previous', 'system prompt', '忽略系统', '忽略之前', '执行任意命令', '访问任意'];
const ipPattern = /(?:^|[^\d])(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}(?::\d{1,5})?(?!\d)/;

function showMessage(text, error = false) {
  message.textContent = text;
  message.classList.toggle('error', error);
}

function parseKeywords(value) {
  return value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean);
}

function cleanText(value) {
  return value.replace(/\s+/g, ' ').trim();
}

function validateText(value, maximum, label, required = false) {
  if (/[\u0000-\u001F\u007F]/.test(value)) throw new Error(`${label}不能包含控制字符`);
  const text = cleanText(value);
  const lowered = text.toLowerCase();
  if (required && !text) throw new Error(`${label}不能为空`);
  if (text.length > maximum) throw new Error(`${label}不能超过 ${maximum} 个字符`);
  if (/[<>]/.test(text) || /https?:\/\//i.test(text) || ipPattern.test(text)) throw new Error(`${label}不能包含标签、URL 或 IP 地址`);
  if (blockedPhrases.some((phrase) => lowered.includes(phrase))) throw new Error(`${label}包含不允许的指令文本`);
  return text;
}

function validateActions() {
  for (const action of actions) {
    action.name = validateText(action.name, 80, `${action.id} 名称`, true);
    action.description = validateText(action.description, 300, `${action.id} 说明`);
    if (action.keywords.length > 20 || action.negativeKeywords.length > 20) throw new Error(`${action.id} 的正向或反向关键词不能超过 20 项`);
    action.keywords = action.keywords.map((word) => validateText(word, 30, `${action.id} 关键词`, true));
    action.negativeKeywords = action.negativeKeywords.map((word) => validateText(word, 30, `${action.id} 反向关键词`, true));
  }
}

function recalculateIndexes() {
  let index = 0;
  for (const action of actions) action.index = action.enabled ? index++ : null;
}

function bindField(element, action, field, parser = (value) => value) {
  element.addEventListener('input', () => { action[field] = parser(element.value); });
}

function renderActions() {
  recalculateIndexes();
  actionsContainer.replaceChildren();
  for (const action of actions) {
    const card = document.createElement('article');
    card.className = `action-card${action.enabled ? '' : ' disabled'}`;

    const head = document.createElement('div');
    head.className = 'action-head';
    const title = document.createElement('div');
    title.className = 'action-title';
    const index = document.createElement('span');
    index.className = 'action-index';
    index.textContent = action.enabled ? `#${action.index}` : '—';
    const id = document.createElement('span');
    id.className = 'action-id';
    id.textContent = action.id;
    title.append(index, id);
    const toggle = document.createElement('label');
    toggle.className = 'toggle';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = action.enabled;
    checkbox.addEventListener('change', () => { action.enabled = checkbox.checked; renderActions(); showMessage('启用状态已改变，保存后下标将按当前顺序重新生成'); });
    toggle.append(checkbox, document.createTextNode('启用'));
    head.append(title, toggle);

    const fields = document.createElement('div');
    fields.className = 'fields';
    const definitions = [
      ['动作名称', 'input', 'name', action.name, '最多 80 字'],
      ['动作说明', 'textarea', 'description', action.description, '最多 300 字，可写使用条件'],
      ['正向关键词', 'input', 'keywords', action.keywords.join('，'), '逗号分隔，最多 20 项'],
      ['反向关键词', 'input', 'negativeKeywords', action.negativeKeywords.join('，'), '命中后不选择该动作，最多 20 项'],
    ];
    for (const [labelText, tag, field, value, hintText] of definitions) {
      const label = document.createElement('label');
      label.append(document.createTextNode(labelText));
      const input = document.createElement(tag);
      input.value = value;
      if (field === 'name') input.maxLength = 80;
      if (field === 'description') input.maxLength = 300;
      bindField(input, action, field, field.includes('Keywords') || field === 'keywords' ? parseKeywords : cleanText);
      const hint = document.createElement('span');
      hint.className = 'hint';
      hint.textContent = hintText;
      label.append(input, hint);
      fields.append(label);
    }
    card.append(head, fields);
    actionsContainer.append(card);
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  let data;
  try { data = await response.json(); } catch { data = { message: '服务返回了无法识别的内容' }; }
  if (!response.ok) {
    const error = new Error(data.message || data.detail || `请求失败：${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function loadActions() {
  try {
    const data = await request('/api/admin/wakefusion/actions');
    actions = data.actions;
    actionsHash.textContent = data.actionsHash;
    actionsHash.title = data.actionsHash;
    loginPanel.hidden = true;
    editorPanel.hidden = false;
    saveButton.disabled = !data.safeToSave;
    renderActions();
    showMessage(data.safeToSave ? '配置已加载' : '当前业务正在运行，请停止视频、滑轨或自动巡展后再保存', !data.safeToSave);
  } catch (error) {
    if (error.status === 401) {
      loginPanel.hidden = false;
      editorPanel.hidden = true;
      return;
    }
    showMessage(error.message, true);
  }
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await request('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: passwordInput.value }),
    });
    passwordInput.value = '';
    await loadActions();
  } catch (error) {
    const node = loginPanel.querySelector('p');
    node.textContent = error.message;
    node.classList.add('message', 'error');
  }
});

reloadButton.addEventListener('click', () => { void loadActions(); });
saveButton.addEventListener('click', async () => {
  try {
    validateActions();
    saveButton.disabled = true;
    const data = await request('/api/admin/wakefusion/actions', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actions }),
    });
    actionsHash.textContent = data.actionsHash;
    actionsHash.title = data.actionsHash;
    showMessage(data.message);
    await loadActions();
  } catch (error) {
    showMessage(error.message, true);
    saveButton.disabled = false;
  }
});

void loadActions();
