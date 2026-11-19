const composer = document.querySelector('#composer');
const input = document.querySelector('#questionInput');
const chatBody = document.querySelector('#chatBody');
const sendButton = composer.querySelector('.send-button');
const uploadButton = document.querySelector('#uploadButton');
const documentInput = document.querySelector('#documentInput');
const documentCount = document.querySelector('#documentCount');
const documentList = document.querySelector('#documentList');
const sessionList = document.querySelector('#sessionList');
const newChatButton = document.querySelector('#newChatButton');
const activeSessionTitle = document.querySelector('#activeSessionTitle');

let currentSessionId = localStorage.getItem('currentSessionId');
let sessions = [];

async function requestJson(url, options = {}) {
  const response = await fetch(url, { cache: 'no-store', ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || 'The request could not be completed.');
  }
  return data;
}

async function refreshDocuments() {
  try {
    renderDocuments(await requestJson('/api/documents'));
  } catch (error) {
    documentList.innerHTML = `<p class="empty-documents">${escapeHtml(error.message)}</p>`;
  }
}

function renderDocuments(documents) {
  documentCount.textContent = documents.length;
  if (!documents.length) {
    documentList.innerHTML = '<p class="empty-documents">No documents uploaded yet.</p>';
    return;
  }
  documentList.innerHTML = documents.map((document) => `
    <div class="document-item">
      <span class="file-icon">PDF</span>
      <div class="document-info">
        <strong title="${escapeAttribute(document.file_name)}">${escapeHtml(document.file_name)}</strong>
        <small>Available for questions</small>
      </div>
      <button class="delete-source" type="button" data-document-id="${document.id}"
        data-document-name="${escapeAttribute(document.file_name)}"
        aria-label="Remove ${escapeAttribute(document.file_name)}" title="Remove source">×</button>
    </div>`).join('');
}

async function refreshSessions() {
  sessions = await requestJson('/api/sessions');
  renderSessions();
}

function renderSessions() {
  if (!sessions.length) {
    sessionList.innerHTML = '<p class="empty-documents">No conversations yet.</p>';
    return;
  }
  sessionList.innerHTML = sessions.map((session) => `
    <div class="session-row${session.id === currentSessionId ? ' active' : ''}">
      <button class="session-item" type="button"
        data-session-id="${escapeAttribute(session.id)}"
        title="${escapeAttribute(session.title)}" ${composer.dataset.busy === 'true' ? 'disabled' : ''}>
        ${escapeHtml(session.title)}
      </button>
      <button class="delete-session" type="button"
        data-delete-session-id="${escapeAttribute(session.id)}"
        aria-label="Delete ${escapeAttribute(session.title)}"
        title="Delete conversation" ${composer.dataset.busy === 'true' ? 'disabled' : ''}>×</button>
    </div>`).join('');
}

async function createSession() {
  const session = await requestJson('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'New Chat' }),
  });
  currentSessionId = session.id;
  localStorage.setItem('currentSessionId', currentSessionId);
  await refreshSessions();
  showConversation(session.title, []);
}

async function selectSession(sessionId) {
  if (composer.dataset.busy === 'true') return;
  currentSessionId = sessionId;
  localStorage.setItem('currentSessionId', sessionId);
  renderSessions();
  chatBody.replaceChildren();
  addSystemMessage('Loading conversation...');
  try {
    const session = await requestJson(`/api/sessions/${encodeURIComponent(sessionId)}`);
    showConversation(session.title, session.messages);
  } catch (error) {
    chatBody.replaceChildren();
    addSystemMessage(error.message);
  }
}

function showConversation(title, messages) {
  activeSessionTitle.textContent = title || 'New Chat';
  chatBody.replaceChildren();
  if (!messages.length) {
    addSystemMessage('Ask questions about your documents.');
    appendMessage('assistant-message', 'Document RAG',
      'Type a question below to search your documents and generate an answer.',
      'R', 'assistant-avatar');
    return;
  }
  for (const message of messages) {
    const isUser = message.role === 'user';
    appendMessage(
      isUser ? 'user-message' : 'assistant-message',
      isUser ? 'You' : 'Document RAG',
      message.content,
      isUser ? 'M' : 'R',
      isUser ? 'user-avatar' : 'assistant-avatar',
      message.created_at,
    );
  }
}

function addSystemMessage(text) {
  const note = document.createElement('div');
  note.className = 'system-note';
  note.textContent = text;
  chatBody.appendChild(note);
}

newChatButton.addEventListener('click', async () => {
  if (composer.dataset.busy === 'true') return;
  newChatButton.disabled = true;
  try {
    await createSession();
  } catch (error) {
    addSystemMessage(error.message);
  } finally {
    newChatButton.disabled = false;
  }
});

sessionList.addEventListener('click', (event) => {
  const deleteButton = event.target.closest('[data-delete-session-id]');
  if (deleteButton) {
    deleteSession(deleteButton.dataset.deleteSessionId);
    return;
  }
  const button = event.target.closest('[data-session-id]');
  if (button) selectSession(button.dataset.sessionId);
});

