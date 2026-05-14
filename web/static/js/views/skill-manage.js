import { api } from '../api.js';
import { showToast } from '../utils.js';

let currentSkills = [];
let currentSkillName = '';

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export async function loadSkillList() {
    const container = document.getElementById('skill-list');
    if (!container) return;

    container.innerHTML = '<p>正在加载技能列表...</p>';

    try {
        const res = await api('/api/skills');
        if (res.success) {
            currentSkills = res.skills || [];
            renderSkillList(currentSkills);
        } else {
            container.innerHTML = '<p>加载技能列表失败：' + escapeHtml(res.error || '未知错误') + '</p>';
        }
    } catch (e) {
        console.error('加载技能列表失败', e);
        container.innerHTML = '<p>加载技能列表失败</p>';
    }
}

function renderSkillList(skills) {
    const container = document.getElementById('skill-list');
    if (!container) return;

    if (skills.length === 0) {
        container.innerHTML = '<p>暂无技能</p>';
        return;
    }

    container.innerHTML = skills.map(s => {
        const name = escapeHtml(s.name);
        const desc = escapeHtml(s.description || '暂无描述');
        return `
        <div class="skill-card" style="border:1px solid #ddd;border-radius:8px;padding:12px;margin-bottom:8px;background:#f8f9fa;cursor:pointer;transition:all 0.2s;" onmouseover="this.style.background='#e8f4fd'" onmouseout="this.style.background='#f8f9fa'" onclick="window.showSkillDetail('${name}')">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div style="flex:1;min-width:0;margin-right:8px;">
                    <h4 style="margin:0 0 4px 0;color:#007bff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</h4>
                    <p style="margin:0;font-size:13px;color:#666;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${desc}</p>
                </div>
                <div style="display:flex;gap:4px;flex-shrink:0;">
                    <button class="btn" style="font-size:12px;padding:2px 8px;width:auto;" onclick="event.stopPropagation();window.showSkillDetail('${name}')">查看</button>
                    <button class="btn btn-danger" style="font-size:12px;padding:2px 8px;width:auto;" onclick="event.stopPropagation();window.deleteSkill('${name}')">删除</button>
                </div>
            </div>
        </div>
    `;
    }).join('');
}

export function filterSkills() {
    const queryEl = document.getElementById('skill-search');
    if (!queryEl) return;

    const query = queryEl.value.trim().toLowerCase();
    if (!query) {
        renderSkillList(currentSkills);
        return;
    }

    const filtered = currentSkills.filter(s =>
        s.name.toLowerCase().includes(query) ||
        (s.description && s.description.toLowerCase().includes(query))
    );
    renderSkillList(filtered);
}

export async function showSkillDetail(skillName) {
    currentSkillName = skillName;
    const modal = document.getElementById('skill-detail-modal');
    const nameEl = document.getElementById('detail-skill-name');
    const contentEl = document.getElementById('detail-skill-content');

    if (!modal || !nameEl || !contentEl) return;

    nameEl.textContent = skillName;
    contentEl.innerHTML = '<p>正在加载详情...</p>';
    modal.classList.remove('hidden');

    try {
        const res = await api(`/api/skills/detail/${encodeURIComponent(skillName)}`);
        if (res.success && res.skill) {
            const s = res.skill;
            const paramsHtml = s.parameters && s.parameters.length > 0
                ? `<ul style="margin:4px 0;padding-left:20px;">${s.parameters.map(p => {
                    const pName = escapeHtml(p.name || '');
                    const pType = escapeHtml(p.type || 'string');
                    const pDesc = escapeHtml(p.description || '');
                    const requiredMark = p.required !== false ? ' <span style="color:#dc3545;">*</span>' : '';
                    const defaultVal = p.default !== undefined ? ` (默认: ${escapeHtml(String(p.default))})` : '';
                    return `<li><code>${pName}</code> (${pType})${requiredMark} - ${pDesc}${defaultVal}</li>`;
                }).join('')}</ul>`
                : '<p style="color:#999;">无参数</p>';

            contentEl.innerHTML = `
                <div style="margin-bottom:12px;">
                    <strong style="color:#333;">名称：</strong>
                    <span>${escapeHtml(s.name)}</span>
                </div>
                <div style="margin-bottom:12px;">
                    <strong style="color:#333;">描述：</strong>
                    <span>${escapeHtml(s.description) || '暂无描述'}</span>
                </div>
                <div style="margin-bottom:12px;">
                    <strong style="color:#333;">分类：</strong>
                    <span style="background:#e8f4fd;padding:2px 8px;border-radius:4px;font-size:12px;">${escapeHtml(s.category) || '未分类'}</span>
                </div>
                <div style="margin-bottom:12px;">
                    <strong style="color:#333;">触发条件：</strong>
                    <span>${escapeHtml(s.trigger) || '暂无'}</span>
                </div>
                <div style="margin-bottom:12px;">
                    <strong style="color:#333;">需要确认：</strong>
                    <span>${s.requires_confirmation ? '✅ 是' : '❌ 否'}</span>
                </div>
                <div style="margin-bottom:12px;">
                    <strong style="color:#333;">参数列表：</strong>
                    ${paramsHtml}
                </div>
                <div style="margin-bottom:12px;">
                    <strong style="color:#333;">文件路径：</strong>
                    <code style="background:#f4f4f4;padding:2px 6px;border-radius:3px;font-size:12px;word-break:break-all;">${escapeHtml(s.file_path) || '未知'}</code>
                </div>
            `;
        } else {
            contentEl.innerHTML = `<p style="color:#dc3545;">加载详情失败：${escapeHtml(res.error || '未知错误')}</p>`;
        }
    } catch (e) {
        console.error('加载技能详情失败', e);
        contentEl.innerHTML = '<p style="color:#dc3545;">加载详情失败</p>';
    }
}

export function closeSkillDetail() {
    const modal = document.getElementById('skill-detail-modal');
    if (modal) modal.classList.add('hidden');
    currentSkillName = '';
}

export async function deleteSkill(skillName) {
    if (!skillName) return;
    if (!confirm(`确定删除技能: ${skillName}?\n\n⚠️ 警告：此操作将永久删除技能文件，不可恢复！`)) return;

    try {
        const res = await api('/api/skills/delete', {
            method: 'POST',
            body: JSON.stringify({ skill_name: skillName })
        });
        if (res.success) {
            showToast('已删除: ' + skillName);
            // 从本地缓存中移除
            currentSkills = currentSkills.filter(s => s.name !== skillName);
            renderSkillList(currentSkills);
            closeSkillDetail();
        } else {
            showToast(res.error || '删除失败', true);
        }
    } catch (e) {
        console.error('删除技能失败', e);
        showToast('删除失败', true);
    }
}

export async function deleteCurrentSkill() {
    if (currentSkillName) {
        await deleteSkill(currentSkillName);
    }
}
