// main.js - 玄枢 Web 界面核心逻辑 (v2.0)

// ==================== 主题切换 ====================
function changeTheme(themeName) {
  document.body.className = themeName;
  localStorage.setItem('preferred-theme', themeName);
}

function loadSavedTheme() {
  const savedTheme = localStorage.getItem('preferred-theme') || 'theme-origin';
  document.body.className = savedTheme;
  const selector = document.getElementById('theme-select');
  if(selector) selector.value = savedTheme;
}

// ==================== 页面导航 ====================
let currentPage = 'chat'; // 'chat', 'memory', 'cluster', 'stats', 'settings'

function switchPage(pageName) {
  currentPage = pageName;
  
  // 更新导航栏激活状态
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });
  
  // 根据页面名称高亮对应导航项
  const navMap = {
    'chat': 0,
    'memory': 1,
    'cluster': 2,
    'stats': 3,
    'settings': 4
  };
  
  const navIndex = navMap[pageName];
  if(navIndex !== undefined) {
    const navItems = document.querySelectorAll('.nav-item');
    if(navItems[navIndex]) {
      navItems[navIndex].classList.add('active');
    }
  }
  
  // 切换页面内容
  document.querySelectorAll('.page-section').forEach(section => {
    section.style.display = 'none';
  });
  
  const targetSection = document.getElementById(`page-${pageName}`);
  if(targetSection) {
    targetSection.style.display = 'block';
  }
  
  // 更新标题
  const titleMap = {
    'chat': '智能对话空间',
    'memory': '核心记忆库',
    'cluster': '集群协作空间',
    'stats': 'Token 使用统计',
    'settings': '系统设置'
  };
  
  const titleEl = document.querySelector('.header-title');
  if(titleEl) {
    titleEl.textContent = titleMap[pageName] || '玄枢';
  }
  
  // 页面特定初始化
  if(pageName === 'memory') {
    loadMemory();
  } else if(pageName === 'settings') {
    loadModels();
  } else if(pageName === 'cluster') {
    startClusterPolling();
  } else if(pageName === 'stats') {
    loadTokenStats();
  } else {
    stopClusterPolling();
  }
}

