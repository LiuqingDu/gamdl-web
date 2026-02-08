/**
 * Apple Music 下载器前端逻辑
 */

// DOM元素引用
const elements = {
    urlInput: document.getElementById('url-input'),
    languageSelect: document.getElementById('language-select'),
    downloadBtn: document.getElementById('download-btn'),
    refreshBtn: document.getElementById('refresh-btn'),
    resetAllBtn: document.getElementById('reset-all-btn'),
    settingsBtn: document.getElementById('settings-btn'),
    logSection: document.getElementById('log-section'),
    logContent: document.getElementById('log-content'),
    taskList: document.getElementById('task-list'),
    settingsModal: document.getElementById('settings-modal'),
    closeModalBtn: document.getElementById('close-modal-btn'),
    cookiesInput: document.getElementById('cookies-input'),
    cookiesStatus: document.getElementById('cookies-status'),
    configInput: document.getElementById('config-input'),
    configStatus: document.getElementById('config-status'),
    saveSettingsBtn: document.getElementById('save-settings-btn'),
    cancelSettingsBtn: document.getElementById('cancel-settings-btn'),
};

// 状态图标映射
const statusIcons = {
    0: '○',   // 等待中
    1: '●',   // 下载中
    2: '✓',   // 完成
    '-1': '✗', // 错误
    '-2': '◌', // 已取消
};

// 状态CSS类映射
const statusClasses = {
    0: 'pending',
    1: 'downloading',
    2: 'completed',
    '-1': 'error',
    '-2': 'cancelled',
};

/**
 * 刷新任务列表
 */
async function refreshTasks() {
    try {
        const response = await fetch('/api/tasks');
        const data = await response.json();

        // 更新日志
        if (data.current_log) {
            elements.logContent.textContent = data.current_log;
            elements.logSection.classList.add('visible');
        } else {
            elements.logSection.classList.remove('visible');
        }

        // 排序任务
        const tasks = data.tasks.sort((a, b) => {
            const statusOrder = [1, 0, 2, -1, -2]; // 下载中 > 等待中 > 完成 > 错误 > 已取消
            return statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status);
        });

        // 渲染任务列表
        renderTaskList(tasks);

    } catch (error) {
        console.error('刷新任务失败:', error);
    }
}

/**
 * 渲染任务列表
 */
function renderTaskList(tasks) {
    if (tasks.length === 0) {
        elements.taskList.innerHTML = '<div class="empty-state">暂无任务</div>';
        return;
    }

    elements.taskList.innerHTML = tasks.map(task => `
        <div class="task-item" data-id="${task.id}">
            <span class="task-status-icon">${statusIcons[task.status] || '?'}</span>
            <div class="task-info">
                <span class="task-name" title="${task.name}">${task.name}</span>
                <span class="task-type">${task.type}</span>
                <span class="task-id">${task.id}</span>
                <div class="task-language">
                    <select class="select" onchange="updateLanguage('${task.id}', this.value)">
                        <option value="zh-CN" ${task.language === 'zh-CN' ? 'selected' : ''}>中文</option>
                        <option value="en-US" ${task.language === 'en-US' ? 'selected' : ''}>English</option>
                    </select>
                </div>
            </div>
            <span class="task-status ${statusClasses[task.status] || ''}">${task.status_text}</span>
            <div class="task-actions">
                ${getTaskActions(task)}
            </div>
        </div>
    `).join('');
}

/**
 * 获取任务操作按钮
 */
function getTaskActions(task) {
    const actions = [];

    // 商店链接（所有任务都显示）
    actions.push(`
        <button class="btn btn-secondary btn-small" onclick="openStore('${task.url}')" title="在商店中打开">
            商店
        </button>
    `);

    // 根据状态显示不同操作
    if (task.status === 0) {
        // 等待中：可以取消
        actions.push(`
            <button class="btn btn-warning btn-small" onclick="cancelTask('${task.id}')">
                取消
            </button>
        `);
    } else if (task.status === 2 || task.status === -1 || task.status === -2) {
        // 完成/错误/已取消：可以重启、覆盖重启和删除
        actions.push(`
            <button class="btn btn-success btn-small" onclick="restartTask('${task.id}')">
                重启
            </button>
        `);
        actions.push(`
            <button class="btn btn-warning btn-small" onclick="restartTaskWithOverwrite('${task.id}')" title="覆盖已有文件重新下载">
                覆盖
            </button>
        `);
        actions.push(`
            <button class="btn btn-danger btn-small" onclick="deleteTask('${task.id}')">
                删除
            </button>
        `);
    }

    return actions.join('');
}

