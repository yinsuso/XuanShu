import { STATE } from '../state.js';
import { api } from '../api.js';
import { showToast, showView, markdownToHtml, escapeHtml } from '../utils.js';
import { renderMembers } from './room-detail.js';

export async function startCollabChat() {
    showView('collab-chat');
    await initCollabChat();
    updateCollabInputState();
}

export async function initCollabChat() {
    const chatContainer = document.getElementById('collab-messages');
    try {
        const res = await api('/api/rooms/collab/messages');
        if (res.success && res.messages && res.messages.length > 0) {
            chatContainer.innerHTML = '';
            res.messages.forEach(msg => {
                const role = msg.role || 'assistant';
                const content = msg.content || '';
                const meta = msg.metadata || {};
                const agentName = meta.agent_name || null;
                appendCollabMessage(role, content, agentName);
            });
            console.log(`📩 已从后端加载 ${res.messages.length} 条历史协作消息`);
        } else {
            if (chatContainer && chatContainer.children.length === 0) {
                appendCollabMessage('system', '🤝 欢迎进入协作对话模式！所有Agent的任务状态和返回结果都将在这里实时显示。');
            }
        }
    } catch (e) {
        console.error('加载历史协作消息失败:', e);
        if (chatContainer && chatContainer.children.length === 0) {
            appendCollabMessage('system', '🤝 欢迎进入协作对话模式！所有Agent的任务状态和返回结果都将在这里实时显示。');
        }
    }
    await refreshCollabMembers();
    if (STATE.collabMemberTimer) clearInterval(STATE.collabMemberTimer);
    STATE.collabMemberTimer = setInterval(refreshCollabMembers, 3000);
    updateCollabInputState();
}

export function updateCollabInputState() {
    const input = document.getElementById('collab-message-input');
    const sendBtn = document.getElementById('collab-send-btn');
    const shouldDisable = STATE.role === 'worker' && STATE.nodeMode === 'auto';

    if (input) {
        input.disabled = shouldDisable;
        input.placeholder = shouldDisable
            ? '🤖 自动模式下无法发送消息（由房主发起协作任务）'
            : '向协作Agent发送指令...';
        input.style.opacity = shouldDisable ? '0.5' : '1';
        input.style.cursor = shouldDisable ? 'not-allowed' : 'text';
    }

    if (sendBtn) {
        sendBtn.disabled = shouldDisable;
        sendBtn.style.opacity = shouldDisable ? '0.5' : '1';
        sendBtn.style.cursor = shouldDisable ? 'not-allowed' : 'pointer';
    }
}

export async function refreshCollabMembers() {
    if (STATE.currentView !== 'collab-chat' && STATE.currentView !== 'room-detail') {
        if (STATE.collabMemberTimer) clearInterval(STATE.collabMemberTimer);
        return;
    }
    try {
        const data = await api('/api/rooms/current');
        if (data.success && data.members_detail) {
            renderMembers(data.members_detail);
            if (STATE.currentView === 'collab-chat') {
                renderCollabMembers(data.members_detail);
            }
            document.getElementById('online-count').textContent = data.members_detail.filter(m => m.status === 'active' || m.status === 'busy').length;
        }
    } catch (e) {
        console.error('刷新成员状态失败:', e);
    }
}

