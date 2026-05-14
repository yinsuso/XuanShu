import { STATE } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../utils.js';

export async function loadModelList(forceReload = false) {
    const container = document.getElementById('model-list');
    try {
        const url = forceReload ? '/api/models?force_reload=true' : '/api/models';
        const res = await api(url);
        if (res.success) {
            container.innerHTML = res.models.map(m => `
                <div class="room-card" onclick="window.selectModel('${m.name}')">
                    <h4>${m.name} ${m.is_current ? '✓' : ''}</h4>
                    <p>提供商: ${m.provider}</p>
                    <p>模型: ${m.model_name}</p>
                    <p>API: ${m.api_base}</p>
                    <button class="btn" style="font-size:12px;padding:2px 8px;margin-right:4px;" onclick="event.stopPropagation();window.editModel('${m.name}')">编辑</button>
                    <button class="btn btn-danger" style="font-size:12px;padding:2px 8px;" onclick="event.stopPropagation();window.deleteModel('${m.name}')">删除</button>
                </div>
            `).join('');
            updateCurrentModel(res.current_config);
        } else {
            container.innerHTML = '<p>加载模型列表失败</p>';
        }
    } catch (e) {
        console.error('加载模型列表失败', e);
        container.innerHTML = '<p>加载模型列表失败</p>';
    }
}

export async function selectModel(name) {
    try {
        const res = await api('/api/switch_model', {
            method: 'POST',
            body: JSON.stringify({ name })
        });
        if (res.success) {
            showToast('已切换到: ' + name);
            updateCurrentModel(name);
            await loadModelList();
        } else {
            showToast(res.error || '切换失败', true);
        }
    } catch (e) {
        showToast('切换模型失败', true);
    }
}

export async function editModel(name) {
    try {
        const res = await api('/api/models?force_reload=true');
        if (res.success) {
            const model = res.models.find(m => m.name === name);
            if (model) {
                document.getElementById('model-original-name').value = model.name;
                document.getElementById('model-name').value = model.name;
                document.getElementById('model-provider').value = model.provider;
                document.getElementById('model-model-name').value = model.model_name;
                document.getElementById('model-api-base').value = model.api_base;
                showToast('已加载模型配置到表单');
            }
        }
    } catch (e) {
        showToast('加载模型配置失败', true);
    }
}

export async function deleteModel(name) {
    if (!confirm(`确定删除模型配置: ${name}?`)) return;
    try {
        const res = await api('/api/delete_model', {
            method: 'POST',
            body: JSON.stringify({ name })
        });
        if (res.success) {
            showToast('已删除');
            await loadModelList();
        } else {
            showToast(res.error || '删除失败', true);
        }
    } catch (e) {
        showToast('删除失败', true);
    }
}

export async function saveModel() {
    const name = document.getElementById('model-name').value.trim();
    const originalName = document.getElementById('model-original-name').value.trim();
    const provider = document.getElementById('model-provider').value;
    const modelName = document.getElementById('model-model-name').value.trim();
    const apiBase = document.getElementById('model-api-base').value.trim();
    const apiKey = document.getElementById('model-api-key').value;

    if (!name || !provider || !modelName || !apiBase) {
        showToast('请填写必填字段', true);
        return;
    }

    const formData = new FormData();
    formData.append('name', name);
    formData.append('original_name', originalName);
    formData.append('provider', provider);
    formData.append('model_name', modelName);
    formData.append('api_base', apiBase);
    formData.append('api_key', apiKey);

    try {
        const res = await fetch(`${STATE.apiBase}/api/save_model`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            showToast('保存成功');
            document.getElementById('model-name').value = '';
            document.getElementById('model-original-name').value = '';
            document.getElementById('model-model-name').value = '';
            document.getElementById('model-api-base').value = '';
            document.getElementById('model-api-key').value = '';
            await loadModelList();
        } else {
            showToast(data.error || '保存失败', true);
        }
    } catch (e) {
        showToast('保存失败', true);
    }
}

export function updateCurrentModel(modelName) {
    document.getElementById('current-model').textContent = modelName || '未选择';
}
