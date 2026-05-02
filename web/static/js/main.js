
function changeTheme(themeName) {
    document.body.className = themeName;
    localStorage.setItem('preferred-theme', themeName);
}

function loadSavedTheme() {
    const savedTheme = localStorage.getItem('preferred-theme') || 'theme-origin';
    document.body.className = savedTheme;
    const selector = document.getElementById('theme-select');
    if(selector) selector.value = savedTheme;
}

// 在 DOMContentLoaded 中调用
document.addEventListener('DOMContentLoaded', () => {
    loadSavedTheme();
});



async function sendMessage() {
    const input = document.getElementById('message-input');
    const text = input.value.trim();
    if (!text) return;

    appendMessage('user', text);
    input.value = '';
    
    const loading = document.getElementById('typing-indicator');
    if(loading) loading.classList.add('active');

    try {
        const formData = new FormData();
        formData.append('message', text);
        const res = await fetch('/api/chat', { method: 'POST', body: formData });
        const data = await res.json();
        if(data.success) {
            appendMessage('assistant', data.response);
        } else {
            appendMessage('assistant', '❌ Error: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        appendMessage('assistant', '❌ Network Error: ' + e.message);
    } finally {
        if(loading) loading.classList.remove('active');
    }
}

function appendMessage(role, content) {
    const container = document.getElementById('messages');
    if(!container) return;
    const div = document.createElement('div');
    div.className = 'message ' + (role === 'user' ? 'user-message' : 'assistant-message');
    div.innerHTML = `
        <div class="avatar ${role === 'user' ? 'user-avatar' : 'assistant-avatar'}">${role === 'user' ? '👤' : '🤖'}</div>
        <div class="message-content">${content}</div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('send-btn')?.addEventListener('click', sendMessage);
    document.getElementById('message-input')?.addEventListener('keypress', (e) => {
        if(e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
});
