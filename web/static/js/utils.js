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

    // 无序列表：将连续的 - 行收集后统一包裹
    text = text.replace(/^- (.*$)/gim, '<li>$1</li>');
    text = text.replace(/(<li>.*<\/li>\n?)+/g, function(match) {
        if (!match.includes('<ol>')) {
            return `<ul>${match}</ul>`;
        }
        return match;
    });

    // 有序列表：保留原始序号，使用 <ol start="n"> 确保序号正确
    // 先匹配连续的数字开头行，统一处理
    text = text.replace(/((?:^\d+\. .*\n?)+)/gim, function(match) {
        const items = match.trim().split('\n');
        const startMatch = items[0].match(/^(\d+)\.\s/);
        const start = startMatch ? startMatch[1] : '1';
        const lis = items.map(line => {
            return line.replace(/^\d+\.\s/, '<li>') + '</li>';
        }).join('\n');
        return `<ol start="${start}">${lis}</ol>`;
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

export function formatDateTime(date = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    const y = date.getFullYear();
    const m = pad(date.getMonth() + 1);
    const d = pad(date.getDate());
    const H = pad(date.getHours());
    const M = pad(date.getMinutes());
    const S = pad(date.getSeconds());
    return `${y}-${m}-${d} ${H}:${M}:${S}`;
}

export function showView(viewName) {
    document.querySelectorAll('[id^="view-"]').forEach(el => el.classList.add('hidden'));
    const viewEl = document.getElementById(`view-${viewName}`);
    if (viewEl) viewEl.classList.remove('hidden');
    STATE.currentView = viewName;
}
