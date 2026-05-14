import { STATE } from '../state.js';
import { api, loadRoomModels } from '../api.js';
import { showToast, showView } from '../utils.js';
import { connectWebSocket } from '../websocket.js';

let memberRefreshTimer = null;
let refreshFailCount = 0;
let lastMemberCount = 0;

export function renderMembers(members) {
    const list = document.getElementById('member-list');
    list.innerHTML = members.map(m => {
        // 优先使用后端返回的provider字段判断，兼容旧数据回退到模型名称判断
        const provider = (m.provider || '').toLowerCase();
        const modelName = (m.model || '').toLowerCase();
        let modelTypeTag = '';
        if (provider === 'openai_compatible' || provider === 'custom') {
            modelTypeTag = '<span style="font-size:10px;background:#2196f3;color:#fff;padding:1px 4px;border-radius:4px;margin-left:4px;">云端API</span>';
        } else if (provider === 'ollama') {
            modelTypeTag = '<span style="font-size:10px;background:#4caf50;color:#fff;padding:1px 4px;border-radius:4px;margin-left:4px;">本地</span>';
        } else if (modelName.includes('api') || modelName.includes('remote') || modelName.includes('dashscope') || modelName.includes('openai')) {
            // 旧数据兼容：根据模型名称兜底判断
            modelTypeTag = '<span style="font-size:10px;background:#2196f3;color:#fff;padding:1px 4px;border-radius:4px;margin-left:4px;">云端API</span>';
        } else {
            modelTypeTag = '<span style="font-size:10px;background:#4caf50;color:#fff;padding:1px 4px;border-radius:4px;margin-left:4px;">本地</span>';
        }
        const statusText = m.status === 'active' ? '空闲' : m.status === 'busy' ? '忙碌中' : (m.status || '离线');
        return `
        <div class="member-item">
            <div>
                <strong>${m.name}</strong>
                <div style="font-size:12px; color:#666; margin-top:4px; display:flex; align-items:center;">
                    <span>${m.model}</span>
                    ${modelTypeTag}
                </div>
            </div>
            <div>
                <span class="status-badge status-${m.status || 'offline'}">${statusText}</span>
            </div>
        </div>
    `}).join('');
}

export async function enterRoom(roomId) {
    try {
        const data = await api('/api/rooms/current');
        if (data && data.success && data.room_name && data.room_name !== "Default-Room" && data.room_ready) {
            document.getElementById('detail-room-name').textContent = data.room_name;
            document.getElementById('detail-room-id').textContent = data.room_id;
            document.getElementById('detail-room-owner').textContent = data.owner_name || '房主';
            document.getElementById('detail-room-model').textContent = data.owner_model;
            document.getElementById('detail-my-mode').textContent = '房主模式';
            document.getElementById('my-nickname').value = data.owner_name || '';

            const myModelSelect = document.getElementById('my-model');
            if (myModelSelect && data.available_models && data.available_models.length > 0) {
                myModelSelect.innerHTML = data.available_models.map(m =>
                    `<option value="${m.model}">${m.desc}</option>`
                ).join('');
                const targetModel = data.current_model || data.owner_model || '';
                if (targetModel) {
                    myModelSelect.value = targetModel;
                }
            } else {
                await loadRoomModels('my-model');
                if (data.owner_model) {
                    myModelSelect.value = data.owner_model;
                }
            }

            if (data.members_detail && data.members_detail.length > 0) {
                renderMembers(data.members_detail);
            } else {
                document.getElementById('member-list').innerHTML = '<p>暂无其他成员</p>';
            }

            document.getElementById('cluster-badge').classList.remove('hidden');
            document.getElementById('nav-collab-chat').classList.remove('hidden');
            document.getElementById('room-name-display').textContent = data.room_name;
            document.getElementById('current-room-info').classList.remove('hidden');

            showView('room-detail');
            startMemberRefresh(data.room_id);
        } else {
            showToast('房间数据未就绪，几秒后自动刷新...');
            setTimeout(() => enterRoom(roomId), 2000);
        }
    } catch (e) {
        showToast('进入房间失败', true);
        console.error(e);
    }
}

