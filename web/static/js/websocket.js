import { STATE } from './state.js';
import { api } from './api.js';
import { showToast, showView } from './utils.js';
import { renderMembers } from './views/room-detail.js';
import { appendCollabMessage, renderCollabMembers, initCollabChat, updateCollabInputState } from './views/collab-chat.js';

export function connectWebSocket() {
    if (STATE.ws && (STATE.ws.readyState === WebSocket.OPEN || STATE.ws.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/cluster/ws/updates`;

    try {
        STATE.ws = new WebSocket(wsUrl);

        STATE.ws.onopen = function() {
            document.getElementById('ws-status').textContent = '已连接';
            document.getElementById('ws-status').style.color = 'green';
        };

        STATE.ws.onmessage = async function(event) {
            try {
                const msg = JSON.parse(event.data);
                await handleClusterEvent(msg);
            } catch (e) {
                console.log('[WebSocket] 消息解析失败:', e);
            }
        };

        STATE.ws.onclose = function() {
            document.getElementById('ws-status').textContent = '断开';
            document.getElementById('ws-status').style.color = 'red';
            if (!STATE.wsReconnectTimer) {
                STATE.wsReconnectTimer = setTimeout(() => {
                    STATE.wsReconnectTimer = null;
                    connectWebSocket();
                }, 3000);
            }
        };

        STATE.ws.onerror = function(error) {
            console.error('[WebSocket] 错误:', error);
        };

    } catch (e) {
        console.error('[WebSocket] 连接创建失败:', e);
    }
}

async function handleClusterEvent(data) {
    console.log('收到集群事件:', data);

    if (data.type === 'room_info_update') {
        const roomInfo = data.room_info;
        if (roomInfo) {
            if (roomInfo.members_detail && roomInfo.members_detail.length > 0) {
                renderMembers(roomInfo.members_detail);
                renderCollabMembers(roomInfo.members_detail);
                document.getElementById('online-count').textContent = roomInfo.members_detail.filter(m =>
                    m.status === 'active' || m.status === 'busy' || m.status === 'online'
                ).length;
                console.log('✅ 成员列表已实时更新，新成员数:', roomInfo.members_detail.length);
            }
            if (roomInfo.room_name && roomInfo.room_name.trim() !== '') {
                document.getElementById('detail-room-name').textContent = roomInfo.room_name;
                document.getElementById('room-name-display').textContent = roomInfo.room_name;
                console.log('✅ 房间名称已更新:', roomInfo.room_name);
            }
            if (roomInfo.room_id && roomInfo.room_id.trim() !== '') {
                document.getElementById('detail-room-id').textContent = roomInfo.room_id;
            }
            if (roomInfo.owner_model && roomInfo.owner_model.trim() !== '') {
                document.getElementById('detail-room-model').textContent = roomInfo.owner_model;
            }
            if (roomInfo.owner_name && roomInfo.owner_name.trim() !== '') {
                document.getElementById('detail-room-owner').textContent = roomInfo.owner_name;
            }
        }
        return;
    }

    if (data.type === 'collab_new_message') {
        const role = data.role || 'assistant';
        const content = data.content || '';
        const meta = data.metadata || {};
        const agentName = meta.agent_name || null;
        appendCollabMessage(role, content, agentName);
        showToast(agentName ? `收到来自 Agent「${agentName}」的回复` : '收到新消息');
        return;
    }

    if (data.type === 'joined_room_success') {
        showToast('✅ 成功进入协作房间，已进入协作模式');
        document.getElementById('cluster-badge').classList.remove('hidden');
        document.getElementById('nav-collab-chat').classList.remove('hidden');
        // 【修复P1-028】优先使用WebSocket事件携带的房间信息，避免等待API
        const displayRoomName = data.room_name || '协作房间';
        document.getElementById('room-name-display').textContent = displayRoomName;
        document.getElementById('detail-room-name').textContent = displayRoomName;
        document.getElementById('detail-room-id').textContent = data.room_id || '等待同步';
        document.getElementById('detail-room-owner').textContent = data.owner_name || '房主';
        document.getElementById('detail-room-model').textContent = data.owner_model || '未知';
        document.getElementById('current-room-info').classList.remove('hidden');
        showView('room-detail');
        const { startMemberRefresh } = await import('./views/room-detail.js');
        await startMemberRefresh();
        // 仍然调用API获取最新完整信息（后台刷新）
        try {
            const roomRes = await api('/api/rooms/current');
            if (roomRes && roomRes.success) {
                if (roomRes.room_name) {
                    document.getElementById('detail-room-name').textContent = roomRes.room_name;
                    document.getElementById('room-name-display').textContent = roomRes.room_name;
                }
                if (roomRes.room_id) {
                    document.getElementById('detail-room-id').textContent = roomRes.room_id;
                }
                if (roomRes.owner_name) {
                    document.getElementById('detail-room-owner').textContent = roomRes.owner_name;
                }
                if (roomRes.owner_model) {
                    document.getElementById('detail-room-model').textContent = roomRes.owner_model;
                }
                if (roomRes.members_detail && roomRes.members_detail.length > 0) {
                    renderMembers(roomRes.members_detail);
                }
            }
        } catch (e) {}
        return;
    }

    if (data.type === 'left_room_success') {
        showToast('✅ 已退出协作模式');
        document.getElementById('cluster-badge').classList.add('hidden');
        document.getElementById('nav-collab-chat').classList.add('hidden');
        document.getElementById('current-room-info').classList.add('hidden');
        cleanupTimers();
        showView('room-list');
        const { refreshRooms } = await import('./views/room-list.js');
        refreshRooms();
        return;
    }

    if (data.type === 'room_dismissed') {
        showToast('🏠 房主已解散房间，协作会话结束');
        document.getElementById('cluster-badge').classList.add('hidden');
        document.getElementById('nav-collab-chat').classList.add('hidden');
        document.getElementById('current-room-info').classList.add('hidden');
        cleanupTimers();
        STATE.role = 'standalone';
        showView('room-list');
        const { refreshRooms } = await import('./views/room-list.js');
        refreshRooms();
        return;
    }

    if (data.type === 'collaboration_ended') {
        showToast('🏁 协作会话已结束');
        document.getElementById('cluster-badge').classList.add('hidden');
        document.getElementById('nav-collab-chat').classList.add('hidden');
        document.getElementById('current-room-info').classList.add('hidden');
        cleanupTimers();
        STATE.role = 'standalone';
        showView('room-list');
        const { refreshRooms } = await import('./views/room-list.js');
        refreshRooms();
        return;
    }

    if (data.type === 'task_assigned') {
        addTaskLog('新任务', data.task_type, data.description);
        STATE.currentActiveTask = {
            task_id: data.task_id,
            task_type: data.task_type,
            description: data.description
        };

        if (STATE.role === 'worker') {
            document.getElementById('cluster-badge').classList.remove('hidden');
            document.getElementById('nav-collab-chat').classList.remove('hidden');
            document.getElementById('current-room-info').classList.remove('hidden');
            showToast('🎯 收到新任务，自动进入协作对话！');
            showView('collab-chat');
            await initCollabChat();
            appendCollabMessage('system', `📋 **收到新任务**\n\n类型: ${data.task_type}\n描述: ${data.description}`);
        }

        if (STATE.role === 'worker' && STATE.nodeMode === 'manual') {
            const entry = addTaskLog('新任务', data.task_type, data.description);
            const btn = document.createElement('button');
            btn.className = 'btn';
            btn.textContent = '批准';
            btn.style.width = 'auto';
            btn.style.marginLeft = '8px';
            btn.onclick = () => approveTask(entry, data.task_id, btn);
            entry.appendChild(btn);
            STATE.pendingApprovals[data.task_id] = entry;
        }
        return;
    }

    if (data.type === 'enter_collab_mode') {
        showToast('🤝 房主发起协作任务，全体进入协作对话模式！');
        document.getElementById('cluster-badge').classList.remove('hidden');
        document.getElementById('nav-collab-chat').classList.remove('hidden');
        showView('collab-chat');
        await initCollabChat();
        // 【修复】房主自己发起任务时，用户消息已在 sendCollabMessage 中本地添加
        // 此处只添加系统消息，避免重复显示用户消息
        if (STATE.role !== 'owner') {
            appendCollabMessage('user', data.description || '房主发起协作任务');
        }
        appendCollabMessage('system', `📢 协作任务详情:\n- 任务类型: ${data.task_type || 'collaborative_task'}\n- 任务描述: ${data.description || ''}`);
        return;
    }

    if (data.type === 'task_status_update') {
        const agentName = data.agent_name || '玄枢';
        const status = data.status;
        addStatusUpdate(data.task_id, data.status);

        if (status === 'assigned') {
            const isTargetMember = !data.agent_name || (STATE.myNickname && data.agent_name === STATE.myNickname);
            if (STATE.currentView !== 'collab-chat') {
                showView('collab-chat');
                await initCollabChat();
                updateCollabInputState();
                showToast(`🤖 Agent「${agentName}」已收到任务，正在处理...`);
            }
        }

        // 【修复】只在协作对话页面且状态为 assigned/running 时显示系统消息
        // completed/failed 状态已通过 collab_new_message 显示结果，避免重复
        if (STATE.currentView === 'collab-chat' && status !== 'completed' && status !== 'failed') {
            if (status === 'assigned') {
                appendCollabMessage('system', `✅ 【任务分发】Agent「${agentName}」已成功接收到任务，准备开始处理...`);
            } else if (status === 'running') {
                appendCollabMessage('system', `⚡ 【执行中】Agent「${agentName}」正在调用大模型进行推理...`);
            }
        }
        return;
    }

    // 【修复】task_update 事件与 task_status_update 功能重复，且 collab_new_message 已显示结果
    // 此处不再重复显示消息，仅更新任务日志
    if (data.type === 'task_update') {
        const agentName = data.agent_name || '未知Agent';
        const status = data.status;
        addStatusUpdate(data.task_id, data.status);
        // 不调用 appendCollabMessage，避免与 collab_new_message 重复
        return;
    }

    // 【修复】移除兜底逻辑中的重复 appendCollabMessage，避免与 collab_new_message 重复显示
    if (data.status && data.task_id) {
        addStatusUpdate(data.task_id, data.status);
        // 不调用 appendCollabMessage，状态更新已通过 collab_new_message 或 task_status_update 显示
        return;
    }

    // 【修复】task_result 与 collab_new_message (agent_result 类型) 重复
    // 优先使用 collab_new_message 显示，此处不再重复
    if (data.type === 'task_result') {
        // 结果已在 collab_new_message 中显示，此处仅显示 Toast 提示
        showToast('任务已完成！');
        return;
    }

    console.log('[WebSocket] 收到事件:', data);
}

function cleanupTimers() {
    if (STATE.memberRefreshTimer) {
        clearInterval(STATE.memberRefreshTimer);
        STATE.memberRefreshTimer = null;
    }
    if (STATE.collabMemberTimer) {
        clearInterval(STATE.collabMemberTimer);
        STATE.collabMemberTimer = null;
    }
}

function addTaskLog(msg, taskType, description) {
    const log = document.getElementById('task-log');
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="time">${new Date().toLocaleTimeString()}</span> ${msg} <small>(${taskType})</small>: ${description}`;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
    return entry;
}

function addStatusUpdate(taskId, status) {
    const log = document.getElementById('task-log');
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="time">${new Date().toLocaleTimeString()}</span> [状态] 任务 ${taskId.slice(0,8)} => ${status}`;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

async function approveTask(logEntry, taskId, btn) {
    try {
        const res = await api(`/api/cluster/tasks/${taskId}/approve`, { method: 'POST' });
        if (res.success) {
            showToast('任务已批准');
            btn.disabled = true;
            btn.textContent = '已批准';
        } else {
            showToast(res.error || '批准失败', true);
        }
    } catch (e) {
        showToast('批准请求失败', true);
    }
}
