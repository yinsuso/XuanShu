
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


     1|
     2|async function sendMessage() {
     3|    const input = document.getElementById('message-input');
     4|    const text = input.value.trim();
     5|    if (!text) return;
     6|
     7|    appendMessage('user', text);
     8|    input.value = '';
     9|    
    10|    const loading = document.getElementById('typing-indicator');
    11|    if(loading) loading.classList.add('active');
    12|
    13|    try {
    14|        const formData = new FormData();
    15|        formData.append('message', text);
    16|        const res = await fetch('/api/chat', { method: 'POST', body: formData });
    17|        const data = await res.json();
    18|        if(data.success) {
    19|            appendMessage('assistant', data.response);
    20|        } else {
    21|            appendMessage('assistant', '❌ Error: ' + (data.error || 'Unknown error'));
    22|        }
    23|    } catch (e) {
    24|        appendMessage('assistant', '❌ Network Error: ' + e.message);
    25|    } finally {
    26|        if(loading) loading.classList.remove('active');
    27|    }
    28|}
    29|
    30|function appendMessage(role, content) {
    31|    const container = document.getElementById('messages');
    32|    if(!container) return;
    33|    const div = document.createElement('div');
    34|    div.className = 'message ' + (role === 'user' ? 'user-message' : 'assistant-message');
    35|    div.innerHTML = `
    36|        <div class="avatar ${role === 'user' ? 'user-avatar' : 'assistant-avatar'}">${role === 'user' ? '👤' : '🤖'}</div>
    37|        <div class="message-content">${content}</div>
    38|    `;
    39|    container.appendChild(div);
    40|    container.scrollTop = container.scrollHeight;
    41|}
    42|
    43|document.addEventListener('DOMContentLoaded', () => {
    44|    document.getElementById('send-btn')?.addEventListener('click', sendMessage);
    45|    document.getElementById('message-input')?.addEventListener('keypress', (e) => {
    46|        if(e.key === 'Enter' && !e.shiftKey) {
    47|            e.preventDefault();
    48|            sendMessage();
    49|        }
    50|    });
    51|});
    52|