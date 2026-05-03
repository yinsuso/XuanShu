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

function appendMessage(role, content) {
  const container = document.getElementById('messages');
  if(!container) return;
  const div = document.createElement('div');
  div.className = 'message ' + (role === 'user' ? 'user-message' : 'assistant-message');
  div.innerHTML = `
    <div class="avatar ${role === 'user' ? 'user-avatar' : 'assistant-avatar'}">${role === 'user' ? '👤' : '🤖'}</div>
    <div class="message-content">${content}</div>
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
  const roomName = document.getElementById('room-name')?.value || 'Default-Room';
  try {
    const res = await fetch('/api/cluster/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
  try {
    const res = await fetch('/api/cluster/join', { method: 'POST' });
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
  if(currentPage !== 'cluster') return;
  
  try {
    const res = await fetch('/api/cluster/status');
    const data = await res.json();
    
    const statusEl = document.getElementById('cluster-status-msg');
    if(statusEl && data.success) {
      if(data.is_hosting) {
        statusEl.innerHTML = '<span style="color: #4caf50;">✅ 正在 hosting: ' + data.room_name + '</span>';
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
