import { STATE } from './state.js';
import { api } from './api.js';
import { showToast, showView } from './utils.js';
import { connectWebSocket } from './websocket.js';
import { refreshRooms } from './views/room-list.js';
import { enterRoom, renderMembers, startMemberRefresh } from './views/room-detail.js';
import { loadModelList } from './views/model-manage.js';

let pendingRoomToEnter = null;
let pendingJoinRoomCallback = null;

async function init() {
    document.getElementById('api-status').textContent = '已连接';
    document.getElementById('api-status').style.color = 'green';
    document.getElementById('local-node-id').textContent = '就绪';

    try {
        const data = await api('/api/info');
        STATE.role = data.role;

        if (data.cluster_token) {
            STATE.clusterToken = data.cluster_token;
            console.log('✅ 已获取集群API Token');
        }

        const collabBtn = document.getElementById('btn-new-collab-conversation');
        const navCollabChatBtn = document.getElementById('nav-collab-chat');

        if (STATE.role === 'manager') {
            if (collabBtn) collabBtn.style.display = 'block';
            console.log('✅ 房主模式：已显示「新建协作对话」按钮');
        } else {
            if (collabBtn) collabBtn.style.display = 'none';
        }

        const startBtn = document.getElementById('btn-start-task');
        const joinBtn = document.querySelector('button[onclick="showView(\'join-room\')"]');

        if (STATE.role === 'manager' || STATE.role === 'standalone') {
            if (startBtn) startBtn.style.display = 'inline-block';
            if (joinBtn) joinBtn.style.display = 'inline-block';
            STATE.room = data.room;

            const currentRoomRes = await api('/api/rooms/current').catch(() => null);
            if (currentRoomRes && currentRoomRes.success && currentRoomRes.room_name && currentRoomRes.room_name !== "Default-Room" && currentRoomRes.room_ready) {
                document.getElementById('detail-room-name').textContent = currentRoomRes.room_name;
                document.getElementById('detail-room-id').textContent = currentRoomRes.room_id;
                document.getElementById('detail-room-owner').textContent = currentRoomRes.owner_name || '房主';
                document.getElementById('detail-room-model').textContent = currentRoomRes.owner_model;
                document.getElementById('detail-my-mode').textContent = '房主模式';

                const myModelSelect = document.getElementById('my-model');
                if (myModelSelect && currentRoomRes.available_models && currentRoomRes.available_models.length > 0) {
                    myModelSelect.innerHTML = currentRoomRes.available_models.map(m =>
                        `<option value="${m.model}">${m.desc}</option>`
                    ).join('');
                    const targetModel = currentRoomRes.current_model || currentRoomRes.owner_model || '';
                    if (targetModel) {
                        myModelSelect.value = targetModel;
                    }
                } else {
                    const { loadRoomModels } = await import('./api.js');
                    await loadRoomModels('my-model');
                    if (currentRoomRes.owner_model) {
                        myModelSelect.value = currentRoomRes.owner_model;
                    }
                }
                document.getElementById('my-nickname').value = currentRoomRes.owner_name || '';

                if (currentRoomRes.members_detail && currentRoomRes.members_detail.length > 0) {
                    renderMembers(currentRoomRes.members_detail);
                } else {
                    document.getElementById('member-list').innerHTML = '<p>暂无其他成员</p>';
                }

                document.getElementById('cluster-badge').classList.remove('hidden');
                document.getElementById('nav-collab-chat').classList.remove('hidden');
                document.getElementById('room-name-display').textContent = currentRoomRes.room_name;
                document.getElementById('current-room-info').classList.remove('hidden');

                showView('room-detail');
                startMemberRefresh(currentRoomRes.room_id);
                showToast('协作模式已自动恢复', false);
            } else {
                showView('room-list');
                await refreshRooms();
            }
        } else if (STATE.role === 'worker') {
            if (startBtn) startBtn.style.display = 'none';
            if (joinBtn) joinBtn.style.display = 'inline-block';
            STATE.nodeMode = data.mode || 'auto';
            STATE.nodeId = data.node_id;

            await api('/api/discovery/start_scan', { method: 'POST' }).catch(() => ({}));

            let roomInfo = null;
            if (data.connected) {
                try {
                    roomInfo = await api('/api/rooms/current');
                    console.log('✅ Worker主动获取房间信息:', roomInfo);
                } catch (e) {
                    console.log('⏳ Worker获取房间信息失败（可能房主暂时不可达）:', e);
                }
            }

            if (data.connected && (data.room_name || data.members_detail || roomInfo)) {
                const displayRoomName = (roomInfo?.room_name && roomInfo.room_name.trim() !== '') ? roomInfo.room_name :
                                        (data.room_name && data.room_name.trim() !== '') ? data.room_name : "协作房间";
                const displayRoomId = (roomInfo?.room_id && roomInfo.room_id.trim() !== '') ? roomInfo.room_id :
                                      (data.room_id && data.room_id.trim() !== '') ? data.room_id : "local-temp";
                const displayOwnerName = (roomInfo?.owner_name && roomInfo.owner_name.trim() !== '') ? roomInfo.owner_name :
                                         (data.owner_name && data.owner_name.trim() !== '') ? data.owner_name : "房主";
                const displayOwnerModel = (roomInfo?.owner_model && roomInfo.owner_model.trim() !== '') ? roomInfo.owner_model :
                                          (data.owner_model && data.owner_model.trim() !== '') ? data.owner_model : (data.model || "unknown");
                const displayMembers = roomInfo?.members_detail || data.members_detail || [];

                document.getElementById('detail-room-name').textContent = displayRoomName;
                document.getElementById('detail-room-id').textContent = displayRoomId;
                document.getElementById('detail-room-owner').textContent = displayOwnerName;
                document.getElementById('detail-room-model').textContent = displayOwnerModel;
                document.getElementById('detail-my-mode').textContent = STATE.nodeMode === 'auto' ? '🤖 自动模式' : '👤 人工干预';

                const myModelSelect = document.getElementById('my-model');
                const { loadRoomModels } = await import('./api.js');
                await loadRoomModels('my-model');
                document.getElementById('my-nickname').placeholder = '设置你的花名';

                if (displayMembers.length > 0) {
                    renderMembers(displayMembers);
                } else {
                    document.getElementById('member-list').innerHTML = '<p>房主房间中...</p>';
                }

                document.getElementById('cluster-badge').classList.remove('hidden');
                document.getElementById('nav-collab-chat').classList.remove('hidden');
                document.getElementById('room-name-display').textContent = displayRoomName;
                document.getElementById('current-room-info').classList.remove('hidden');

                showView('room-detail');
                startMemberRefresh(displayRoomId);
                showToast('协作模式已自动恢复', false);
            } else if (data.connected) {
                document.getElementById('cluster-badge').classList.remove('hidden');
                document.getElementById('nav-collab-chat').classList.remove('hidden');
                showView('room-detail');
                document.getElementById('detail-room-name').textContent = "协作房间";
                document.getElementById('detail-my-mode').textContent = STATE.nodeMode === 'auto' ? '🤖 自动模式' : '👤 人工干预';
                const { loadRoomModels } = await import('./api.js');
                await loadRoomModels('my-model');
                document.getElementById('room-name-display').textContent = "协作房间";
                document.getElementById('current-room-info').classList.remove('hidden');
                startMemberRefresh("unknown");
            } else {
                const nameInput = document.getElementById('join-member-name');
                if (nameInput) nameInput.value = data.node_id || '';
                const modeSelect = document.getElementById('join-mode');
                if (modeSelect) modeSelect.value = STATE.nodeMode;
                showView('join-room');
            }
        } else {
            showView('room-list');
            await refreshRooms();
        }
    } catch (e) {
        showToast('获取节点信息失败', true);
        console.error(e);
        showView('room-list');
        await refreshRooms();
    }

    await loadModelList();

    if (STATE.role === 'manager' || STATE.role === 'worker' || STATE.role === 'standalone') {
        connectWebSocket();
    }

    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) {
        sendBtn.addEventListener('click', async () => {
            const { sendMessage } = await import('./views/chat.js');
            sendMessage();
        });
        const msgInput = document.getElementById('message-input');
        if (msgInput) {
            msgInput.addEventListener('keypress', async (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    const { sendMessage } = await import('./views/chat.js');
                    sendMessage();
                }
            });
        }
    }

    document.getElementById('api-status').textContent = '已连接';
    document.getElementById('api-status').style.color = 'green';
}

