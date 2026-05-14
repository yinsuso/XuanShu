import { api } from '../api.js';
import { showToast } from '../utils.js';

export async function refreshRooms() {
    try {
        const data = await api('/api/rooms/list');
        if (!data.success) {
            document.getElementById('room-list-container').innerHTML = '<p>获取房间列表失败</p>';
            return;
        }

        const rooms = data.rooms || [];
        if (rooms.length === 0) {
            document.getElementById('room-list-container').innerHTML = '<p>尚未创建房间</p>';
            return;
        }

        document.getElementById('room-list-container').innerHTML = rooms.map(room => `
            <div class="room-card" onclick='window.handleRoomCardClick(${JSON.stringify(room).replace(/'/g, "\\x27")})'>
                <h4>${room.room_name} <small>${room.room_id.slice(-8)}</small></h4>
                <p>房主: ${room.owner_name || '未知'}</p>
                <p>模型: ${room.owner_model || '未知'}</p>
                <p>成员数: ${room.total_members || 0}</p>
                <p>房间状态: ${room.status === 'active' ? '🟢 活跃' : '🟡 等待中'}</p>
                ${room.has_password ? '<p>🔒 已加密</p>' : ''}
            </div>
        `).join('');

        if (rooms.length > 0) {
            const firstRoom = rooms[0];
            if (firstRoom.members_detail && firstRoom.members_detail.length > 0) {
                const { renderMembers } = await import('./room-detail.js');
                renderMembers(firstRoom.members_detail);
                document.getElementById('online-count').textContent = firstRoom.members_detail.filter(m => m.status === 'online').length;
            } else {
                document.getElementById('member-list').innerHTML = '<p>暂无其他成员</p>';
                document.getElementById('online-count').textContent = '1';
            }
        }
    } catch (e) {
        showToast('获取房间信息失败', true);
        console.error(e);
    }
}

export function filterRooms() {
    const search = document.getElementById('room-search').value.toLowerCase();
    const cards = document.querySelectorAll('.room-card');
    cards.forEach(card => {
        const text = card.textContent.toLowerCase();
        card.style.display = text.includes(search) ? '' : 'none';
    });
}
