
async function createCluster() {
    const roomName = document.getElementById('room-name').value || "Default-Agent-Room";
    try {
        const res = await fetch('/api/cluster/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({room_name: roomName})
        });
        const data = await res.json();
        alert(data.message || data.error);
        updateClusterStatus();
    } catch(e) { alert('Error: ' + e.message); }
}

async function joinCluster() {
    try {
        const res = await fetch('/api/cluster/join', {method: 'POST'});
        const data = await res.json();
        alert(data.message || data.error);
        updateClusterStatus();
    } catch(e) { alert('Error: ' + e.message); }
}

async function updateClusterStatus() {
    try {
        const res = await fetch('/api/cluster/status');
        const data = await res.json();
        if(data.success) {
            const status = data.is_hosting ? `🟢 房主 [${data.room_name}]` : (data.found_rooms?.length > 0 ? `🟢 成员` : `🔴 单机模式`);
            const el = document.getElementById('cluster-status-msg');
            if(el) el.innerText = '状态：' + status;
        }
    } catch(e) { console.error('Status check failed', e); }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('cluster-btn')?.addEventListener('click', () => {
        const panel = document.getElementById('cluster-panel');
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    });
    setInterval(updateClusterStatus, 5000);
    updateClusterStatus();
});