export function startMemberRefresh(roomId) {
    if (memberRefreshTimer) {
        clearInterval(memberRefreshTimer);
    }
    refreshFailCount = 0;
    lastMemberCount = 0;

    memberRefreshTimer = setInterval(async () => {
        if (STATE.currentView === 'room-detail' || STATE.currentView === 'collab-chat') {
            try {
                const data = await api('/api/rooms/current');
                if (data && data.members_detail) {
                    const currentMemberCount = data.members_detail.length;

                    if ((lastMemberCount === 0 && currentMemberCount > 0) ||
                        (lastMemberCount > 0 && currentMemberCount > lastMemberCount)) {
                        console.log(`✅ 检测到成员列表变化：${lastMemberCount} -> ${currentMemberCount}，主动更新房间信息`);

                        if (data.room_name && data.room_name.trim() !== '') {
                            document.getElementById('detail-room-name').textContent = data.room_name;
                            document.getElementById('room-name-display').textContent = data.room_name;
                        }
                        if (data.room_id && data.room_id.trim() !== '') {
                            document.getElementById('detail-room-id').textContent = data.room_id;
                        }
                        if (data.owner_name && data.owner_name.trim() !== '') {
                            document.getElementById('detail-room-owner').textContent = data.owner_name;
                        }
                        if (data.owner_model && data.owner_model.trim() !== '') {
                            document.getElementById('detail-room-model').textContent = data.owner_model;
                        }

                        if (lastMemberCount === 0 && currentMemberCount > 0) {
                            showToast('成员列表已加载，房间信息已更新');
                        } else if (currentMemberCount > lastMemberCount) {
                            showToast('有新成员加入，房间信息已更新');
                        }
                    }

                    renderMembers(data.members_detail);
                    lastMemberCount = currentMemberCount;
                    refreshFailCount = 0;

                    if (data.room_name && data.room_name.trim() !== '') {
                        document.getElementById('detail-room-name').textContent = data.room_name;
                        document.getElementById('room-name-display').textContent = data.room_name;
                    }
                    if (data.room_id && data.room_id.trim() !== '') {
                        document.getElementById('detail-room-id').textContent = data.room_id;
                    }
                    if (data.owner_name && data.owner_name.trim() !== '') {
                        document.getElementById('detail-room-owner').textContent = data.owner_name;
                    }
                    if (data.owner_model && data.owner_model.trim() !== '') {
                        document.getElementById('detail-room-model').textContent = data.owner_model;
                    }
                } else if (data && !data.is_collab_mode) {
                    console.log('⚠️ 房主已退出协作模式，成员端自动退出');
                    await handleRoomExit();
                }
            } catch (e) {
                refreshFailCount++;
                console.log(`⚠️ 获取房间信息失败，连续失败次数: ${refreshFailCount}`);

                if (refreshFailCount >= 6) {
                    console.log('❌ 连续获取房间信息失败，自动退出协作模式');
                    showToast('与房主失去连接，已自动退出协作模式', true);
                    await handleRoomExit();
                }
            }
        } else {
            clearInterval(memberRefreshTimer);
            memberRefreshTimer = null;
        }
    }, 5000);
}

export async function updateMyInfo() {
    const nickname = document.getElementById('my-nickname').value.trim();
    const model = document.getElementById('my-model').value;
    if (!nickname) {
        showToast('请输入花名', true);
        return;
    }
    try {
        const res = await api('/api/rooms/update_member', {
            method: 'POST',
            body: JSON.stringify({ nickname, model })
        });
        if (res.success) {
            showToast('信息已更新');
            STATE.myNickname = nickname;
            STATE.myModel = model;
            const { refreshRooms } = await import('./room-list.js');
            refreshRooms();
        } else {
            showToast(res.error || '更新失败', true);
        }
    } catch (e) {
        showToast('更新请求失败', true);
        console.error(e);
    }
}