// ==================== 对话功能 ====================
async function sendMessage() {
  if(currentPage !== 'chat') return;
  
  const input = document.getElementById('message-input');
  const text = input.value.trim();
  if (!text) return;

  appendMessage('user', text);
  input.value = '';
  
  const loading = document.getElementById('typing-indicator');
  if(loading) loading.classList.add('active');

  try {
    const formData = new FormData();
    formData.append('message', text);
    const res = await fetch('/api/chat', { method: 'POST', body: formData });
    const data = await res.json();
    if(data.success) {
      appendMessage('assistant', data.response);
    } else {
      appendMessage('assistant', '❌ Error: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    appendMessage('assistant', '❌ Network Error: ' + e.message);
  } finally {
    if(loading) loading.classList.remove('active');
  }
}

function copyToClipboard(button) {
  const messageDiv = button.closest('.message');
  const contentDiv = messageDiv.querySelector('.message-content');
  const text = contentDiv.innerText;

  navigator.clipboard.writeText(text).then(() => {
    const originalText = button.textContent;
    button.textContent = '✅ 已复制';
    button.classList.add('copied');
    setTimeout(() => {
      button.textContent = originalText;
      button.classList.remove('copied');
    }, 2000);
  }).catch(err => {
    alert('复制失败: ' + err.message);
  });
}

function retryMessage(button) {
  const messageDiv = button.closest('.message');
  // 查找前一条用户消息
  const prevMessage = messageDiv.previousElementSibling;
  if (!prevMessage || !prevMessage.classList.contains('user-message')) {
    alert('未找到可重试的用户消息');
    return;
  }
  const userContentDiv = prevMessage.querySelector('.message-content');
  if (!userContentDiv) {
    alert('无法获取用户消息内容');
    return;
  }
  const originalText = userContentDiv.innerText.trim();
  if (!originalText) {
    alert('用户消息为空');
    return;
  }

  // 将原消息重新填入输入框并发送
  const input = document.getElementById('message-input');
  if (input) {
    input.value = originalText;
    // 自动发送
    sendMessage();
  }
}

function appendMessage(role, content) {
  const container = document.getElementById('messages');
  if(!container) return;
  const div = document.createElement('div');
  div.className = 'message ' + (role === 'user' ? 'user-message' : 'assistant-message');

  // 渲染 Markdown（仅助手消息）
  let renderedContent = content;
  if(role === 'assistant' && typeof marked !== 'undefined') {
    try {
      renderedContent = marked.parse(content);
    } catch (e) {
      renderedContent = content; // 降级为原始文本
    }
  }

  // 助手消息添加操作按钮（复制、重新回复）
  let actionsHtml = '';
  if(role === 'assistant') {
    actionsHtml = `
      <div class="message-actions">
        <button class="copy-btn" onclick="copyToClipboard(this)" title="复制内容">📋 复制</button>
        <button class="retry-btn" onclick="retryMessage(this)" title="重新生成"> ↩️ 重新回复</button>
      </div>
    `;
  }

  div.innerHTML = `
    <div class="avatar ${role === 'user' ? 'user-avatar' : 'assistant-avatar'}">${role === 'user' ? '👤' : '🤖'}</div>
    <div class="message-content">${renderedContent}</div>
    ${actionsHtml}
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

// ==================== 导出功能 ====================
async function exportConversation() {
  try {
    const res = await fetch('/api/export');
    if(res.ok) {
      // 触发下载
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'agent_conversation_export.md';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } else {
      const data = await res.json();
      alert('导出失败：' + (data.error || '未知错误'));
    }
  } catch (e) {
    alert('网络错误：' + e.message);
  }
}

// ==================== 记忆页面功能 ====================
async function loadMemory() {
  const container = document.getElementById('memory-list');
  if(!container) return;
  
  container.innerHTML = '<p>加载中...</p>';
  
  try {
    const res = await fetch('/api/memory');
    const data = await res.json();
    
    if(data.success && data.memories) {
      if(data.memories.length === 0) {
        container.innerHTML = '<p>暂无核心记忆</p>';
        return;
      }
      
      let html = '<ul style="list-style: none; padding: 0;">';
      data.memories.forEach(mem => {
        html += `
          <li style="background: var(--bg-card); padding: 10px; margin-bottom: 8px; border-radius: 6px; border-left: 3px solid var(--primary-color);">
            <strong>${mem.key}</strong>: ${mem.value}
          </li>
        `;
      });
      html += '</ul>';
      container.innerHTML = html;
    } else {
      container.innerHTML = '<p>加载失败</p>';
    }
  } catch (e) {
    container.innerHTML = '<p>网络错误</p>';
  }
}

// ==================== 统计页面功能 ====================
let statsChart = null;

async function loadTokenStats() {
  const container = document.getElementById('stats-content');
  if(!container) return;
  
  container.innerHTML = '<p>加载中...</p>';
  
  try {
    const res = await fetch('/api/token-stats');
    const data = await res.json();
    
    if(data.success && data.data) {
      const stats = data.data;
      
      // 总统计卡片
      let html = `
        <div class="stats-overview">
          <div class="stat-card">
            <h3>总 Token 消耗</h3>
            <div class="stat-value">${stats.total.total_tokens.toLocaleString()}</div>
          </div>
          <div class="stat-card">
            <h3>Prompt Tokens</h3>
            <div class="stat-value">${stats.total.prompt_tokens.toLocaleString()}</div>
          </div>
          <div class="stat-card">
            <h3>Completion Tokens</h3>
            <div class="stat-value">${stats.total.completion_tokens.toLocaleString()}</div>
          </div>
        </div>
      `;
      
      // 按模型统计
      if(stats.by_model && stats.by_model.length > 0) {
        html += '<h3>按模型统计</h3><ul style="list-style: none; padding: 0;">';
        stats.by_model.forEach(item => {
          html += `
            <li style="background: var(--bg-card); padding: 10px; margin-bottom: 8px; border-radius: 6px; display: flex; justify-content: space-between;">
              <span>${item.model}</span>
              <span>${item.total.toLocaleString()} tokens (${item.count}次)</span>
            </li>
          `;
        });
        html += '</ul>';
      }
      
      // 按日期统计 (图表)
      if(stats.by_date && stats.by_date.length > 0) {
        html += `
          <h3>最近 7 天趋势</h3>
          <canvas id="statsChart" style="max-height: 300px; margin-top: 15px;"></canvas>
        `;
      }
      
      container.innerHTML = html;
      
      // 渲染图表
      if(stats.by_date && stats.by_date.length > 0 && typeof Chart !== 'undefined') {
        const ctx = document.getElementById('statsChart').getContext('2d');
        const labels = stats.by_date.map(d => d.date);
        const values = stats.by_date.map(d => d.total);
        
        if(statsChart) statsChart.destroy();
        
        statsChart = new Chart(ctx, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [{
              label: 'Token 消耗',
              data: values,
              backgroundColor: 'rgba(33, 150, 243, 0.6)',
              borderColor: 'rgba(33, 150, 243, 1)',
              borderWidth: 1
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              y: {
                beginAtZero: true,
                ticks: {
                  color: getComputedStyle(document.body).getPropertyValue('--text-primary')
                }
              },
              x: {
                ticks: {
                  color: getComputedStyle(document.body).getPropertyValue('--text-primary')
                }
              }
            },
            plugins: {
              legend: {
                labels: {
                  color: getComputedStyle(document.body).getPropertyValue('--text-primary')
                }
              }
            }
          }
        });
      }
    } else {
      container.innerHTML = '<p>加载失败</p>';
    }
  } catch (e) {
    container.innerHTML = '<p>网络错误：' + e.message + '</p>';
  }
}

// ==================== 设置页面功能 ====================
async function loadModels() {
  const select = document.getElementById('model-select');
  if(!select) return;
  
  try {
    const res = await fetch('/api/models');
    const data = await res.json();
    
    if(data.success && data.models) {
      select.innerHTML = '';
      data.models.forEach(model => {
        const option = document.createElement('option');
        option.value = model.name;
        option.textContent = `${model.name} (${model.model_name})`;
        if(model.name === data.current_config) {
          option.selected = true;
        }
        select.appendChild(option);
      });
    }
  } catch (e) {
    console.error('Failed to load models:', e);
  }
}

async function switchModel() {
  const select = document.getElementById('model-select');
  if(!select) return;
  
  const name = select.value;
  const formData = new FormData();
  formData.append('name', name);
  
  try {
    const res = await fetch('/api/switch_model', { method: 'POST', body: formData });
    const data = await res.json();
    if(data.success) {
      alert('已切换到模型：' + name);
    } else {
      alert('切换失败：' + data.error);
    }
  } catch (e) {
    alert('网络错误');
  }
}

// ==================== 设置页面功能：保存新增模型 ====================
async function saveModel() {
  const nameEl = document.getElementById('new-model-name');
  const providerEl = document.getElementById('new-model-provider');
  const modelNameEl = document.getElementById('new-model-model-name');
  const apiBaseEl = document.getElementById('new-model-api-base');
  const apiKeyEl = document.getElementById('new-model-api-key');

  const name = nameEl?.value.trim();
  const provider = providerEl?.value;
  const model_name = modelNameEl?.value.trim();
  const api_base = apiBaseEl?.value.trim();
  const api_key = apiKeyEl?.value.trim();

  if(!name || !provider || !model_name || !api_base) {
    alert('请填写配置名称、提供商、模型名称和API地址');
    return;
  }

  const formData = new FormData();
  formData.append('name', name);
  formData.append('provider', provider);
  formData.append('model_name', model_name);
  formData.append('api_base', api_base);
  formData.append('api_key', api_key);

  try {
    const res = await fetch('/api/save_model', { method: 'POST', body: formData });
    const data = await res.json();
    if(data.success) {
      alert('模型配置已保存');
      // 清空表单
      nameEl.value = '';
      modelNameEl.value = '';
      apiBaseEl.value = '';
      apiKeyEl.value = '';
      // 刷新模型列表
      loadModels();
    } else {
      alert('保存失败：' + data.error);
    }
  } catch (e) {
    alert('网络错误：' + e.message);
  }
}

async function deleteModel() {
  const select = document.getElementById('model-select');
  if (!select) return;
  const name = select.value;
  if (!confirm(`确定要删除模型 "${name}" 吗？此操作不可撤销。`)) {
    return;
  }

  try {
    const res = await fetch('/api/delete_model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name })
    });
    const data = await res.json();
    if (data.success) {
      alert('模型已删除');
      loadModels();
    } else {
      alert('删除失败: ' + data.error);
    }
  } catch (e) {
    alert('网络错误: ' + e.message);
  }
}

// ==================== 集群协作功能 ====================
let clusterInterval = null;

async function createCluster() {
    const roomName = document.getElementById('cluster-room-name').value.trim();
    if (!roomName) {
        alert('请输入房间名称');
        return;
    }
    try {
        const res = await fetch('/api/cluster/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({room_name: roomName})
        });
        if (res.ok) {
            const data = await res.json();
            currentRoomId = data.room_id;
            clusterRole = 'manager';
            updateClusterUIRole('manager');
            alert(`房间创建成功：${data.room_name} (ID: ${data.room_id})`);
            if (clusterPoller) clearInterval(clusterPoller);
            startClusterPolling();
        } else {
            const err = await res.json();
            alert('创建失败: ' + (err.detail || '未知错误'));
        }
    } catch (e) {
        alert('创建房间请求失败: ' + e);
    }
},
      body: JSON.stringify({ room_name: roomName })
    });
    const data = await res.json();
    if(data.success) {
      alert('已创建协作房间：' + roomName);
      startClusterPolling();
    } else {
      alert('创建失败：' + data.error);
    }
  } catch (e) {
    alert('网络错误');
  }
}

async function joinCluster() {
    // 刷新房间列表并提示用户
    await checkClusterStatus();
    alert('请从左侧房间列表中选择一个房间，点击“加入”按钮');
});
    const data = await res.json();
    if(data.success) {
      alert('正在搜索并加入房间...');
      startClusterPolling();
    } else {
      alert('加入失败：' + data.error);
    }
  } catch (e) {
    alert('网络错误');
  }
}

function startClusterPolling() {
  if(clusterInterval) clearInterval(clusterInterval);
  clusterInterval = setInterval(checkClusterStatus, 3000);
  checkClusterStatus();
}

function stopClusterPolling() {
  if(clusterInterval) {
    clearInterval(clusterInterval);
    clusterInterval = null;
  }
}

async function checkClusterStatus() {
    try {
        if (currentRoomId) {
            const res = await fetch(`/api/cluster/room/${currentRoomId}/status`);
            if (res.ok) {
                const data = await res.json();
                updateRoomDetailUI(data);
                return;
            } else {
                resetClusterUI();
                return;
            }
        } else {
            const res = await fetch('/api/cluster/rooms');
            if (res.ok) {
                const data = await res.json();
                updateRoomListUI(data.rooms);
                return;
            }
        }
    } catch (e) {
        console.error('Cluster status check failed:', e);
    }
} else if(data.found_rooms && data.found_rooms.length > 0) {
        statusEl.innerHTML = '<span style="color: #2196f3;">🔍 发现房间：' + data.found_rooms.join(', ') + '</span>';
      } else {
        statusEl.innerHTML = '<span style="color: #ff9800;">🔍 搜索中...</span>';
      }
    }
  } catch (e) {
    // 静默失败
  }
}

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
  loadSavedTheme();
  
  // 绑定导航栏点击事件
  const navItems = document.querySelectorAll('.nav-item');
  const pages = ['chat', 'memory', 'cluster', 'stats', 'settings'];
  
  navItems.forEach((item, index) => {
    if(index < pages.length) {
      item.addEventListener('click', () => {
        switchPage(pages[index]);
      });
    }
  });
  
  // 绑定发送按钮
  document.getElementById('send-btn')?.addEventListener('click', sendMessage);
  document.getElementById('message-input')?.addEventListener('keypress', (e) => {
    if(e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  
  // 绑定模型切换按钮
  document.getElementById('switch-model-btn')?.addEventListener('click', switchModel);
  document.getElementById('delete-model-btn')?.addEventListener('click', deleteModel);
  
  // 绑定导出按钮
  document.querySelector('.btn-secondary.btn-sm')?.addEventListener('click', exportConversation);
  
  // 默认显示对话页面
  switchPage('chat');
});
// === 集群协作辅助函数 ===

function updateRoomListUI(rooms) {
    const list = document.getElementById('room-list');
    if (!list) return;
    list.innerHTML = '';
    if (rooms.length === 0) {
        list.innerHTML = '<p style="color:#888;padding:8px">暂无可用房间</p>';
        return;
    }
    rooms.forEach(room => {
        const div = document.createElement('div');
        div.className = 'room-item';
        div.style.padding = '8px';
        div.style.borderBottom = '1px solid #eee';
        div.innerHTML = `
            <strong>${room.room_name}</strong>
            <div style="font-size:12px;color:#666">Host: ${room.ip}:${room.host_port}</div>
            <button onclick="quickJoin('${room.room_id}', '${room.ip}', ${room.host_port})" style="margin-top:4px;padding:2px 6px;font-size:12px;cursor:pointer">加入</button>
        `;
        list.appendChild(div);
    });
}

async function quickJoin(roomId, ip, port) {
    const name = prompt('请输入你的花名（用于识别）:');
    if (!name) return;
    const mode = confirm('是否自动协作？\n确定 = 自动（授权由房主决定）\n取消 = 人工干预（部分授权需自己决定）') ? 'auto' : 'manual';
    await performJoin(roomId, ip, port, name, mode);
}

async function performJoin(roomId, ip, port, name, mode) {
    try {
        const res = await fetch(`/api/cluster/join/${roomId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({manager_ip: ip, manager_port: port})
        });
        if (res.ok) {
            const data = await res.json();
            currentRoomId = roomId;
            clusterRole = 'worker';
            memberName = name;
            memberMode = mode;
            // 同步模式到后端
            await fetch('/api/cluster/mode', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode: mode})
            });
            alert(`已加入房间 ${roomId}（模式: ${mode}）`);
            updateClusterUIRole('worker');
            if (clusterPoller) clearInterval(clusterPoller);
            startClusterPolling();
        } else {
            alert('加入失败: ' + (await res.json()).detail);
        }
    } catch (e) {
        alert('加入房间请求失败: ' + e);
    }
}

