import { api } from '../api.js';

let currentStatsData = null;
let currentView = 'overview';
let selectedDays = 7;
let selectedModel = '';
let selectedDate = '';

export async function loadStats() {
    const container = document.getElementById('stats-container');
    if (!container) return;

    container.innerHTML = `
        <div class="stats-toolbar">
            <div class="stats-filter-group">
                <label>时间范围:</label>
                <select id="stats-days" onchange="window.handleStatsDaysChange(this.value)">
                    <option value="7">最近7天</option>
                    <option value="14">最近14天</option>
                    <option value="30">最近30天</option>
                    <option value="90">最近90天</option>
                </select>
            </div>
            <div class="stats-filter-group">
                <label>模型筛选:</label>
                <select id="stats-model" onchange="window.handleStatsModelChange(this.value)">
                    <option value="">全部模型</option>
                </select>
            </div>
            <div class="stats-filter-group">
                <label>日期筛选:</label>
                <select id="stats-date" onchange="window.handleStatsDateChange(this.value)">
                    <option value="">全部日期</option>
                </select>
            </div>
            <button class="btn" style="width:auto;padding:6px 16px;" onclick="window.refreshStats()">🔄 刷新</button>
        </div>

        <div class="stats-tabs">
            <button class="stats-tab active" onclick="window.switchStatsTab('overview')">📊 总览</button>
            <button class="stats-tab" onclick="window.switchStatsTab('daily')">📅 按天统计</button>
            <button class="stats-tab" onclick="window.switchStatsTab('models')">🤖 按模型统计</button>
            <button class="stats-tab" onclick="window.switchStatsTab('detail')">🔍 交叉明细</button>
            <button class="stats-tab" onclick="window.switchStatsTab('recent')">📝 最近记录</button>
        </div>

        <div id="stats-content" class="stats-content">
            <p>正在加载统计数据...</p>
        </div>
    `;

    await Promise.all([
        fetchStats(),
        loadModelFilter(),
        loadDateFilter()
    ]);
}

async function fetchStats() {
    try {
        const params = new URLSearchParams();
        params.append('detailed', 'true');
        params.append('days', selectedDays.toString());
        if (selectedModel) params.append('model', selectedModel);
        if (selectedDate) params.append('date', selectedDate);

        const [statsRes, convsRes] = await Promise.all([
            api(`/api/token-stats?${params.toString()}`),
            api('/api/conversations?limit=100')
        ]);

        if (statsRes.success) {
            currentStatsData = statsRes.data;
            renderStats();
        } else {
            document.getElementById('stats-content').innerHTML =
                `<p class="stats-error">加载统计数据失败: ${statsRes.error || '未知错误'}</p>`;
        }
    } catch (e) {
        console.error('加载统计数据失败', e);
        document.getElementById('stats-content').innerHTML =
            '<p class="stats-error">加载统计数据失败，请稍后重试</p>';
    }
}

async function loadModelFilter() {
    try {
        const res = await api('/api/token-stats/models');
        const select = document.getElementById('stats-model');
        if (!select || !res.success) return;

        const models = res.models || [];
        select.innerHTML = '<option value="">全部模型</option>' +
            models.map(m => `<option value="${m.model_name}">${m.model_name} (${m.provider})</option>`).join('');
    } catch (e) {
        console.log('加载模型筛选失败', e);
    }
}

async function loadDateFilter() {
    try {
        const res = await api(`/api/token-stats/dates?days=${selectedDays}`);
        const select = document.getElementById('stats-date');
        if (!select || !res.success) return;

        const dates = res.dates || [];
        select.innerHTML = '<option value="">全部日期</option>' +
            dates.map(d => `<option value="${d}">${d}</option>`).join('');
    } catch (e) {
        console.log('加载日期筛选失败', e);
    }
}

function renderStats() {
    if (!currentStatsData) return;

    const content = document.getElementById('stats-content');
    if (!content) return;

    switch (currentView) {
        case 'overview':
            content.innerHTML = renderOverview();
            break;
        case 'daily':
            content.innerHTML = renderDaily();
            break;
        case 'models':
            content.innerHTML = renderModels();
            break;
        case 'detail':
            content.innerHTML = renderDetail();
            break;
        case 'recent':
            content.innerHTML = renderRecent();
            break;
    }
}

