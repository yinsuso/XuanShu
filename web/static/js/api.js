import { STATE } from './state.js';

export async function api(endpoint, options = {}) {
    const url = `${STATE.apiBase}${endpoint}`;
    const config = {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        ...options
    };
    if (options.body && !options.method) {
        config.method = 'POST';
    }
    if (STATE.clusterToken && !config.headers['X-Cluster-Token']) {
        config.headers['X-Cluster-Token'] = STATE.clusterToken;
    }
    if (options.headers) {
        config.headers = { ...config.headers, ...options.headers };
    }
    const res = await fetch(url, config);
    if (!res.ok) {
        console.error(`API Error ${res.status}: ${url}`);
        try {
            const errData = await res.json();
            return { success: false, error: errData.detail || `HTTP ${res.status}` };
        } catch {
            return { success: false, error: `HTTP ${res.status}` };
        }
    }
    return await res.json();
}

export async function loadRoomModels(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const defaultModels = [
        { name: 'qwen3.5:9b', desc: 'qwen3.5:9b (代码专精)' },
        { name: 'qwen2.5:7b', desc: 'qwen2.5:7b (通用)' },
        { name: 'llama3:8b', desc: 'llama3:8b' },
        { name: 'phi3:3.8b', desc: 'phi3:3.8b (轻量)' }
    ];

    const models = [];

    try {
        const allRes = await api('/api/all_models');
        if (allRes.success && allRes.models.length > 0) {
            allRes.models.forEach(m => {
                const suffix = m.model === allRes.current_model ? ' (当前)' : '';
                const typeLabel = m.provider === 'ollama' ? ' (本地)' : ' (云端)';
                models.push({ name: m.model, desc: `${m.model}${suffix}${typeLabel}` });
            });
        }
    } catch (e) {
        console.log('获取配置模型失败', e);
    }

    if (models.length === 0) {
        models.push(...defaultModels.map(m => ({ name: m.name, desc: m.desc, type: 'default' })));
    }

    select.innerHTML = models.map(m =>
        `<option value="${m.name}">${m.desc}</option>`
    ).join('');

    try {
        const allRes = await api('/api/all_models');
        if (allRes.success && allRes.current_model) {
            select.value = allRes.current_model;
        }
    } catch (e) {}
}