export function renderCollabMembers(members) {
    const panel = document.getElementById('collab-members-panel');
    if (!panel) return;

    if (!members || members.length === 0) {
        panel.innerHTML = '<p style="color:#666;">暂无成员</p>';
        return;
    }

    panel.innerHTML = members.map(m => {
        const statusText = m.status === 'active' ? '🟢 空闲' : m.status === 'busy' ? '🔴 忙碌中' : '⚪ 离线';
        const statusClass = m.status === 'active' ? 'status-online' : m.status === 'busy' ? 'status-busy' : 'status-offline';
        const isOwner = m.is_owner ? '<span style="font-size:10px;background:#ffc107;color:#333;padding:1px 4px;border-radius:4px;">房主</span>' : '';
        const modelType = (m.model || '').toLowerCase();
        let modelTypeTag = '';
        if (modelType.includes('api') || modelType.includes('remote') || modelType.includes('dashscope') || modelType.includes('openai')) {
            modelTypeTag = '<span style="font-size:10px;background:#2196f3;color:#fff;padding:1px 4px;border-radius:4px;margin-left:4px;">云端API</span>';
        } else {
            modelTypeTag = '<span style="font-size:10px;background:#4caf50;color:#fff;padding:1px 4px;border-radius:4px;margin-left:4px;">本地</span>';
        }

        return `
            <div style="padding:10px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <strong>${m.name}</strong>
                        ${isOwner}
                    </div>
                    <div style="font-size:12px;color:#556;margin-top:4px;display:flex;align-items:center;">
                        <span style="word-break:break-all;">${m.model}</span>
                        ${modelTypeTag}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div class="${statusClass}" style="font-size:13px;padding:4px 10px;border-radius:12px;">${statusText}</div>
                </div>
            </div>
        `;
    }).join('');
}

export async function sendCollabMessage() {
    const input = document.getElementById('collab-message-input');
    const sendBtn = document.getElementById('collab-send-btn');
    const text = input.value.trim();
    if (!text) return;

    // 【内置命令处理】识别协作模式通用内置命令
    const lowerText = text.toLowerCase();
    if (lowerText.startsWith('/')) {
        const handled = await handleCollabBuiltinCommand(text, lowerText, input);
        if (handled) return;
    }

    appendCollabMessage('user', text);
    input.value = '';
    sendBtn.disabled = true;
    sendBtn.textContent = '分发任务中...';

    try {
        const payload = { message: text, mode: 'collaborative' };
        if (STATE.currentConversationId) {
            payload.conversation_id = STATE.currentConversationId;
        }

        const taskRes = await api('/api/rooms/start_task', {
            method: 'POST',
            body: JSON.stringify({
                task_type: 'collaborative_task',
                description: text
            })
        });

        if (taskRes.success) {
            showToast('协作任务已分发');
            if (taskRes.collab_conversation_id) {
                STATE.collabConversationId = taskRes.collab_conversation_id;
            }
        } else {
            showToast(taskRes.error || '分发失败', true);
        }
    } catch (e) {
        appendCollabMessage('assistant', '❌ 网络错误: ' + e.message);
        console.error('协作对话错误:', e);
    } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = '发送';
    }
}

/**
 * 【协作模式内置命令处理器】
 * 处理常用且通用的内置命令，返回 true 表示命令已处理
 */
async function handleCollabBuiltinCommand(originalText, lowerText, input) {
    input.value = '';

    switch (lowerText) {
        case '/new':
        case '/reset':
            appendCollabMessage('system', `📢 收到内置命令「${originalText}」，正在开启新的协作对话...`);
            try {
                if (window.createNewCollabConversation) {
                    await window.createNewCollabConversation();
                    appendCollabMessage('system', '✅ 已开启新的协作对话，历史记录已保存。');
                } else {
                    showToast('创建新对话功能未就绪', true);
                }
            } catch (e) {
                showToast('创建新协作对话失败: ' + e.message, true);
                console.error('内置命令 /new 或 /reset 执行失败:', e);
            }
            return true;

        case '/clear':
            appendCollabMessage('system', `📢 收到内置命令「${originalText}」，正在清屏...`);
            document.getElementById('collab-messages').innerHTML = '';
            showToast('屏幕已清空');
            return true;

        case '/export':
        case '/save':
            appendCollabMessage('system', `📢 收到内置命令「${originalText}」，正在导出协作对话...`);
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

        case '/members':
        case '/status':
            appendCollabMessage('system', `📢 收到内置命令「${originalText}」，正在刷新成员状态...`);
            try {
                await refreshCollabMembers();
                appendCollabMessage('system', '✅ 成员状态已刷新。');
            } catch (e) {
                showToast('刷新成员状态失败: ' + e.message, true);
            }
            return true;

        case '/room':
        case '/info':
            appendCollabMessage('system', `📢 收到内置命令「${originalText}」，正在加载房间信息...`);
            try {
                if (window.showView) {
                    window.showView('room-detail');
                } else {
                    showToast('房间信息功能未就绪', true);
                }
            } catch (e) {
                showToast('加载房间信息失败: ' + e.message, true);
            }
            return true;

        case '/model':
        case '/models':
            appendCollabMessage('system', `📢 收到内置命令「${originalText}」，正在打开模型管理...`);
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
            appendCollabMessage('system', getCollabHelpText());
            return true;

        default:
            // 未识别的命令，恢复输入并返回 false 让上层继续处理
            input.value = originalText;
            return false;
    }
}

