/**
 * IP Camera Viewer - Professional Layout
 * Tree list + 5-slot video layout (1 main + 4 sub)
 */

class CameraViewer {
    constructor() {
        this.cameras = [];
        this.slotAssignments = {
            main: null,
            sub1: null,
            sub2: null,
            sub3: null,
            sub4: null
        };
        this.sortBy = 'ip'; // 'ip' or 'name'
        this.scanPollInterval = null;
        this.draggedCamera = null;
        this.contextMenuCamera = null;
        this.assigningToSlot = null; // Track which slot is being assigned

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadCameras();
        this.startStatusUpdates();
    }

    // ==================== Event Binding ====================

    bindEvents() {
        // Header buttons
        document.getElementById('scanBtn')?.addEventListener('click', () => this.startScan());
        document.getElementById('addCameraBtn')?.addEventListener('click', () => this.showAddCameraModal());
        document.getElementById('refreshBtn')?.addEventListener('click', () => this.refreshCameras());

        // Sort buttons
        document.getElementById('sortByIp')?.addEventListener('click', () => this.setSort('ip'));
        document.getElementById('sortByName')?.addEventListener('click', () => this.setSort('name'));

        // Modal close buttons
        document.querySelectorAll('.modal-close, .modal-cancel').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.closeModal(e.target.closest('.modal-overlay'));
            });
        });

        // Add camera form
        document.getElementById('saveCameraBtn')?.addEventListener('click', () => this.addCameraManual());
        document.getElementById('addCameraForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.addCameraManual();
        });

        // Add all button in scan modal
        document.getElementById('addAllBtn')?.addEventListener('click', () => this.addAllCameras());

        // Clear slot buttons
        document.querySelectorAll('.clear-slot-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const slot = e.target.dataset.slot;
                this.clearSlot(slot);
            });
        });

        // Maximize buttons
        document.querySelectorAll('.maximize-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const slot = e.target.closest('.maximize-btn').dataset.slot;
                this.toggleFullscreen(slot);
            });
        });

        // Assign buttons
        document.querySelectorAll('.assign-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const slot = e.target.closest('.assign-btn').dataset.slot;
                this.showAssignCameraModal(slot);
            });
        });

        // Screenshot buttons
        document.querySelectorAll('.screenshot-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const slot = e.target.closest('.screenshot-btn').dataset.slot;
                this.takeScreenshot(slot);
            });
        });

        // Drag & Drop for video slots
        this.setupDragAndDrop();

        // Context menu
        this.setupContextMenu();

        // Hide context menu on click outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.context-menu')) {
                this.hideContextMenu();
            }
        });

        // ESC key to exit fullscreen
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.exitFullscreen();
            }
        });
    }

    // ==================== Drag & Drop ====================

    setupDragAndDrop() {
        // Video slots as drop targets
        const slots = ['main', 'sub1', 'sub2', 'sub3', 'sub4'];
        slots.forEach(slotId => {
            const slot = document.getElementById(`slot-${slotId}`);
            if (!slot) return;

            slot.addEventListener('dragover', (e) => {
                e.preventDefault();
                slot.classList.add('drag-over');
            });

            slot.addEventListener('dragleave', () => {
                slot.classList.remove('drag-over');
            });

            slot.addEventListener('drop', (e) => {
                e.preventDefault();
                slot.classList.remove('drag-over');
                if (this.draggedCamera) {
                    this.assignCameraToSlot(this.draggedCamera, slotId);
                }
            });
        });
    }

    setupTreeItemDrag(item, camera) {
        item.setAttribute('draggable', 'true');
        item.addEventListener('dragstart', (e) => {
            this.draggedCamera = camera;
            item.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'copy';
        });
        item.addEventListener('dragend', () => {
            item.classList.remove('dragging');
            this.draggedCamera = null;
        });
        item.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.showContextMenu(e, camera);
        });
    }

    // ==================== Context Menu ====================

    setupContextMenu() {
        const menu = document.getElementById('contextMenu');
        menu.querySelectorAll('.context-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const action = e.target.dataset.action;
                this.handleContextAction(action);
                this.hideContextMenu();
            });
        });
    }

    showContextMenu(e, camera) {
        this.contextMenuCamera = camera;
        const menu = document.getElementById('contextMenu');
        menu.style.left = `${e.pageX}px`;
        menu.style.top = `${e.pageY}px`;
        menu.classList.add('active');
    }

    hideContextMenu() {
        document.getElementById('contextMenu')?.classList.remove('active');
    }

    handleContextAction(action) {
        if (!this.contextMenuCamera) return;

        const slotMap = {
            'assign-main': 'main',
            'assign-sub1': 'sub1',
            'assign-sub2': 'sub2',
            'assign-sub3': 'sub3',
            'assign-sub4': 'sub4',
        };

        if (slotMap[action]) {
            this.assignCameraToSlot(this.contextMenuCamera, slotMap[action]);
        } else if (action === 'remove') {
            this.removeCamera(this.contextMenuCamera.id);
        }
    }

    // ==================== Slot Management ====================

    assignCameraToSlot(camera, slotId) {
        this.slotAssignments[slotId] = camera.id;
        this.updateSlotDisplay(slotId, camera);
        this.showToast(`${camera.name} 已分配到 ${this.getSlotName(slotId)}`, 'success');
    }

    clearSlot(slotId) {
        this.slotAssignments[slotId] = null;
        this.updateSlotDisplay(slotId, null);
    }

    updateSlotDisplay(slotId, camera) {
        const slot = document.getElementById(`slot-${slotId}`);
        const nameEl = document.getElementById(`slot-${slotId}-name`);
        const img = document.getElementById(`stream-${slotId}`);
        const placeholder = document.getElementById(`placeholder-${slotId}`);
        const statusEl = document.getElementById(`status-${slotId}`);
        const statusDot = statusEl?.querySelector('.status-dot');
        const statusText = statusEl?.querySelector('.status-text');

        if (camera) {
            // Has camera
            slot?.classList.add('has-camera');
            if (nameEl) nameEl.textContent = camera.name;
            if (img) {
                img.src = `/api/stream/${camera.id}`;
                img.classList.add('active');
            }
            if (placeholder) placeholder.style.display = 'none';
            if (statusText) statusText.textContent = '连接中...';
            if (statusDot) statusDot.className = 'status-dot connecting';

            // Handle stream load
            if (img) {
                img.onload = () => {
                    if (statusText) statusText.textContent = '在线';
                    if (statusDot) statusDot.className = 'status-dot online';
                };
                img.onerror = () => {
                    if (statusText) statusText.textContent = '连接失败';
                    if (statusDot) statusDot.className = 'status-dot';
                };
            }
        } else {
            // Empty slot
            slot?.classList.remove('has-camera');
            if (nameEl) nameEl.textContent = '未分配';
            if (img) {
                img.src = '';
                img.classList.remove('active');
            }
            if (placeholder) placeholder.style.display = 'block';
            if (statusText) statusText.textContent = '离线';
            if (statusDot) statusDot.className = 'status-dot';
        }
    }

    getSlotName(slotId) {
        const names = {
            main: '主窗口',
            sub1: '窗口 1',
            sub2: '窗口 2',
            sub3: '窗口 3',
            sub4: '窗口 4',
        };
        return names[slotId] || slotId;
    }

    // ==================== Fullscreen ====================

    toggleFullscreen(slotId) {
        const slot = document.getElementById(`slot-${slotId}`);
        if (!slot) return;

        if (slot.classList.contains('fullscreen')) {
            this.exitFullscreen();
        } else {
            this.enterFullscreen(slotId);
        }
    }

    enterFullscreen(slotId) {
        // Exit any existing fullscreen
        this.exitFullscreen();

        const slot = document.getElementById(`slot-${slotId}`);
        if (!slot) return;

        slot.classList.add('fullscreen');

        // Update button title
        const btn = slot.querySelector('.maximize-btn');
        if (btn) btn.title = '退出最大化';

        // Hide sidebar and other slots
        document.querySelector('.sidebar')?.style.setProperty('display', 'none');
        document.querySelectorAll('.video-slot').forEach(s => {
            if (s.id !== `slot-${slotId}`) {
                s.style.setProperty('display', 'none');
            }
        });
    }

    exitFullscreen() {
        const fullscreenSlot = document.querySelector('.video-slot.fullscreen');
        if (!fullscreenSlot) return;

        fullscreenSlot.classList.remove('fullscreen');

        // Update button title
        const btn = fullscreenSlot.querySelector('.maximize-btn');
        if (btn) btn.title = '最大化';

        // Show sidebar and all slots
        document.querySelector('.sidebar')?.style.removeProperty('display');
        document.querySelectorAll('.video-slot').forEach(s => {
            s.style.removeProperty('display');
        });
    }

    // ==================== Screenshot ====================

    takeScreenshot(slotId) {
        const cameraId = this.slotAssignments[slotId];
        if (!cameraId) {
            this.showToast('该窗口未分配摄像头', 'warning');
            return;
        }

        const camera = this.cameras.find(c => c.id === cameraId);
        if (!camera) {
            this.showToast('摄像头不存在', 'error');
            return;
        }

        // Show loading toast
        this.showToast('正在截取图片...', 'info');

        // Create a temporary link to download the snapshot
        const link = document.createElement('a');
        link.href = `/api/snapshot/${cameraId}`;
        link.download = `${camera.name}_${new Date().getTime()}.jpg`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        // Show success message after a short delay
        setTimeout(() => {
            this.showToast('截图已保存', 'success');
        }, 500);
    }

    // ==================== Camera Loading & Sorting ====================

    async loadCameras() {
        try {
            const response = await fetch('/api/cameras');
            this.cameras = await response.json();
            this.renderTree();
            this.updateStats();
        } catch (error) {
            console.error('加载摄像头失败:', error);
            this.showToast('加载摄像头列表失败', 'error');
        }
    }

    setSort(sortBy) {
        this.sortBy = sortBy;
        document.getElementById('sortByIp')?.classList.toggle('active', sortBy === 'ip');
        document.getElementById('sortByName')?.classList.toggle('active', sortBy === 'name');
        this.renderTree();
    }

    getSortedCameras() {
        const sorted = [...this.cameras];
        if (this.sortBy === 'ip') {
            sorted.sort((a, b) => {
                const ipA = a.ip?.split('.').map(Number) || [];
                const ipB = b.ip?.split('.').map(Number) || [];
                for (let i = 0; i < 4; i++) {
                    if (ipA[i] !== ipB[i]) return ipA[i] - ipB[i];
                }
                return 0;
            });
        } else {
            sorted.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        }
        return sorted;
    }

    renderTree() {
        const container = document.getElementById('cameraTree');
        if (!container) return;

        const cameras = this.getSortedCameras();

        if (cameras.length === 0) {
            container.innerHTML = `
                <div class="tree-empty">
                    <p style="text-align:center;padding:40px 20px;color:var(--text-secondary);">
                        暂无摄像头<br>
                        <small>点击"扫描网络"或"添加"按钮</small>
                    </p>
                </div>
            `;
            return;
        }

        container.innerHTML = cameras.map(camera => {
            const isOnline = camera.is_online;
            const icon = isOnline ? '📹' : '📷';
            return `
                <div class="tree-item ${isOnline ? 'online' : 'offline'}" data-camera-id="${camera.id}">
                    <div class="tree-item-icon">${icon}</div>
                    <div class="tree-item-info">
                        <div class="tree-item-name">${this.escapeHtml(camera.name)}</div>
                        <div class="tree-item-ip">${camera.ip || 'Unknown'}</div>
                    </div>
                    <div class="tree-item-status ${isOnline ? 'online' : 'offline'}"></div>
                    <button class="tree-remove-btn" data-camera-id="${camera.id}" title="移除摄像头">×</button>
                </div>
            `;
        }).join('');

        // Setup drag, click and remove for each item
        container.querySelectorAll('.tree-item').forEach((item, index) => {
            this.setupTreeItemDrag(item, cameras[index]);
        });

        // Remove buttons — stop propagation so drag/context menu aren't triggered
        container.querySelectorAll('.tree-remove-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                e.preventDefault();
                const camId = e.target.dataset.cameraId;
                this.removeCamera(camId);
            });
        });
    }

    // ==================== Status Updates ====================

    startStatusUpdates() {
        setInterval(() => this.updateStreamStatus(), 2000);
    }

    async refreshCameras() {
        const btn = document.getElementById('refreshBtn');
        if (btn) {
            btn.disabled = true;
            btn.title = '检测中...';
        }
        this.showToast('正在重新检测摄像头在线状态...', 'info');

        try {
            await fetch('/api/cameras/refresh', { method: 'POST' });
        } catch (e) {
            // ignore, still poll below
        }

        // Poll status updates for ~8 s to reflect reconnect results
        let polls = 0;
        const pollRefresh = async () => {
            await this.updateStreamStatus();
            this.renderTree();
            polls++;
            if (polls < 8) {
                setTimeout(pollRefresh, 1000);
            } else {
                if (btn) {
                    btn.disabled = false;
                    btn.title = '刷新';
                }
                this.showToast('在线状态检测完成', 'success');
            }
        };
        setTimeout(pollRefresh, 1500); // give streams 1.5 s to start connecting
    }

    async updateStreamStatus() {
        try {
            const activeCamIds = Object.values(this.slotAssignments).filter(id => id);
            const mainCamId = this.slotAssignments['main'] || '';
            const queryParams = new URLSearchParams({
                active: activeCamIds.join(','),
                main: mainCamId
            }).toString();

            const response = await fetch(`/api/streams/status?${queryParams}`);
            const statuses = await response.json();

            // Update camera online status
            statuses.forEach(status => {
                const camera = this.cameras.find(c => c.id === status.camera_id);
                if (camera) {
                    camera.is_online = status.is_connected;
                }

                // Update slot status if this camera is assigned
                Object.entries(this.slotAssignments).forEach(([slotId, camId]) => {
                    if (camId === status.camera_id) {
                        const statusEl = document.getElementById(`status-${slotId}`);
                        const statusDot = statusEl?.querySelector('.status-dot');
                        const statusText = statusEl?.querySelector('.status-text');

                        if (status.is_connected) {
                            if (statusText) statusText.textContent = `${status.fps} FPS`;
                            if (statusDot) statusDot.className = 'status-dot online';
                        } else if (status.is_running) {
                            if (statusText) statusText.textContent = '连接中...';
                            if (statusDot) statusDot.className = 'status-dot connecting';
                        } else {
                            if (statusText) statusText.textContent = '离线';
                            if (statusDot) statusDot.className = 'status-dot';
                        }
                    }
                });
            });

            // Update stats
            const onlineCount = statuses.filter(s => s.is_connected).length;
            const onlineCountEl = document.getElementById('onlineCount');
            if (onlineCountEl) onlineCountEl.textContent = onlineCount;

            // Re-render tree to update online status
            if (this.cameras.some(c => c.is_online !== (c.is_online || false))) {
                this.renderTree();
            }
        } catch (error) {
            // Silent fail
        }
    }

    updateStats() {
        const totalEl = document.getElementById('totalCount');
        if (totalEl) totalEl.textContent = this.cameras.length;
        const onlineCount = this.cameras.filter(c => c.is_online).length;
        const onlineEl = document.getElementById('onlineCount');
        if (onlineEl) onlineEl.textContent = onlineCount;
    }

    // ==================== Scanning ====================

    async startScan() {
        const modal = document.getElementById('scanModal');
        const progressArea = document.getElementById('scanProgressArea');
        const resultsArea = document.getElementById('scanResults');
        const addAllBtn = document.getElementById('addAllBtn');

        this.showModal(modal);
        progressArea.style.display = 'block';
        resultsArea.style.display = 'none';
        addAllBtn.style.display = 'none';
        document.getElementById('scanStatusText').textContent = '正在启动扫描...';
        document.getElementById('scanProgressBar').style.width = '0%';
        document.getElementById('scanProgressText').textContent = '';

        try {
            const response = await fetch('/api/scan', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                this.pollScanStatus();
            } else {
                document.getElementById('scanStatusText').textContent = result.error || '扫描启动失败';
            }
        } catch (error) {
            document.getElementById('scanStatusText').textContent = '网络错误';
        }
    }

    async pollScanStatus() {
        const poll = async () => {
            try {
                const response = await fetch('/api/scan/status');
                const status = await response.json();

                document.getElementById('scanStatusText').textContent = status.message;

                if (status.total > 0) {
                    const percent = Math.round((status.progress / status.total) * 100);
                    document.getElementById('scanProgressBar').style.width = `${percent}%`;
                    document.getElementById('scanProgressText').textContent =
                        `${status.progress}/${status.total} (${percent}%) - 已发现 ${status.found} 个`;
                }

                if (!status.is_scanning) {
                    // Scan complete — auto-sync cameras and reset windows
                    document.getElementById('scanStatusText').textContent = '扫描完成，正在同步摄像头列表...';
                    await this.syncCamerasFromScan();
                } else {
                    setTimeout(poll, 1000);
                }
            } catch (error) {
                setTimeout(poll, 2000);
            }
        };
        poll();
    }

    async syncCamerasFromScan() {
        try {
            const response = await fetch('/api/cameras/sync', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                // Reset all video slots
                this.resetAllSlots();
                // Reload tree with new camera list
                await this.loadCameras();
                // Close scan modal
                this.closeModal(document.getElementById('scanModal'));
                this.showToast(`已同步 ${result.count} 个摄像头，所有窗口已重置`, 'success');
            } else {
                this.showToast(result.error || '同步失败', 'error');
                // Fall back: show results for manual add
                document.getElementById('scanProgressArea').style.display = 'none';
                document.getElementById('scanResults').style.display = 'block';
                document.getElementById('addAllBtn').style.display = 'inline-flex';
                await this.loadScanResultsToModal();
            }
        } catch (error) {
            console.error('同步摄像头失败:', error);
            this.showToast('同步失败，请检查网络', 'error');
        }
    }

    resetAllSlots() {
        const slots = ['main', 'sub1', 'sub2', 'sub3', 'sub4'];
        slots.forEach(slotId => {
            this.slotAssignments[slotId] = null;
            this.updateSlotDisplay(slotId, null);
        });
    }

    async loadScanResultsToModal() {
        try {
            const response = await fetch('/api/scan/results');
            const cameras = await response.json();
            this.renderScanResultsInModal(cameras);
        } catch (error) {
            console.error('加载扫描结果失败:', error);
        }
    }

    renderScanResultsInModal(cameras) {
        const container = document.getElementById('scanResults');
        if (cameras.length === 0) {
            container.innerHTML = '<p style="text-align:center;padding:30px;">未发现新摄像头</p>';
            return;
        }

        container.innerHTML = `
            <div style="margin-bottom:15px;color:var(--text-secondary);font-size:13px;">
                发现 ${cameras.length} 个摄像头
            </div>
            ${cameras.map(cam => `
                <div class="camera-list-item" data-camera-id="${cam.id}">
                    <div class="camera-list-info">
                        <h4>${this.escapeHtml(cam.name || 'Unknown')}</h4>
                        <p>${cam.ip} - ${cam.type || 'RTSP'}</p>
                    </div>
                    <button class="btn btn-primary btn-sm add-scan-cam-btn" data-camera-id="${cam.id}">
                        添加
                    </button>
                </div>
            `).join('')}
        `;

        // Bind add buttons
        container.querySelectorAll('.add-scan-cam-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const camId = e.target.dataset.cameraId;
                this.addDiscoveredCamera(camId, e.target);
            });
        });
    }

    async addDiscoveredCamera(camId, btn) {
        btn.disabled = true;
        btn.textContent = '添加中...';

        try {
            const response = await fetch(`/api/cameras/${camId}/add`, { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                btn.textContent = '已添加';
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-secondary');
                this.showToast('摄像头添加成功', 'success');
                await this.loadCameras();
            } else {
                btn.disabled = false;
                btn.textContent = '添加';
                this.showToast(result.error || '添加失败', 'error');
            }
        } catch (error) {
            btn.disabled = false;
            btn.textContent = '添加';
            this.showToast('添加失败', 'error');
        }
    }

    async addAllCameras() {
        const btn = document.getElementById('addAllBtn');
        btn.disabled = true;
        btn.textContent = '添加中...';

        try {
            const response = await fetch('/api/scan/results');
            const cameras = await response.json();

            let added = 0;
            for (const cam of cameras) {
                try {
                    await fetch(`/api/cameras/${cam.id}/add`, { method: 'POST' });
                    added++;
                } catch (e) {
                    // Continue with next
                }
            }

            this.showToast(`成功添加 ${added} 个摄像头`, 'success');
            await this.loadCameras();
            this.closeModal(document.getElementById('scanModal'));
        } catch (error) {
            this.showToast('添加失败', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = '添加全部';
        }
    }

    // ==================== Manual Add ====================

    showAddCameraModal() {
        this.showModal(document.getElementById('addCameraModal'));
    }

    showAssignCameraModal(slotId) {
        this.assigningToSlot = slotId;
        const modal = document.getElementById('assignCameraModal');
        const listContainer = document.getElementById('assignCameraList');

        // Update modal title
        const modalTitle = modal.querySelector('.modal-header h2');
        if (modalTitle) {
            modalTitle.textContent = `为 ${this.getSlotName(slotId)} 选择摄像头`;
        }

        // Render camera list
        if (this.cameras.length === 0) {
            listContainer.innerHTML = '<p style="text-align:center;padding:30px;color:var(--text-secondary);">暂无可用摄像头</p>';
        } else {
            listContainer.innerHTML = this.cameras.map(cam => `
                <div class="camera-list-item" data-camera-id="${cam.id}">
                    <div class="camera-list-info">
                        <h4>${this.escapeHtml(cam.name)}</h4>
                        <p>${cam.ip} - ${cam.is_online ? '在线' : '离线'}</p>
                    </div>
                    <button class="btn btn-primary btn-sm assign-camera-btn" data-camera-id="${cam.id}">
                        选择
                    </button>
                </div>
            `).join('');

            // Bind click events
            listContainer.querySelectorAll('.assign-camera-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const camId = e.target.dataset.cameraId;
                    const camera = this.cameras.find(c => c.id === camId);
                    if (camera) {
                        this.assignCameraToSlot(camera, this.assigningToSlot);
                        this.closeModal(modal);
                    }
                });
            });
        }

        this.showModal(modal);
    }

    async addCameraManual() {
        const form = document.getElementById('addCameraForm');
        const formData = new FormData(form);

        let rtspUrl = formData.get('rtsp_url');
        const username = formData.get('username');
        const password = formData.get('password');

        // Inject credentials into URL if provided
        if (username && password && rtspUrl) {
            try {
                const url = new URL(rtspUrl);
                url.username = username;
                url.password = password;
                rtspUrl = url.toString();
            } catch (e) {
                // Invalid URL, use as-is
            }
        }

        const data = {
            name: formData.get('name'),
            rtsp_url: rtspUrl,
        };

        try {
            const response = await fetch('/api/cameras', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('摄像头添加成功', 'success');
                this.closeModal(document.getElementById('addCameraModal'));
                form.reset();
                await this.loadCameras();
            } else {
                this.showToast(result.error || '添加失败', 'error');
            }
        } catch (error) {
            this.showToast('添加失败', 'error');
        }
    }

    // ==================== Remove Camera ====================

    async removeCamera(camId) {
        if (!confirm('确定要移除此摄像头吗？')) return;

        try {
            const response = await fetch(`/api/cameras/${camId}`, { method: 'DELETE' });
            const result = await response.json();

            if (result.success) {
                // Clear from slots if assigned
                Object.keys(this.slotAssignments).forEach(slotId => {
                    if (this.slotAssignments[slotId] === camId) {
                        this.clearSlot(slotId);
                    }
                });
                this.showToast('摄像头已移除', 'success');
                await this.loadCameras();
            } else {
                this.showToast('移除失败', 'error');
            }
        } catch (error) {
            this.showToast('移除失败', 'error');
        }
    }

    // ==================== UI Helpers ====================

    showModal(modal) {
        if (modal) modal.classList.add('active');
    }

    closeModal(modal) {
        if (modal) {
            modal.classList.remove('active');
            if (this.scanPollInterval) {
                clearInterval(this.scanPollInterval);
                this.scanPollInterval = null;
            }
        }
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize
const cameraViewer = new CameraViewer();

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        // Close modals first
        const activeModal = document.querySelector('.modal-overlay.active');
        if (activeModal) {
            activeModal.classList.remove('active');
        } else {
            // Exit fullscreen if no modal is open
            cameraViewer.exitFullscreen();
        }
    }
});