window.addEventListener('DOMContentLoaded', init);

window.showView = async (viewName) => {
    const { showView: showViewFn } = await import('./utils.js');
    showViewFn(viewName);
    if (viewName === 'model-manage') {
        const { loadModelList } = await import('./views/model-manage.js');
        await loadModelList();
    } else if (viewName === 'conversation-history') {
        const { loadConversationList } = await import('./views/chat.js');
        await loadConversationList();
    } else if (viewName === 'create-room') {
        const { loadRoomModels } = await import('./api.js');
        await loadRoomModels('new-room-model');
    } else if (viewName === 'join-room') {
        const { loadRoomModels } = await import('./api.js');
        await loadRoomModels('join-model');
    } else if (viewName === 'stats') {
        const { loadStats } = await import('./views/stats.js');
        await loadStats();
    } else if (viewName === 'skill-manage') {
        const { loadSkillList } = await import('./views/skill-manage.js');
        await loadSkillList();
    }
};
window.refreshRooms = refreshRooms;
window.enterRoom = enterRoom;
window.handleRoomExit = async () => {
    const { handleRoomExit } = await import('./views/room-detail.js');
    await handleRoomExit();
};
window.joinRoom = async () => {
    const { joinRoom } = await import('./views/room-detail.js');
    await joinRoom();
};
window.createRoom = async () => {
    const { createRoom } = await import('./views/room-create.js');
    await createRoom();
};
window.updateMyInfo = async () => {
    const { updateMyInfo } = await import('./views/room-detail.js');
    await updateMyInfo();
};
window.startCollabChat = async () => {
    const { startCollabChat } = await import('./views/collab-chat.js');
    await startCollabChat();
};
window.sendCollabMessage = async () => {
    const { sendCollabMessage } = await import('./views/collab-chat.js');
    await sendCollabMessage();
};
window.enterStandaloneMode = async () => {
    const { enterStandaloneMode } = await import('./views/chat.js');
    await enterStandaloneMode();
};
window.createNewStandaloneConversation = async () => {
    const { createNewStandaloneConversation } = await import('./views/chat.js');
    await createNewStandaloneConversation();
};
window.createNewCollabConversation = async () => {
    const { createNewCollabConversation } = await import('./views/chat.js');
    await createNewCollabConversation();
};
window.exportConversation = async (format) => {
    const { exportConversation } = await import('./views/chat.js');
    await exportConversation(format);
};
window.selectModel = async (name) => {
    const { selectModel } = await import('./views/model-manage.js');
    await selectModel(name);
};
window.editModel = async (name) => {
    const { editModel } = await import('./views/model-manage.js');
    await editModel(name);
};
window.deleteModel = async (name) => {
    const { deleteModel } = await import('./views/model-manage.js');
    await deleteModel(name);
};
window.saveModel = async () => {
    const { saveModel } = await import('./views/model-manage.js');
    await saveModel();
};
window.loadModelList = async (forceReload) => {
    const { loadModelList } = await import('./views/model-manage.js');
    await loadModelList(forceReload);
};
window.loadConversation = async (conversationId) => {
    const { loadConversation } = await import('./views/chat.js');
    await loadConversation(conversationId);
};
window.deleteConversation = async (conversationId) => {
    const { deleteConversation } = await import('./views/chat.js');
    await deleteConversation(conversationId);
};
window.copyMessage = async (btn, index) => {
    const { copyMessage } = await import('./views/chat.js');
    await copyMessage(btn, index);
};
window.regenerateMessage = async (index) => {
    const { regenerateMessage } = await import('./views/chat.js');
    await regenerateMessage(index);
};
window.copyCollabMessage = async (btn, index) => {
    const { copyCollabMessage } = await import('./views/collab-chat.js');
    await copyCollabMessage(btn, index);
};
window.filterRooms = async () => {
    const { filterRooms } = await import('./views/room-list.js');
    await filterRooms();
};
window.loadSkillList = async () => {
    const { loadSkillList } = await import('./views/skill-manage.js');
    await loadSkillList();
};
window.showSkillDetail = async (name) => {
    const { showSkillDetail } = await import('./views/skill-manage.js');
    await showSkillDetail(name);
};
window.closeSkillDetail = async () => {
    const { closeSkillDetail } = await import('./views/skill-manage.js');
    closeSkillDetail();
};
window.deleteSkill = async (name) => {
    const { deleteSkill } = await import('./views/skill-manage.js');
    await deleteSkill(name);
};
window.deleteCurrentSkill = async () => {
    const { deleteCurrentSkill } = await import('./views/skill-manage.js');
    await deleteCurrentSkill();
};
window.filterSkills = async () => {
    const { filterSkills } = await import('./views/skill-manage.js');
    filterSkills();
};

