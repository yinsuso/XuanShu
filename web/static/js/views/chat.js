import { STATE } from '../state.js';
import { api } from '../api.js';
import { showToast, markdownToHtml, escapeHtml, formatTime, formatDateTime, showView } from '../utils.js';

let lastUserMessage = '';
let lastConversationId = null;

export function appendMessage(role, content, msgIndex = null) {
    const container = document.getElementById('messages');
    if (!container) return;
    const div = document.createElement('div');
    div.className = 'message ' + (role === 'user' ? 'user-message' : 'assistant-message');
    const renderedContent = role === 'assistant' ? markdownToHtml(content) : escapeHtml(content);
    const index = msgIndex !== null ? msgIndex : container.children.length;
    const timeStr = formatDateTime();
    div.innerHTML = `
        <div class='avatar'>${role === 'user' ? '👤' : '🤖'}</div>
        <div class='message-content'>
            ${renderedContent}
            <div style="margin-top:4px;font-size:11px;color:#999;text-align:right;">${timeStr}</div>
            ${role === 'assistant' ? `
                <div style="margin-top:4px;display:flex;gap:4px;justify-content:flex-end;">
                    <button class="btn" style="font-size:11px;padding:2px 6px;width:auto;" onclick="window.copyMessage(this, ${index})">📋 复制</button>
                    <button class="btn" style="font-size:11px;padding:2px 6px;width:auto;" onclick="window.regenerateMessage(${index})">🔄 重新回复</button>
                </div>
            ` : ''}
        </div>
    `;
    div.dataset.index = index;
    div.dataset.content = content;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

export function copyMessage(btn, index) {
    const msgDiv = document.querySelector(`.message[data-index="${index}"]`);
    if (msgDiv) {
        const content = msgDiv.dataset.content || msgDiv.querySelector('.message-content').textContent;
        navigator.clipboard.writeText(content).then(() => {
            showToast('已复制到剪贴板');
        }).catch(() => {
            showToast('复制失败', true);
        });
    }
}

export function regenerateMessage(index) {
    const msgDiv = document.querySelector(`.message[data-index="${index}"]`);
    if (msgDiv && lastUserMessage) {
        const userMsgDiv = msgDiv.previousElementSibling;
        if (userMsgDiv && userMsgDiv.classList.contains('user-message')) {
            const userContent = userMsgDiv.dataset.content || userMsgDiv.querySelector('.message-content').textContent;
            lastUserMessage = userContent;
            lastConversationId = STATE.currentConversationId;
            msgDiv.remove();
            resendMessage(userContent);
        }
    }
}

export async function resendMessage(userMessage) {
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) {
        sendBtn.disabled = true;
        sendBtn.textContent = '重新生成中...';

        try {
            const payload = { message: userMessage };
            if (lastConversationId) {
                payload.conversation_id = lastConversationId;
            }

            const submitRes = await api('/api/chat/async-submit', {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            if (!submitRes.success) {
                appendMessage('assistant', '❌ ' + (submitRes.error || '提交任务失败'));
                return;
            }

            STATE.currentConversationId = submitRes.conversation_id;
            document.getElementById('current-conversation').textContent = '当前对话';

            appendMessage('assistant', '⏳ 正在重新生成...');

            const result = await pollAsyncChatTask(submitRes.task_id, sendBtn);

            const messagesContainer = document.getElementById('messages');
            if (messagesContainer) {
                const lastChild = messagesContainer.lastElementChild;
                if (lastChild && lastChild.classList.contains('message') &&
                    lastChild.classList.contains('assistant-message')) {
                    lastChild.remove();
                }
            }

            appendMessage('assistant', result);

        } catch (e) {
            const messagesContainer = document.getElementById('messages');
            if (messagesContainer) {
                const lastChild = messagesContainer.lastElementChild;
                if (lastChild && lastChild.classList.contains('message') &&
                    lastChild.classList.contains('assistant-message')) {
                    const lastContent = lastChild.querySelector('.message-content');
                    if (lastContent && (lastContent.textContent.includes('⏳'))) {
                        lastChild.remove();
                    }
                }
            }
            appendMessage('assistant', '❌ ' + (e.message || '网络错误'));
        } finally {
            sendBtn.disabled = false;
            sendBtn.textContent = '发送';
        }
    }
}

export async function sendMessage() {
    const input = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const text = input.value.trim();
    if (!text) return;

    // 【内置命令处理】识别单机模式通用内置命令
    const lowerText = text.toLowerCase();
    if (lowerText.startsWith('/')) {
        const handled = await handleStandaloneBuiltinCommand(text, lowerText, input);
        if (handled) return;
    }

    lastUserMessage = text;
    lastConversationId = STATE.currentConversationId;

    appendMessage('user', text);
    input.value = '';
    sendBtn.disabled = true;
    sendBtn.textContent = '处理中...';

    try {
        const payload = { message: text };
        if (STATE.currentConversationId) {
            payload.conversation_id = STATE.currentConversationId;
        }

        const submitRes = await api('/api/chat/async-submit', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (!submitRes.success) {
            appendMessage('assistant', '❌ ' + (submitRes.error || '提交任务失败'));
            return;
        }

        STATE.currentConversationId = submitRes.conversation_id;
        document.getElementById('current-conversation').textContent = '当前对话';

        appendMessage('assistant', '⏳ 正在思考中...');

        const result = await pollAsyncChatTask(submitRes.task_id, sendBtn);

        const messagesContainer = document.getElementById('messages');
        if (messagesContainer) {
            const lastChild = messagesContainer.lastElementChild;
            if (lastChild && lastChild.classList.contains('message') &&
                lastChild.classList.contains('assistant-message')) {
                lastChild.remove();
            }
        }

        appendMessage('assistant', result);

    } catch (e) {
        const messagesContainer = document.getElementById('messages');
        if (messagesContainer) {
            const lastChild = messagesContainer.lastElementChild;
            if (lastChild && lastChild.classList.contains('message') &&
                lastChild.classList.contains('assistant-message')) {
                const lastContent = lastChild.querySelector('.message-content');
                if (lastContent && lastContent.textContent.includes('⏳')) {
                    lastChild.remove();
                }
            }
        }
        appendMessage('assistant', '❌ ' + (e.message || '网络错误'));
    } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = '发送';
    }
}

/**
 * 【单机模式内置命令处理器】
 * 处理常用且通用的内置命令，返回 true 表示命令已处理
 */
async function handleStandaloneBuiltinCommand(originalText, lowerText, input) {
    input.value = '';

    switch (lowerText) {
        case '/new':
        case '/reset':
            appendMessage('system', `📢 收到内置命令「${originalText}」，正在开启新的单机对话...`);
            try {
                if (window.createNewStandaloneConversation) {
                    await window.createNewStandaloneConversation();
                    appendMessage('system', '✅ 已开启新的单机对话，历史记录已保存。');
                } else {
                    showToast('创建新对话功能未就绪', true);
                }
            } catch (e) {
                showToast('创建新对话失败: ' + e.message, true);
            }
            return true;

        case '/clear':
            appendMessage('system', `📢 收到内置命令「${originalText}」，正在清屏...`);
            document.getElementById('messages').innerHTML = '';
            showToast('屏幕已清空');
            return true;

        case '/history':
            appendMessage('system', `📢 收到内置命令「${originalText}」，正在加载对话历史...`);
            try {
                if (window.showView && window.loadConversationList) {
                    await window.loadConversationList();
                    window.showView('conversation-history');
                } else {
                    showToast('历史功能未就绪', true);
                }
            } catch (e) {
                showToast('加载历史失败: ' + e.message, true);
            }
            return true;

        case '/export':
        case '/save':
            appendMessage('system', `📢 收到内置命令「${originalText}」，正在导出对话...`);
            try {
                if (window.exportConversation) {
                    window.exportConversation('md');
                } else {
                    showToast('导出功能未就绪', true);
                }
            } catch (e) {
                showToast('导出失败: ' + e.message, true);
            }
            return true;

        case '/model':
        case '/models':
            appendMessage('system', `📢 收到内置命令「${originalText}」，正在打开模型管理...`);
            try {
                if (window.showView && window.loadModelList) {
                    await window.loadModelList();
                    window.showView('model-manage');
                } else {
                    showToast('模型管理功能未就绪', true);
                }
            } catch (e) {
                showToast('打开模型管理失败: ' + e.message, true);
            }
            return true;

        case '/help':
        case '/?':
            appendMessage('system', getStandaloneHelpText());
            return true;

        default:
            // 未识别的命令，恢复输入并返回 false 让上层继续处理
            input.value = originalText;
            return false;
    }
}

/**
 * 【单机模式帮助文本】
 */
function getStandaloneHelpText() {
    return `📖 **单机模式内置命令列表**

| 命令 | 说明 |
|------|------|
| /new 或 /reset | 开启新的单机对话 |
| /clear | 清空当前对话屏幕 |
| /history | 打开对话历史列表 |
| /export 或 /save | 导出当前对话为 Markdown |
| /model 或 /models | 打开模型管理页面 |
| /help 或 /? | 显示此帮助信息 |

💡 提示：所有命令不区分大小写`;
}

function pollAsyncChatTask(taskId, sendBtn) {
    const pollInterval = 1000;  // 轮询间隔改为1秒，减少服务器压力
    const maxPollTime = 180000; // 最大轮询时间改为3分钟（与后端超时匹配）
    const startTime = Date.now();
    let lastStatus = 'pending';
    let statusUpdateTime = Date.now();

    return new Promise((resolve, reject) => {
        const poll = async () => {
            try {
                const elapsed = Date.now() - startTime;
                if (elapsed > maxPollTime) {
                    reject(new Error('任务处理时间较长，已超出前端等待时间。任务可能仍在后台运行，请稍后刷新页面查看结果。'));
                    return;
                }

                const statusRes = await api(`/api/chat/task/${taskId}`);
                if (!statusRes.success) {
                    setTimeout(poll, pollInterval);
                    return;
                }

                const status = statusRes.status;
                
                // 更新UI状态显示
                if (status !== lastStatus) {
                    lastStatus = status;
                    statusUpdateTime = Date.now();
                    const messagesContainer = document.getElementById('messages');
                    if (messagesContainer) {
                        const lastChild = messagesContainer.lastElementChild;
                        if (lastChild && lastChild.classList.contains('assistant-message')) {
                            const contentDiv = lastChild.querySelector('.message-content');
                            if (contentDiv) {
                                if (status === 'processing') {
                                    const processingTime = Math.floor((Date.now() - startTime) / 1000);
                                    contentDiv.innerHTML = `⏳ 正在处理中... (${processingTime}秒)`;
                                } else if (status === 'pending') {
                                    contentDiv.innerHTML = `⏳ 等待处理中...`;
                                }
                            }
                        }
                    }
                } else if (status === 'processing') {
                    // 每10秒更新一次处理时间显示
                    const processingTime = Math.floor((Date.now() - startTime) / 1000);
                    if (processingTime % 10 === 0) {
                        const messagesContainer = document.getElementById('messages');
                        if (messagesContainer) {
                            const lastChild = messagesContainer.lastElementChild;
                            if (lastChild && lastChild.classList.contains('assistant-message')) {
                                const contentDiv = lastChild.querySelector('.message-content');
                                if (contentDiv && contentDiv.textContent.includes('⏳')) {
                                    contentDiv.innerHTML = `⏳ 正在处理中... (${processingTime}秒)`;
                                }
                            }
                        }
                    }
                }
                
                if (status === 'completed') {
                    resolve(statusRes.result);
                } else if (status === 'failed') {
                    reject(new Error(statusRes.error || '任务执行失败'));
                } else {
                    setTimeout(poll, pollInterval);
                }
            } catch (pollError) {
                // 网络错误时增加间隔，避免频繁请求
                setTimeout(poll, pollInterval * 2);
            }
        };
        poll();
    });
}

export async function enterStandaloneMode() {
    showToast('正在进入单机对话模式...');
    try {
        // 步骤1：如果前端已记录当前单机对话ID，优先尝试加载
        if (STATE.currentConversationId) {
            const res = await api(`/api/conversation/${STATE.currentConversationId}`);
            if (res.success) {
                document.getElementById('current-conversation').textContent = res.conversation.title;
                showView('chat');
                renderConversation(res.conversation);
                showToast('已加载当前对话');
                return;
            }
        }

        // 步骤2：调用后端切换模式，后端会自动加载该模式最近的对话
        const res = await api('/api/conversations/switch-mode', {
            method: 'POST',
            body: JSON.stringify({ mode: 'standalone' })
        });

        if (res.success) {
            // 步骤3：获取后端当前的对话状态
            const convRes = await api('/api/conversations?conversation_type=standalone&limit=1');
            if (convRes.success && convRes.conversations && convRes.conversations.length > 0) {
                const lastConv = convRes.conversations[0];
                STATE.currentConversationId = lastConv.conversation_id;
                document.getElementById('current-conversation').textContent = lastConv.title || '当前对话';

                // 加载并渲染对话内容
                const detailRes = await api(`/api/conversation/${lastConv.conversation_id}`);
                if (detailRes.success) {
                    showView('chat');
                    renderConversation(detailRes.conversation);
                    showToast('已恢复单机对话');
                } else {
                    showView('chat');
                    document.getElementById('messages').innerHTML = '';
                    showToast('已切换到单机对话模式');
                }
            } else {
                showView('chat');
                document.getElementById('messages').innerHTML = '';
                STATE.currentConversationId = null;
                document.getElementById('current-conversation').textContent = '新对话';
                showToast('已切换到单机对话模式');
            }
        } else {
            showToast(res.error || '切换模式失败', true);
            return;
        }

        STATE.collabConversationId = null;
    } catch (e) {
        console.error('切换到单机模式失败', e);
        showToast('切换到单机模式失败', true);
    }
}

export async function createNewStandaloneConversation() {
    showToast('正在创建新的单机对话...');
    try {
        const res = await api('/api/conversations/switch-mode', {
            method: 'POST',
            body: JSON.stringify({ mode: 'standalone' })
        });
        showToast('已切换到单机对话模式');
        showView('chat');
        document.getElementById('messages').innerHTML = '';
        STATE.currentConversationId = res.conversation_id || null;
        document.getElementById('current-conversation').textContent = '新对话';
    } catch (e) {
        showToast('创建单机对话失败', true);
    }
}

export async function createNewCollabConversation() {
    showToast('正在创建新的协作对话...');
    try {
        const res = await api('/api/conversations/switch-mode', {
            method: 'POST',
            body: JSON.stringify({ mode: 'collaboration' })
        });
        showToast('已切换到协作对话模式');
        showView('collab-chat');
        document.getElementById('collab-messages').innerHTML = '';
        STATE.collabConversationId = res.conversation_id || null;
        document.getElementById('current-conversation').textContent = '新协作对话';
    } catch (e) {
        showToast('创建协作对话失败', true);
    }
}

export function exportConversation(format) {
    if (STATE.currentView === 'collab-chat') {
        const url = format === 'json' ? '/api/rooms/collab/export/json' : '/api/rooms/collab/export';
        window.open(url, '_blank');
        showToast('正在导出协作' + (format === 'json' ? 'JSON' : 'Markdown') + '文件...');
    } else {
        const url = format === 'json' ? '/api/export/json' : '/api/export';
        window.open(url, '_blank');
        showToast('正在导出' + (format === 'json' ? 'JSON' : 'Markdown') + '文件...');
    }
}

export async function loadConversationList() {
    const container = document.getElementById('conversation-list');
    try {
        const res = await api('/api/conversations');
        if (res.success) {
            if (res.conversations.length === 0) {
                container.innerHTML = '<p>暂无对话历史</p>';
            } else {
                container.innerHTML = res.conversations.map(c => `
                    <div class="room-card" onclick="window.loadConversation('${c.conversation_id}')">
                        <h4>${c.title || '未命名对话'}</h4>
                        <p>更新时间: ${formatTime(c.updated_at)}</p>
                        <p>消息数: ${c.message_count}</p>
                        <button class="btn btn-danger" style="font-size:12px;padding:2px 8px;" onclick="event.stopPropagation();window.deleteConversation('${c.conversation_id}')">删除</button>
                    </div>
                `).join('');
            }
        } else {
            container.innerHTML = '<p>加载对话历史失败</p>';
        }
    } catch (e) {
        console.error('加载对话历史失败', e);
        container.innerHTML = '<p>加载对话历史失败</p>';
    }
}

export async function loadConversation(conversationId) {
    try {
        const res = await api(`/api/conversation/${conversationId}`);
        if (res.success) {
            STATE.currentConversationId = conversationId;
            document.getElementById('current-conversation').textContent = res.conversation.title;
            showView('chat');
            renderConversation(res.conversation);
        } else {
            showToast('加载对话失败', true);
        }
    } catch (e) {
        showToast('加载对话失败', true);
    }
}

export function renderConversation(conversation) {
    const container = document.getElementById('messages');
    container.innerHTML = '';
    conversation.messages.forEach(msg => {
        appendMessage(msg.role, msg.content);
    });
}

export async function deleteConversation(conversationId) {
    if (!confirm('确定删除此对话?')) return;
    try {
        const res = await api(`/api/conversation/${conversationId}`, {
            method: 'DELETE'
        });
        if (res.success) {
            showToast('已删除');
            if (STATE.currentConversationId === conversationId) {
                STATE.currentConversationId = null;
                document.getElementById('current-conversation').textContent = '未选择';
            }
            loadConversationList();
        } else {
            showToast(res.error || '删除失败', true);
        }
    } catch (e) {
        showToast('删除失败', true);
    }
}

export async function createNewConversation() {
    try {
        const res = await api('/api/conversation', {
            method: 'POST',
            body: JSON.stringify({})
        });
        if (res.success) {
            STATE.currentConversationId = res.conversation_id;
            document.getElementById('current-conversation').textContent = res.conversation.title;
            showView('chat');
            document.getElementById('messages').innerHTML = '';
            showToast('已创建新对话');
        } else {
            showToast(res.error || '创建失败', true);
        }
    } catch (e) {
        showToast('创建对话失败', true);
    }
}