function renderOverview() {
    const total = currentStatsData.total || {};
    const today = currentStatsData.today || {};
    const todayBreakdown = currentStatsData.today_breakdown || {};
    const models = todayBreakdown.models || [];

    let html = `
        <div class="stats-overview">
            <div class="stats-cards">
                <div class="stats-card total">
                    <h4>📊 累计使用</h4>
                    <div class="stats-number">${formatNumber(total.total_tokens || 0)}</div>
                    <div class="stats-detail">
                        <span>Prompt: ${formatNumber(total.prompt_tokens || 0)}</span>
                        <span>Completion: ${formatNumber(total.completion_tokens || 0)}</span>
                    </div>
                    <div class="stats-detail">
                        <span>调用次数: ${formatNumber(total.call_count || 0)}</span>
                    </div>
                </div>
                <div class="stats-card today">
                    <h4>📅 今日使用</h4>
                    <div class="stats-number">${formatNumber(today.total_tokens || 0)}</div>
                    <div class="stats-detail">
                        <span>Prompt: ${formatNumber(today.prompt_tokens || 0)}</span>
                        <span>Completion: ${formatNumber(today.completion_tokens || 0)}</span>
                    </div>
                    <div class="stats-detail">
                        <span>调用次数: ${formatNumber(today.call_count || 0)}</span>
                    </div>
                </div>
            </div>
    `;

    if (models.length > 0) {
        html += `
            <div class="stats-section">
                <h4>🤖 今日模型使用明细</h4>
                <table class="stats-table">
                    <thead>
                        <tr>
                            <th>模型</th>
                            <th>提供商</th>
                            <th>Prompt Tokens</th>
                            <th>Completion Tokens</th>
                            <th>总 Tokens</th>
                            <th>调用次数</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${models.map(m => `
                            <tr>
                                <td>${m.model_name}</td>
                                <td>${m.provider}</td>
                                <td>${formatNumber(m.prompt_tokens)}</td>
                                <td>${formatNumber(m.completion_tokens)}</td>
                                <td><strong>${formatNumber(m.total_tokens)}</strong></td>
                                <td>${formatNumber(m.call_count)}</td>
                            </tr>
                        `).join('')}
                        <tr class="stats-summary-row">
                            <td colspan="2"><strong>今日合计</strong></td>
                            <td><strong>${formatNumber(todayBreakdown.summary?.prompt_tokens || 0)}</strong></td>
                            <td><strong>${formatNumber(todayBreakdown.summary?.completion_tokens || 0)}</strong></td>
                            <td><strong>${formatNumber(todayBreakdown.summary?.total_tokens || 0)}</strong></td>
                            <td><strong>${formatNumber(todayBreakdown.summary?.call_count || 0)}</strong></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        `;
    }

    html += '</div>';
    return html;
}