async function deleteSession(sessionId) {
  if (composer.dataset.busy === 'true') return;
  const session = sessions.find((item) => item.id === sessionId);
  if (!session) return;
  if (!window.confirm(`Delete “${session.title}” and its messages?`)) return;

  try {
    await requestJson(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    });
    if (sessionId === currentSessionId) {
      currentSessionId = null;
      localStorage.removeItem('currentSessionId');
    }
    await refreshSessions();
    if (sessionId === currentSessionId) return;
    if (!currentSessionId || !sessions.some((item) => item.id === currentSessionId)) {
      if (sessions.length) await selectSession(sessions[0].id);
      else await createSession();
    }
  } catch (error) {
    addSystemMessage(error.message);
  }
}

uploadButton.addEventListener('click', () => documentInput.click());

documentList.addEventListener('click', async (event) => {
  const button = event.target.closest('.delete-source');
  if (!button || button.disabled) return;
  const documentName = button.dataset.documentName;
  if (!window.confirm(`Remove “${documentName}” from your sources?`)) return;

  button.disabled = true;
  try {
    await requestJson(`/api/documents/${button.dataset.documentId}`, { method: 'DELETE' });
    await refreshDocuments();
    appendMessage('assistant-message', 'Document RAG', `${documentName} was removed from your sources.`, 'R', 'assistant-avatar');
  } catch (error) {
    button.disabled = false;
    appendMessage('assistant-message', 'Document RAG', error.message, 'R', 'assistant-avatar');
  }
});

documentInput.addEventListener('change', async () => {
  const file = documentInput.files[0];
  if (!file) return;
  setBusy(true);
  appendMessage('assistant-message', 'Document RAG', `Indexing ${file.name}...`, 'R', 'assistant-avatar');
  try {
    const formData = new FormData();
    formData.append('file', file);
    const data = await requestJson('/api/upload', { method: 'POST', body: formData });
    await refreshDocuments();
    appendMessage('assistant-message', 'Document RAG', `${data.file_name} is ready. Indexed ${data.chunks} chunks.`, 'R', 'assistant-avatar');
  } catch (error) {
    appendMessage('assistant-message', 'Document RAG', error.message, 'R', 'assistant-avatar');
  } finally {
    documentInput.value = '';
    setBusy(false);
  }
});

composer.addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question || !currentSessionId || composer.dataset.busy === 'true') return;

  appendMessage('user-message', 'You', question, 'M', 'user-avatar');
  input.value = '';
  setBusy(true);
  const pending = appendMessage('assistant-message', 'Document RAG', 'Searching your indexed documents...', 'R', 'assistant-avatar');

  try {
    const data = await requestJson('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: currentSessionId }),
    });
    pending.querySelector('p').innerHTML = escapeHtml(data.answer).replace(/\n/g, '<br />');
    try {
      await refreshSessions();
      const active = sessions.find((session) => session.id === currentSessionId);
      if (active) activeSessionTitle.textContent = active.title;
    } catch (_error) {
      // The saved answer remains usable if refreshing the sidebar fails.
    }
  } catch (error) {
    pending.querySelector('p').textContent = error.message;
  } finally {
    setBusy(false);
    input.focus();
    chatBody.scrollTop = chatBody.scrollHeight;
  }
});

function setBusy(isBusy) {
  composer.dataset.busy = String(isBusy);
  input.disabled = isBusy;
  sendButton.disabled = isBusy;
  uploadButton.disabled = isBusy;
  newChatButton.disabled = isBusy;
  renderSessions();
}

function appendMessage(messageClass, author, text, avatarText, avatarClass, timestamp = null) {
  const message = document.createElement('article');
  message.className = `message ${messageClass}`;
  const time = timestamp ? new Date(timestamp) : new Date();
  const timeText = Number.isNaN(time.getTime()) ? 'Now' : time.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  message.innerHTML = `
    <span class="avatar ${avatarClass}">${avatarText}</span>
    <div class="message-content">
      <div class="message-meta"><strong>${escapeHtml(author)}</strong><time>${escapeHtml(timeText)}</time></div>
      <p>${escapeHtml(text).replace(/\n/g, '<br />')}</p>
    </div>`;
  chatBody.appendChild(message);
  chatBody.scrollTop = chatBody.scrollHeight;
  return message;
}

function escapeHtml(value) {
  const element = document.createElement('div');
  element.textContent = String(value);
  return element.innerHTML;
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/"/g, '&quot;');
}

async function initialize() {
  await Promise.all([refreshDocuments(), refreshSessions().catch((error) => {
    sessionList.innerHTML = `<p class="empty-documents">${escapeHtml(error.message)}</p>`;
  })]);

  if (!sessions.length) {
    await createSession();
    return;
  }
  const savedSessionExists = sessions.some((session) => session.id === currentSessionId);
  const sessionId = savedSessionExists ? currentSessionId : sessions[0].id;
  await selectSession(sessionId);
}

initialize().catch((error) => addSystemMessage(error.message));
