import { api } from '../api.js';
import { showToast } from '../utils.js';
import { enterRoom } from './room-detail.js';

export async function createRoom() {
    const name = document.getElementById('new-room-name').value.trim();
    const owner = document.getElementById('new-room-owner').value.trim();
    const model = document.getElementById('new-room-model').value;
    const password = document.getElementById('new-room-password').value;
    if (!name || !owner) {
        showToast('请填写房间名和房主名', true);
        return;
    }
    try {
        const res = await api('/api/rooms/create', {
            method: 'POST',
            body: JSON.stringify({ room_name: name, owner_name: owner, model, password })
        });
        if (res.success) {
            showToast('房间创建成功');
            await enterRoom(res.room_id);
        } else {
            showToast(res.error || '创建失败', true);
        }
    } catch (e) {
        showToast('创建房间请求失败', true);
        console.error(e);
    }
}