/**
 * 创建下载任务
 */
async function createTask() {
    const url = elements.urlInput.value.trim();
    const language = elements.languageSelect.value;

    if (!url) {
        alert('请输入 Apple Music 链接');
        return;
    }

    try {
        const response = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, language })
        });

        const data = await response.json();

        if (!response.ok) {
            alert('添加失败: ' + (data.detail || data.error || '未知错误'));
            return;
        }

        elements.urlInput.value = '';
        refreshTasks();

    } catch (error) {
        alert('添加失败: ' + error.message);
    }
}

/**
 * 取消任务
 */
async function cancelTask(taskId) {
    try {
        const response = await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
        const data = await response.json();

        if (!response.ok) {
            alert('取消失败: ' + (data.detail || data.error));
            return;
        }

        refreshTasks();

    } catch (error) {
        alert('取消失败: ' + error.message);
    }
}

/**
 * 重启任务
 */
async function restartTask(taskId) {
    try {
        const response = await fetch(`/api/tasks/${taskId}/restart`, { method: 'POST' });
        const data = await response.json();

        if (!response.ok) {
            alert('重启失败: ' + (data.detail || data.error));
            return;
        }

        refreshTasks();

    } catch (error) {
        alert('重启失败: ' + error.message);
    }
}

/**
 * 覆盖重启任务（会覆盖已有文件）
 */