export async function handleRoomExit() {
    const confirmMsg = (STATE.role === 'manager' || STATE.role === 'standalone')
        ? '确定要解散房间吗？解散后所有成员将被移除。'
        : '确定要退出房间吗？';
    if (!confirm(confirmMsg)) return;

    try {
        const endpoint = (STATE.role === 'manager' || STATE.role === 'standalone')
            ? '/api/rooms/dismiss'
            : '/api/rooms/leave';

        const res = await api(endpoint, { method: 'POST' });

        if (res.success) {
            showToast((STATE.role === 'manager' || STATE.role === 'standalone') ? '房间已解散' : '已退出房间');
            document.getElementById('cluster-badge').classList.add('hidden');
            document.getElementById('nav-collab-chat').classList.add('hidden');
            document.getElementById('current-room-info').classList.add('hidden');
            if (memberRefreshTimer) {
                clearInterval(memberRefreshTimer);
                memberRefreshTimer = null;
            }
            if (STATE.collabMemberTimer) {
                clearInterval(STATE.collabMemberTimer);
                STATE.collabMemberTimer = null;
            }
            STATE.currentRoomId = null;
            STATE.currentConversationId = null;
            STATE.collabConversationId = null;
            const messagesContainer = document.getElementById('messages');
            if (messagesContainer) {
                messagesContainer.innerHTML = '';
            }
            const collabMessagesContainer = document.getElementById('collab-messages');
            if (collabMessagesContainer) {
                collabMessagesContainer.innerHTML = '';
            }
            showView('room-list');
            const { refreshRooms } = await import('./room-list.js');
            refreshRooms();
        } else {
            showToast(res.error || '操作失败', true);
        }
    } catch (e) {
        showToast('请求失败', true);
        console.error(e);
    }
}

export async function joinRoom() {
    const host = document.getElementById('join-room-host').value.trim();
    const name = document.getElementById('join-member-name').value.trim();
    const mode = document.getElementById('join-mode').value;
    const model = document.getElementById('join-model').value;
    const password = document.getElementById('join-room-password').value;
    if (!host || !name || !model) {
        showToast('请填写房间地址、成员名称和模型', true);
        return;
    }
    try {
        const res = await api('/api/rooms/join', {
            method: 'POST',
            body: JSON.stringify({ host, name, mode, model, password })
        });
        if (res.success) {
            showToast('已成功加入协作房间');
            STATE.role = 'worker';
            STATE.nodeMode = mode;
            document.getElementById('cluster-badge').classList.remove('hidden');
            document.getElementById('nav-collab-chat').classList.remove('hidden');
            document.getElementById('detail-my-mode').textContent = (mode === 'auto' ? '🤖 自动模式' : '👤 人工干预');
            document.getElementById('current-room-info').classList.remove('hidden');
            document.getElementById('my-nickname').value = name;
            await loadRoomModels('my-model');
            const myModelSelect = document.getElementById('my-model');
            if (myModelSelect) {
                myModelSelect.value = model;
            }

            try {
                const roomRes = await api('/api/rooms/current');
                if (roomRes && roomRes.room_name && roomRes.room_name.trim() !== '') {
                    document.getElementById('detail-room-name').textContent = roomRes.room_name;
                    document.getElementById('room-name-display').textContent = roomRes.room_name;
                } else {
                    document.getElementById('detail-room-name').textContent = '协作房间';
                    document.getElementById('room-name-display').textContent = '协作房间';
                }
                if (roomRes && roomRes.room_id && roomRes.room_id.trim() !== '') {
                    document.getElementById('detail-room-id').textContent = roomRes.room_id;
                } else {
                    document.getElementById('detail-room-id').textContent = '等待房主同步';
                }
                if (roomRes && roomRes.owner_name && roomRes.owner_name.trim() !== '') {
                    document.getElementById('detail-room-owner').textContent = roomRes.owner_name;
                } else {
                    document.getElementById('detail-room-owner').textContent = '房主';
                }
                if (roomRes && roomRes.owner_model && roomRes.owner_model.trim() !== '') {
                    document.getElementById('detail-room-model').textContent = roomRes.owner_model;
                } else {
                    document.getElementById('detail-room-model').textContent = '未知';
                }
                if (roomRes && roomRes.members_detail && roomRes.members_detail.length > 0) {
                    renderMembers(roomRes.members_detail);
                } else {
                    document.getElementById('member-list').innerHTML = '<p>房主房间中，等待同步...</p>';
                }
            } catch (e) {
                document.getElementById('detail-room-name').textContent = '协作房间';
                document.getElementById('detail-room-id').textContent = '等待房主同步';
                document.getElementById('detail-room-owner').textContent = '房主';
                document.getElementById('detail-room-model').textContent = '未知';
                document.getElementById('room-name-display').textContent = '协作房间';
                document.getElementById('member-list').innerHTML = '<p>房主房间中，等待同步...</p>';
            }

            showView('room-detail');
            startMemberRefresh("pending");
            connectWebSocket();
        } else {
            showToast(res.error || '加入失败', true);
        }
    } catch (e) {
        showToast('加入请求失败', true);
        console.error(e);
    }
}