/**
 * 【协作模式帮助文本】
 */
function getCollabHelpText() {
    return `📖 **协作模式内置命令列表**

| 命令 | 说明 |
|------|------|
| /new 或 /reset | 开启新的协作对话 |
| /clear | 清空当前协作对话屏幕 |
| /export 或 /save | 导出当前协作对话为 Markdown |
| /members 或 /status | 刷新并显示成员状态 |
| /room 或 /info | 打开房间信息页面 |
| /model 或 /models | 打开模型管理页面 |
| /help 或 /? | 显示此帮助信息 |

💡 提示：所有命令不区分大小写`;
}

export function appendCollabMessage(role, content, agentName = null) {
    const container = document.getElementById('collab-messages');
    if (!container) return;

    // 【修复P1-032】去重检查：如果最后一条消息的内容和角色完全相同，则不重复添加
    const lastChild = container.lastElementChild;
    if (lastChild && lastChild.dataset.content === content && lastChild.dataset.role === role) {
        console.log('🔄 [去重] 跳过重复消息:', content.slice(0, 30));
        return;
    }

    // 【修复P1-035】增强去重：检查最近5条消息中是否有相同内容和角色的消息
    const recentMessages = Array.from(container.children).slice(-5);
    for (const msg of recentMessages) {
        if (msg.dataset.content === content && msg.dataset.role === role) {
            console.log('🔄 [增强去重] 跳过重复消息:', content.slice(0, 30));
            return;
        }
    }

    const div = document.createElement('div');

    let displayRole = role;
    let avatarIcon = '🤝';
    if (agentName) {
        avatarIcon = '🤖';
        displayRole = 'assistant';
    }

    div.className = 'message ' + (role === 'user' ? 'user-message' : role === 'system' ? '' : 'assistant-message');
    const renderedContent = (role === 'assistant' || role === 'system') ? markdownToHtml(content) : escapeHtml(content);

    let prefixHtml = '';
    if (agentName) {
        prefixHtml = `<div style="font-size:12px;color:#007bff;margin-bottom:4px;">📩 来自 Agent「${agentName}」</div>`;
    } else if (role === 'system') {
        prefixHtml = `<div style="font-size:12px;color:#666;margin-bottom:4px;">📢 系统通知</div>`;
    }

    const msgIndex = container.children.length;
    div.innerHTML = `
        <div class='avatar'>${avatarIcon}</div>
        <div class='message-content'>
            ${prefixHtml}
            ${renderedContent}
            <div style="margin-top:8px;display:flex;gap:4px;">
                <button class="btn" style="font-size:11px;padding:2px 6px;width:auto;" onclick="window.copyCollabMessage(this, ${msgIndex})">📋 复制</button>
            </div>
        </div>
    `;
    div.dataset.index = msgIndex;
    div.dataset.content = content;
    div.dataset.role = role;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

export function copyCollabMessage(btn, index) {
    const msgDiv = document.querySelector(`#collab-messages .message[data-index="${index}"]`);
    if (msgDiv) {
        const content = msgDiv.dataset.content || msgDiv.querySelector('.message-content').textContent;
        navigator.clipboard.writeText(content).then(() => {
            showToast('已复制到剪贴板');
        }).catch(() => {
            showToast('复制失败', true);
        });
    }
}
