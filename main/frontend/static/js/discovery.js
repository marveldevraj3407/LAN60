/**
 * Device discovery and recipient selection logic for 60% scope.
 */

const DiscoveryModule = {
  selectedPeerIds: new Set(),
  currentSourceItem: null, // { path, name, size }

  init() {
    this.bindEvents();
    this.refreshPeers();

    // Listen for live peer updates from UDP discovery
    API.on("PEERS_UPDATED", (peers) => {
      this.renderPeers(peers);
    });
  },

  bindEvents() {
    const btnSelectAll = document.getElementById("btn-select-all");
    const btnClearAll = document.getElementById("btn-clear-all");
    const btnSelectFile = document.getElementById("btn-select-file");
    const btnSend = document.getElementById("btn-send-transfer");
    const btnRefresh = document.getElementById("btn-refresh-discovery");

    if (btnSelectAll) {
      btnSelectAll.addEventListener("click", () => this.selectAllPeers());
    }
    if (btnClearAll) {
      btnClearAll.addEventListener("click", () => this.clearAllPeers());
    }
    if (btnSelectFile) {
      btnSelectFile.addEventListener("click", () => this.selectFile());
    }
    if (btnSend) {
      btnSend.addEventListener("click", () => this.startSendTransfer());
    }

    if (btnRefresh) {
      btnRefresh.addEventListener("click", async () => {
        btnRefresh.disabled = true;
        const origContent = btnRefresh.innerHTML;
        btnRefresh.innerHTML = `
          <svg class="spin-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"/><path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/></svg>
          <span>Scanning...</span>
        `;
        try {
          await API.refreshPeersBroadcast();
          showToast("Broadcasting network discovery...", "info");
          setTimeout(() => this.refreshPeers(), 600);
        } catch (err) {
          console.error("Refresh failed:", err);
        } finally {
          setTimeout(() => {
            btnRefresh.disabled = false;
            btnRefresh.innerHTML = origContent;
          }, 1000);
        }
      });
    }
  },

  async refreshPeers() {
    try {
      const data = await API.getPeers();
      this.renderPeers(data.peers || []);
    } catch (err) {
      console.error("Failed to fetch peers:", err);
    }
  },

  renderPeers(peers) {
    const container = document.getElementById("available-devices-list");
    const countBadge = document.getElementById("online-devices-count");
    if (!container) return;

    // Filter peers
    const onlinePeers = peers.filter((p) => p.is_online);
    if (countBadge) {
      countBadge.textContent = `${onlinePeers.length} online`;
    }
    const elStatusPeers = document.getElementById("status-peers");
    if (elStatusPeers) {
      elStatusPeers.textContent = `${onlinePeers.length} peer${onlinePeers.length === 1 ? "" : "s"} online`;
    }

    if (peers.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
              <rect width="18" height="12" x="3" y="4" rx="2"></rect><line x1="2" x2="22" y1="20" y2="20"></line>
            </svg>
          </div>
          <h3 class="empty-state-title">No devices found on local network</h3>
          <p class="empty-state-desc">Peers connected to the same Wi-Fi or subnet running LAN File Sharing will appear here automatically.</p>
          <button class="btn btn-secondary btn-sm" onclick="document.getElementById('btn-refresh-discovery').click()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
            <span>Scan again</span>
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = "";
    peers.forEach((peer) => {
      const isSelected = this.selectedPeerIds.has(peer.device_id);
      const card = document.createElement("div");
      card.className = `peer-card ${isSelected ? "selected" : ""}`;
      card.dataset.deviceId = peer.device_id;

      const initials = (peer.username || "P").charAt(0).toUpperCase();
      const statusPill = peer.is_online
        ? `<span class="badge badge-success"><span class="badge-dot"></span>Online</span>`
        : `<span class="badge badge-neutral"><span class="badge-dot"></span>Offline</span>`;

      card.innerHTML = `
        <div class="peer-info">
          <input type="checkbox" class="custom-checkbox peer-checkbox" ${isSelected ? "checked" : ""} ${!peer.is_online ? "disabled" : ""} aria-label="Select ${escapeHtml(peer.username)}">
          <div class="peer-avatar">${initials}</div>
          <div class="peer-details">
            <div class="peer-name">
              <span>${escapeHtml(peer.username)}</span>
              <span class="peer-hostname">— ${escapeHtml(peer.hostname)}</span>
            </div>
            <div class="peer-sub">
              <span class="ip-tag tabular-nums">${escapeHtml(peer.ip)}</span>
              <span class="port-tag tabular-nums">:${peer.tcp_port}</span>
            </div>
          </div>
        </div>
        <div class="peer-status-col">
          ${statusPill}
        </div>
      `;

      card.addEventListener("click", (e) => {
        if (!peer.is_online) return;
        const chk = card.querySelector(".peer-checkbox");
        if (e.target !== chk) {
          chk.checked = !chk.checked;
        }
        if (chk.checked) {
          this.selectedPeerIds.add(peer.device_id);
          card.classList.add("selected");
        } else {
          this.selectedPeerIds.delete(peer.device_id);
          card.classList.remove("selected");
        }
        this.updateSendButtonState();
      });

      container.appendChild(card);
    });

    this.updateSendButtonState();
  },

  selectAllPeers() {
    const cards = document.querySelectorAll(".peer-card");
    cards.forEach((card) => {
      const chk = card.querySelector(".peer-checkbox");
      if (chk && !chk.disabled) {
        chk.checked = true;
        this.selectedPeerIds.add(card.dataset.deviceId);
        card.classList.add("selected");
      }
    });
    this.updateSendButtonState();
  },

  clearAllPeers() {
    this.selectedPeerIds.clear();
    const cards = document.querySelectorAll(".peer-card");
    cards.forEach((card) => {
      const chk = card.querySelector(".peer-checkbox");
      if (chk) chk.checked = false;
      card.classList.remove("selected");
    });
    this.updateSendButtonState();
  },

  async selectFile() {
    const btn = document.getElementById("btn-select-file");
    if (btn) btn.classList.add("loading");
    showToast("Opening file dialog...", "info");
    try {
      const res = await API.selectFileNative();
      if (res && res.selected) {
        this.currentSourceItem = res;
        this.renderSelectedFile();
        showToast(`Selected file: ${res.name}`, "success");
      } else {
        showToast("No file selected", "neutral");
      }
    } catch (err) {
      showToast(`Error opening file dialog: ${err}`, "error");
    } finally {
      if (btn) btn.classList.remove("loading");
    }
  },

  clearSelectedFile() {
    this.currentSourceItem = null;
    this.renderSelectedFile();
  },

  renderSelectedFile() {
    const box = document.getElementById("selected-file-display");
    const btnFile = document.getElementById("btn-select-file");

    if (btnFile) {
      btnFile.classList.remove("active-selection");
      if (this.currentSourceItem) {
        btnFile.classList.add("active-selection");
      }
    }

    if (!box) return;

    if (!this.currentSourceItem) {
      box.className = "selected-file-box";
      box.innerHTML = `
        <div class="empty-selection-placeholder">
          <div class="placeholder-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
              <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>
            </svg>
          </div>
          <div class="placeholder-text">
            <span class="placeholder-main">No file selected</span>
            <span class="placeholder-sub">Click Select File above to choose a file</span>
          </div>
        </div>
      `;
    } else {
      box.className = "selected-file-box active";
      const sizeStr = formatBytes(this.currentSourceItem.size || 0);

      box.innerHTML = `
        <div class="selected-item-card">
          <div class="selected-item-left">
            <div class="selected-type-badge file">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/></svg>
            </div>
            <div class="selected-item-meta">
              <div class="selected-item-name-row">
                <span class="selected-item-name">${escapeHtml(this.currentSourceItem.name)}</span>
                <span class="badge badge-neutral tabular-nums">${sizeStr}</span>
              </div>
              <div class="selected-item-path mono" title="${escapeHtml(this.currentSourceItem.path)}">
                ${escapeHtml(this.currentSourceItem.path)}
              </div>
            </div>
          </div>
          <button type="button" class="btn btn-ghost btn-sm" title="Deselect item" onclick="DiscoveryModule.clearSelectedFile()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            <span>Clear</span>
          </button>
        </div>
      `;
    }
    this.updateSendButtonState();
  },

  updateSendButtonState() {
    const btn = document.getElementById("btn-send-transfer");
    if (!btn) return;
    const hasRecipients = this.selectedPeerIds.size > 0;
    const hasItem = !!this.currentSourceItem;
    btn.disabled = !(hasRecipients && hasItem);

    if (hasRecipients) {
      const count = this.selectedPeerIds.size;
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
        <span>Send to ${count} recipient${count > 1 ? "s" : ""}</span>
      `;
    } else {
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
        <span>Send</span>
      `;
    }
  },

  async startSendTransfer() {
    if (!this.currentSourceItem || this.selectedPeerIds.size === 0) return;

    const payload = {
      source_path: this.currentSourceItem.path,
      recipients: Array.from(this.selectedPeerIds),
    };

    const btn = document.getElementById("btn-send-transfer");
    if (btn) btn.disabled = true;

    try {
      showToast(`Initiating transfer to ${this.selectedPeerIds.size} recipient(s)...`, "info");
      const res = await API.sendTransfer(payload);
      if (res.success) {
        showToast("Transfer request sent! Waiting for receiver approval.", "success");
        this.clearSelectedFile();
        window.switchTab("tab-transfers");
      } else {
        showToast(`Failed: ${res.message}`, "error");
      }
    } catch (err) {
      showToast(`Transfer error: ${err}`, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  },
};

function formatBytes(bytes, decimals = 2) {
  if (!+bytes) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
