import { STATE } from './state.js';

export function markdownToHtml(text) {
    if (!text) return '';
    text = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    text = text.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    text = text.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    text = text.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, function(match, lang, code) {
        return `<pre><code class="language-${lang || 'text'}">${code.trim()}</code></pre>`;
    });

    text = text.replace(/^- (.*$)/gim, '<li>$1</li>');
    text = text.replace(/(?:<li>.*<\/li>)+/g, function(match) {
        return `<ul>${match}</ul>`;
    });

    text = text.replace(/^\d+\. (.*$)/gim, '<li>$1</li>');
    text = text.replace(/(?:<li>.*<\/li>)+/g, function(match) {
        if (!match.includes('<ul>')) {
            return `<ol>${match}</ol>`;
        }
        return match;
    });

    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    text = text.replace(/\n/g, '<br>');

    return text;
}

export function showToast(msg, isError = false) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = 'toast' + (isError ? ' error' : '');
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 3000);
}

export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export function formatTime(timeStr) {
    try {
        const date = new Date(timeStr);
        return date.toLocaleString('zh-CN');
    } catch {
        return timeStr;
    }
}

export function showView(viewName) {
    document.querySelectorAll('[id^="view-"]').forEach(el => el.classList.add('hidden'));
    const viewEl = document.getElementById(`view-${viewName}`);
    if (viewEl) viewEl.classList.remove('hidden');
    STATE.currentView = viewName;
}
