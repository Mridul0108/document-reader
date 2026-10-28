const composer = document.querySelector('#composer');
const input = document.querySelector('#questionInput');
const chatBody = document.querySelector('#chatBody');

composer.addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;

  appendMessage('user-message', 'You', question, 'M', 'user-avatar');
  input.value = '';
  chatBody.scrollTop = chatBody.scrollHeight;

  try {
    const response = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    if (!response.ok) throw new Error('The server could not answer the question.');
    const data = await response.json();
    appendMessage('assistant-message', 'Document RAG', data.answer, 'R', 'assistant-avatar');
  } catch (error) {
    appendMessage('assistant-message', 'Document RAG', error.message, 'R', 'assistant-avatar');
  }

  chatBody.scrollTop = chatBody.scrollHeight;
});

function appendMessage(messageClass, author, text, avatarText, avatarClass) {
  const message = document.createElement('article');
  message.className = `message ${messageClass}`;
  message.innerHTML = `
    <span class="avatar ${avatarClass}">${avatarText}</span>
    <div class="message-content">
      <div class="message-meta"><strong>${escapeHtml(author)}</strong><time>Now</time></div>
      <p>${escapeHtml(text).replace(/\n/g, '<br />')}</p>
    </div>`;
  chatBody.appendChild(message);
}

function escapeHtml(value) {
  const element = document.createElement('div');
  element.textContent = value;
  return element.innerHTML;
}