function renderDaily() {
    const daily = currentStatsData.daily || [];

    if (daily.length === 0) {
        return '<p class="stats-empty">暂无按天统计数据</p>';
    }

    const chartData = daily.slice().reverse();
    const maxTokens = Math.max(...chartData.map(d => d.total_tokens || 0), 1);

    let html = `
        <div class="stats-daily">
            <div class="stats-section">
                <h4>📅 每日Token使用趋势</h4>
                <div class="stats-chart">
                    ${chartData.map(d => {
                        const height = maxTokens > 0 ? (d.total_tokens / maxTokens * 200) : 0;
                        return `
                            <div class="chart-bar-wrapper" title="${d.date}: ${formatNumber(d.total_tokens)} tokens">
                                <div class="chart-bar" style="height: ${height}px;">
                                    <span class="chart-value">${formatNumber(d.total_tokens)}</span>
                                </div>
                                <span class="chart-label">${d.date.slice(5)}</span>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>

            <div class="stats-section">
                <h4>📋 每日详细数据</h4>
                <table class="stats-table">
                    <thead>
                        <tr>
                            <th>日期</th>
                            <th>Prompt Tokens</th>
                            <th>Completion Tokens</th>
                            <th>总 Tokens</th>
                            <th>调用次数</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${daily.map(d => `
                            <tr>
                                <td>${d.date}</td>
                                <td>${formatNumber(d.prompt_tokens)}</td>
                                <td>${formatNumber(d.completion_tokens)}</td>
                                <td><strong>${formatNumber(d.total_tokens)}</strong></td>
                                <td>${formatNumber(d.call_count)}</td>
                                <td>
                                    <button class="btn" style="width:auto;padding:2px 8px;font-size:12px;"
                                        onclick="window.viewDateDetail('${d.date}')">查看明细</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;

    return html;
}

function renderModels() {
    const models = currentStatsData.models || [];

    if (models.length === 0) {
        return '<p class="stats-empty">暂无模型统计数据</p>';
    }

    const maxTokens = Math.max(...models.map(m => m.total_tokens || 0), 1);

    let html = `
        <div class="stats-models">
            <div class="stats-section">
                <h4>🤖 模型使用占比</h4>
                <div class="stats-model-bars">
                    ${models.map(m => {
                        const pct = maxTokens > 0 ? ((m.total_tokens / maxTokens) * 100).toFixed(1) : 0;
                        return `
                            <div class="model-bar-item">
                                <div class="model-bar-info">
                                    <span class="model-bar-name">${m.model_name}</span>
                                    <span class="model-bar-provider">${m.provider}</span>
                                </div>
                                <div class="model-bar-track">
                                    <div class="model-bar-fill" style="width: ${pct}%;"></div>
                                </div>
                                <div class="model-bar-stats">
                                    <span>${formatNumber(m.total_tokens)} tokens</span>
                                    <span>${m.call_count} 次调用</span>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>

            <div class="stats-section">
                <h4>📋 模型详细数据</h4>
                <table class="stats-table">
                    <thead>
                        <tr>
                            <th>模型</th>
                            <th>提供商</th>
                            <th>Prompt Tokens</th>
                            <th>Completion Tokens</th>
                            <th>总 Tokens</th>
                            <th>调用次数</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${models.map(m => `
                            <tr>
                                <td>${m.model_name}</td>
                                <td>${m.provider}</td>
                                <td>${formatNumber(m.prompt_tokens)}</td>
                                <td>${formatNumber(m.completion_tokens)}</td>
                                <td><strong>${formatNumber(m.total_tokens)}</strong></td>
                                <td>${formatNumber(m.call_count)}</td>
                                <td>
                                    <button class="btn" style="width:auto;padding:2px 8px;font-size:12px;"
                                        onclick="window.viewModelDetail('${m.model_name}')">查看趋势</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;

    return html;
}

function renderDetail() {
    const dailyModel = currentStatsData.daily_model || [];

    if (dailyModel.length === 0) {
        return '<p class="stats-empty">暂无交叉明细数据</p>';
    }

    const grouped = {};
    dailyModel.forEach(item => {
        if (!grouped[item.date]) {
            grouped[item.date] = [];
        }
        grouped[item.date].push(item);
    });

    const dates = Object.keys(grouped).sort().reverse();

    let html = `
        <div class="stats-detail-view">
            <div class="stats-section">
                <h4>🔍 每日-模型交叉明细</h4>
    `;

    dates.forEach(date => {
        const items = grouped[date];
        const dateTotal = items.reduce((sum, i) => sum + (i.total_tokens || 0), 0);

        html += `
            <div class="detail-date-group">
                <div class="detail-date-header">
                    <span class="detail-date-title">📅 ${date}</span>
                    <span class="detail-date-total">合计: ${formatNumber(dateTotal)} tokens</span>
                </div>
                <table class="stats-table">
                    <thead>
                        <tr>
                            <th>模型</th>
                            <th>提供商</th>
                            <th>Prompt</th>
                            <th>Completion</th>
                            <th>总 Tokens</th>
                            <th>调用次数</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${items.map(item => `
                            <tr>
                                <td>${item.model_name}</td>
                                <td>${item.provider}</td>
                                <td>${formatNumber(item.prompt_tokens)}</td>
                                <td>${formatNumber(item.completion_tokens)}</td>
                                <td><strong>${formatNumber(item.total_tokens)}</strong></td>
                                <td>${formatNumber(item.call_count)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    });

    html += '</div></div>';
    return html;
}

function renderRecent() {
    const recent = currentStatsData.recent || [];

    if (recent.length === 0) {
        return '<p class="stats-empty">暂无最近记录</p>';
    }

    let html = `
        <div class="stats-recent">
            <div class="stats-section">
                <h4>📝 最近使用记录</h4>
                <table class="stats-table">
                    <thead>
                        <tr>
                            <th>时间</th>
                            <th>模型</th>
                            <th>提供商</th>
                            <th>Prompt</th>
                            <th>Completion</th>
                            <th>总 Tokens</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${recent.map(r => `
                            <tr>
                                <td>${formatTimestamp(r.timestamp)}</td>
                                <td>${r.model_name}</td>
                                <td>${r.provider}</td>
                                <td>${formatNumber(r.prompt_tokens)}</td>
                                <td>${formatNumber(r.completion_tokens)}</td>
                                <td><strong>${formatNumber(r.total_tokens)}</strong></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;

    return html;
}

function formatNumber(num) {
    if (num === undefined || num === null) return '0';
    return num.toLocaleString('zh-CN');
}

function formatTimestamp(ts) {
    if (!ts) return '-';
    try {
        const date = new Date(ts);
        return date.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return ts;
    }
}

window.handleStatsDaysChange = async function(value) {
    selectedDays = parseInt(value);
    await fetchStats();
    await loadDateFilter();
};

window.handleStatsModelChange = async function(value) {
    selectedModel = value;
    await fetchStats();
};

window.handleStatsDateChange = async function(value) {
    selectedDate = value;
    await fetchStats();
};

window.refreshStats = async function() {
    await fetchStats();
    await loadModelFilter();
    await loadDateFilter();
};

window.switchStatsTab = function(tab) {
    currentView = tab;

    document.querySelectorAll('.stats-tab').forEach(el => {
        el.classList.remove('active');
    });
    event.target.classList.add('active');

    renderStats();
};

window.viewDateDetail = async function(date) {
    selectedDate = date;
    const dateSelect = document.getElementById('stats-date');
    if (dateSelect) dateSelect.value = date;
    await fetchStats();

    currentView = 'overview';
    document.querySelectorAll('.stats-tab').forEach(el => el.classList.remove('active'));
    const overviewTab = document.querySelector('.stats-tab:nth-child(1)');
    if (overviewTab) overviewTab.classList.add('active');
    renderStats();
};

window.viewModelDetail = async function(model) {
    selectedModel = model;
    const modelSelect = document.getElementById('stats-model');
    if (modelSelect) modelSelect.value = model;
    await fetchStats();

    currentView = 'overview';
    document.querySelectorAll('.stats-tab').forEach(el => el.classList.remove('active'));
    const overviewTab = document.querySelector('.stats-tab:nth-child(1)');
    if (overviewTab) overviewTab.classList.add('active');
    renderStats();
};