function updateRoomDetailUI(data) {
    const detail = document.getElementById('room-detail');
    if (!detail) return;
    detail.style.display = 'block';
    document.getElementById('room-name-display').textContent = data.room_name;
    document.getElementById('room-id-display').textContent = data.room_id;

    const membersDiv = document.getElementById('members-list');
    membersDiv.innerHTML = '';
    data.members.forEach(m => {
        const item = document.createElement('div');
        item.style.padding = '4px 0';
        item.innerHTML = `
            <span>${m.node_id} (${m.model})</span>
            <span class="status-${m.status}" style="margin-left:8px;color:${m.status==='online'?'green':'gray'}">${m.status}</span>
            <span style="margin-left:8px">模式: ${m.mode}</span>
            <span style="margin-left:8px">能力: ${m.capability_score.toFixed(2)}</span>
            <span style="margin-left:8px">待处理: ${m.pending_tasks}</span>
        `;
        membersDiv.appendChild(item);
    });

    // 更新UI角色区域
    updateClusterUIRole(clusterRole);
}

function updateClusterUIRole(role) {
    const createForm = document.getElementById('create-room-form') || document.querySelector('.create-room');
    const roomDetail = document.getElementById('room-detail');
    const controlPanel = document.getElementById('control-panel');
    const memberInfo = document.getElementById('member-info');
    const welcomeMsg = document.getElementById('welcome-msg');

    // 隐藏主要区域
    if (createForm) createForm.style.display = 'none';
    if (roomDetail) roomDetail.style.display = 'none';
    if (controlPanel) controlPanel.style.display = 'none';
    if (memberInfo) memberInfo.style.display = 'none';
    if (welcomeMsg) welcomeMsg.style.display = 'none';

    if (role === 'manager') {
        if (roomDetail) roomDetail.style.display = 'block';
        if (controlPanel) controlPanel.style.display = 'block';
    } else if (role === 'worker') {
        if (roomDetail) roomDetail.style.display = 'block';
        if (memberInfo) memberInfo.style.display = 'block';
        // 更新成员信息显示
        const nameSpan = document.getElementById('member-name-display');
        if (nameSpan) nameSpan.textContent = memberName;
        const modeSpan = document.getElementById('member-mode-display');
        if (modeSpan) modeSpan.textContent = memberMode;
    } else {
        if (welcomeMsg) welcomeMsg.style.display = 'block';
        if (createForm) createForm.style.display = 'block';
    }
}