window.handleRoomCardClick = async (room) => {
    pendingRoomToEnter = room;

    if (room.is_local) {
        await enterRoom(room.room_id);
        return;
    }

    showJoinRoomModal(async (formData) => {
        if (!formData) {
            showToast('已取消', true);
            return;
        }

        const host = room.ip + ':' + (room.manager_port || 30001);
        const { name, model, password } = formData;
        const mode = 'auto';

        try {
            const res = await api('/api/rooms/join', {
                method: 'POST',
                body: JSON.stringify({ host, name, mode, model, password })
            });
            if (res.success) {
                showToast('已成功加入房间');
                setTimeout(() => init(), 1000);
            } else {
                showToast(res.error || '加入失败', true);
            }
        } catch (e) {
            showToast('请求失败', true);
            console.error(e);
        }
    });
};

async function showJoinRoomModal(callback) {
    const modal = document.getElementById('join-room-modal');
    modal.classList.remove('hidden');

    document.getElementById('join-modal-name').value = '';
    document.getElementById('join-modal-password').value = '';

    const { loadRoomModels } = await import('./api.js');
    await loadRoomModels('join-modal-model');

    document.getElementById('join-modal-name').focus();

    const confirmBtn = document.getElementById('join-modal-confirm');
    const cancelBtn = document.getElementById('join-modal-cancel');

    const newConfirm = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirm, confirmBtn);
    const newCancel = cancelBtn.cloneNode(true);
    cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);

    pendingJoinRoomCallback = callback;

    newConfirm.onclick = () => {
        const name = document.getElementById('join-modal-name').value.trim();
        const model = document.getElementById('join-modal-model').value;
        const password = document.getElementById('join-modal-password').value || '';

        if (!name) {
            showToast('请输入成员花名', true);
            return;
        }

        modal.classList.add('hidden');
        if (pendingJoinRoomCallback) {
            pendingJoinRoomCallback({ name, model, password });
        }
    };

    newCancel.onclick = () => {
        modal.classList.add('hidden');
        if (pendingJoinRoomCallback) {
            pendingJoinRoomCallback(null);
        }
    };
}
