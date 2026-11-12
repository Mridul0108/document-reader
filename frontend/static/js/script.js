const composer = document.querySelector('#composer');
const input = document.querySelector('#questionInput');
const chatBody = document.querySelector('#chatBody');
const messageList = chatBody;
const sendButton = composer.querySelector('.send-button');
const uploadButton = document.querySelector('#uploadButton');
const documentInput = document.querySelector('#documentInput');
const documentCount = document.querySelector('#documentCount');
const documentList = document.querySelector('#documentList');

async function refreshDocuments() {
  try {
    const response = await fetch('/api/documents', { cache: 'no-store' });
    if (!response.ok) throw new Error('Could not load documents.');
    renderDocuments(await response.json());
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
      <div><strong title="${escapeHtml(document.file_name)}">${escapeHtml(document.file_name)}</strong><small>Available for questions</small></div>
      <span class="check" aria-label="Indexed">✓</span>
    </div>`).join('');
}

uploadButton.addEventListener('click', () => documentInput.click());

documentInput.addEventListener('change', async () => {
  const file = documentInput.files[0];
  if (!file) return;
  setBusy(true);
  appendMessage('assistant-message', 'Document RAG', `Indexing ${file.name}...`, 'R', 'assistant-avatar');
  try {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'The document could not be indexed.');
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
  if (!question || composer.dataset.busy === 'true') return;

  appendMessage('user-message', 'You', question, 'M', 'user-avatar');
  input.value = '';
  setBusy(true);
  const pending = appendMessage('assistant-message', 'Document RAG', 'Searching your indexed documents...', 'R', 'assistant-avatar');

  try {
    const response = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'The server could not answer the question.');
    pending.querySelector('p').innerHTML = escapeHtml(data.answer).replace(/\n/g, '<br />');
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
}

function appendMessage(messageClass, author, text, avatarText, avatarClass) {
  const message = document.createElement('article');
  message.className = `message ${messageClass}`;
  message.innerHTML = `
    <span class="avatar ${avatarClass}">${avatarText}</span>
    <div class="message-content">
      <div class="message-meta"><strong>${escapeHtml(author)}</strong><time>Now</time></div>
      <p>${escapeHtml(text).replace(/\n/g, '<br />')}</p>
    </div>`;
  messageList.appendChild(message);
  chatBody.scrollTop = chatBody.scrollHeight;
  return message;
}

function escapeHtml(value) {
  const element = document.createElement('div');
  element.textContent = value;
  return element.innerHTML;
}

refreshDocuments();