function resetClusterUI() {
    currentRoomId = null;
    clusterRole = null;
    clusterManagerIp = null;
    clusterManagerPort = null;
    if (clusterPoller) {
        clearInterval(clusterPoller);
        clusterPoller = null;
    }
    updateClusterUIRole(null);
    // 隐藏详情，显示欢迎
    const detail = document.getElementById('room-detail');
    if (detail) detail.style.display = 'none';
    // 刷新房间列表
    checkClusterStatus();
}

async function startTask() {
    const taskType = document.getElementById('task-type').value.trim();
    const description = document.getElementById('task-description').value.trim();
    const parametersStr = document.getElementById('task-parameters').value.trim();
    let parameters = {};
    if (parametersStr) {
        try { parameters = JSON.parse(parametersStr); } catch (e) {
            alert('参数必须是有效的 JSON 格式');
            return;
        }
    }
    try {
        const res = await fetch(`/api/cluster/room/${currentRoomId}/start_task`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({task_type: taskType, description: description, parameters: parameters})
        });
        if (res.ok) {
            const data = await res.json();
            alert(`任务已发布，任务ID: ${data.task_id}`);
            document.getElementById('task-type').value = '';
            document.getElementById('task-description').value = '';
            document.getElementById('task-parameters').value = '';
        } else {
            alert('发布失败: ' + (await res.json()).detail);
        }
    } catch (e) {
        alert('请求失败: ' + e);
    }
}