async function restartTaskWithOverwrite(taskId) {
    if (!confirm('确定要覆盖已有文件重新下载吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/tasks/${taskId}/restart-overwrite`, { method: 'POST' });
        const data = await response.json();

        if (!response.ok) {
            alert('覆盖重启失败: ' + (data.detail || data.error));
            return;
        }

        refreshTasks();

    } catch (error) {
        alert('覆盖重启失败: ' + error.message);
    }
}

/**
 * 删除任务
 */
async function deleteTask(taskId) {
    if (!confirm('确定要删除这个任务吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
        const data = await response.json();

        if (!response.ok) {
            alert('删除失败: ' + (data.detail || data.error));
            return;
        }

        refreshTasks();

    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

/**
 * 更新任务语言
 */
async function updateLanguage(taskId, language) {
    try {
        const response = await fetch(`/api/tasks/${taskId}/language`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language })
        });

        const data = await response.json();

        if (!response.ok) {
            alert('更新语言失败: ' + (data.detail || data.error));
            refreshTasks();
            return;
        }

    } catch (error) {
        alert('更新语言失败: ' + error.message);
        refreshTasks();
    }
}

/**
 * 重置所有任务
 */
async function resetAllTasks() {
    if (!confirm('确定要重新下载所有任务吗？')) {
        return;
    }

    if (!confirm('这将把所有非运行中的任务重置为等待状态，确定继续？')) {
        return;
    }

    try {
        const response = await fetch('/api/tasks/reset-all', { method: 'POST' });
        const data = await response.json();

        if (!response.ok) {
            alert('重置失败: ' + (data.detail || data.error));
            return;
        }

        alert(data.message);
        refreshTasks();

    } catch (error) {
        alert('重置失败: ' + error.message);
    }
}

/**
 * 在商店中打开
 */
function openStore(url) {
    window.open(url, '_blank');
}

/**
 * 打开设置弹窗
 */
async function openSettings() {
    elements.settingsModal.classList.add('visible');

    // 加载cookies状态
    try {
        const cookiesStatusResponse = await fetch('/api/settings/cookies');
        const cookiesStatusData = await cookiesStatusResponse.json();

        if (cookiesStatusData.configured) {
            elements.cookiesStatus.textContent = '状态: ✓ 已配置';
            elements.cookiesStatus.className = 'cookies-status configured';
        } else {
            elements.cookiesStatus.textContent = '状态: ⚠️ 未配置';
            elements.cookiesStatus.className = 'cookies-status not-configured';
        }

        // 加载cookies内容
        const cookiesContentResponse = await fetch('/api/settings/cookies/content');
        const cookiesContentData = await cookiesContentResponse.json();
        elements.cookiesInput.value = cookiesContentData.content || '';

    } catch (error) {
        console.error('加载Cookies设置失败:', error);
    }

    // 加载config.ini状态
    try {
        const configStatusResponse = await fetch('/api/settings/config');
        const configStatusData = await configStatusResponse.json();

        if (configStatusData.configured) {
            elements.configStatus.textContent = '状态: ✓ 已配置';
            elements.configStatus.className = 'cookies-status configured';
        } else {
            elements.configStatus.textContent = '状态: ⚠️ 未配置';
            elements.configStatus.className = 'cookies-status not-configured';
        }

        // 加载config.ini内容
        const configContentResponse = await fetch('/api/settings/config/content');
        const configContentData = await configContentResponse.json();
        elements.configInput.value = configContentData.content || '';

    } catch (error) {
        console.error('加载config.ini设置失败:', error);
    }
}

/**
 * 关闭设置弹窗
 */
function closeSettings() {
    elements.settingsModal.classList.remove('visible');
}

/**
 * 保存所有设置
 */
async function saveSettings() {
    const cookiesContent = elements.cookiesInput.value;
    const configContent = elements.configInput.value;
    let success = true;
    let messages = [];

    // 保存Cookies
    try {
        const cookiesResponse = await fetch('/api/settings/cookies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: cookiesContent })
        });

        if (!cookiesResponse.ok) {
            const data = await cookiesResponse.json();
            messages.push('Cookies保存失败: ' + (data.detail || data.error));
            success = false;
        }
    } catch (error) {
        messages.push('Cookies保存失败: ' + error.message);
        success = false;
    }

    // 保存Config
    try {
        const configResponse = await fetch('/api/settings/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: configContent })
        });

        if (!configResponse.ok) {
            const data = await configResponse.json();
            messages.push('配置保存失败: ' + (data.detail || data.error));
            success = false;
        }
    } catch (error) {
        messages.push('配置保存失败: ' + error.message);
        success = false;
    }

    if (success) {
        alert('设置已保存');
        closeSettings();
    } else {
        alert(messages.join('\n'));
    }
}

// 事件绑定
elements.downloadBtn.addEventListener('click', createTask);
elements.refreshBtn.addEventListener('click', refreshTasks);
elements.resetAllBtn.addEventListener('click', resetAllTasks);
elements.settingsBtn.addEventListener('click', openSettings);
elements.closeModalBtn.addEventListener('click', closeSettings);
elements.cancelSettingsBtn.addEventListener('click', closeSettings);
elements.saveSettingsBtn.addEventListener('click', saveSettings);

// 回车键提交
elements.urlInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        createTask();
    }
});

// 粘贴时自动解码URL中的中文
elements.urlInput.addEventListener('paste', (e) => {
    // 延迟执行，等待粘贴内容写入
    setTimeout(() => {
        try {
            elements.urlInput.value = decodeURIComponent(elements.urlInput.value);
        } catch (err) {
            // 如果解码失败（可能已经是解码后的），保持原样
        }
    }, 0);
});

// 输入时也尝试解码（处理手动输入编码URL的情况）
elements.urlInput.addEventListener('blur', () => {
    try {
        const decoded = decodeURIComponent(elements.urlInput.value);
        if (decoded !== elements.urlInput.value) {
            elements.urlInput.value = decoded;
        }
    } catch (err) {
        // 解码失败，保持原样
    }
});

// 点击弹窗外部关闭
elements.settingsModal.addEventListener('click', (e) => {
    if (e.target === elements.settingsModal) {
        closeSettings();
    }
});

// 页面加载时刷新任务
refreshTasks();

// 每5秒自动刷新
setInterval(refreshTasks, 5000);