async function dismissRoom() {
    if (!confirm('确定要解散房间吗？所有成员将被断开。')) return;
    try {
        const res = await fetch(`/api/cluster/room/${currentRoomId}/dismiss`, {method: 'POST'});
        if (res.ok) {
            alert('房间已解散');
            resetClusterUI();
        } else {
            alert('解散失败: ' + (await res.json()).detail);
        }
    } catch (e) {
        alert('解散请求失败: ' + e);
    }
}

async function leaveRoom() {
    if (!confirm('确定退出房间吗？')) return;
    try {
        const res = await fetch('/api/cluster/leave', {method: 'POST'});
        if (res.ok) {
            alert('已退出房间');
            resetClusterUI();
        } else {
            alert('退出失败: ' + (await res.json()).detail);
        }
    } catch (e) {
        alert('退出请求失败: ' + e);
    }
}

async function setMode(mode) {
    try {
        const res = await fetch('/api/cluster/mode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: mode})
        });
        if (res.ok) {
            memberMode = mode;
            alert('协作模式已更新为 ' + mode);
            // 更新显示
            const modeSpan = document.getElementById('member-mode-display');
            if (modeSpan) modeSpan.textContent = mode;
        } else {
            alert('模式更新失败: ' + (await res.json()).detail);
        }
    } catch (e) {
        alert('模式更新请求失败: ' + e);
    }
}

// 暴露给全局以便 HTML onclick 调用
window.quickJoin = quickJoin;
window.performJoin = performJoin;
window.startTask = startTask;
window.dismissRoom = dismissRoom;
window.leaveRoom = leaveRoom;
window.setMode = setMode;
