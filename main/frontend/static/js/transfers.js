/**
 * Transfers manager, progress visualization, and incoming modal for 60% scope.
 */

const TransfersModule = {
  activeJobs: {}, // transfer_id -> job data
  pendingIncomingRequests: [],

  init() {
    this.setupSSEListeners();
    this.renderActiveTransfers();
  },

  setupSSEListeners() {
    // 1. Incoming transfer request
    API.on("INCOMING_TRANSFER_REQUEST", (req) => {
      this.pendingIncomingRequests.push(req);
      this.updateIncomingBadge();
      this.showIncomingModal(req);
    });

    // 2. Transfer started
    API.on("TRANSFER_STARTED", (data) => {
      this.activeJobs[data.transfer_id] = {
        id: data.transfer_id,
        direction: data.direction,
        name: data.item_name,
        peer_username: data.peer_username || "Peer",
        total_bytes: data.total_bytes,
        transferred_bytes: 0,
        percent: 0,
        speed_mbps: 0,
        status: "IN_PROGRESS",
      };
      this.renderActiveTransfers();
    });

    // 3. Transfer progress
    API.on("TRANSFER_PROGRESS", (data) => {
      if (!this.activeJobs[data.transfer_id]) {
        this.activeJobs[data.transfer_id] = { id: data.transfer_id };
      }
      Object.assign(this.activeJobs[data.transfer_id], data);
      this.renderActiveTransfers();
    });

    // 4. Transfer completed
    API.on("TRANSFER_COMPLETED", (data) => {
      if (this.activeJobs[data.transfer_id]) {
        this.activeJobs[data.transfer_id].status = "COMPLETED";
        this.activeJobs[data.transfer_id].percent = 100;
      }
      this.renderActiveTransfers();
      showToast(`Transfer complete: ${data.item_name}`, "success");
    });

    // 5. Transfer failed
    API.on("TRANSFER_FAILED", (data) => {
      if (this.activeJobs[data.transfer_id]) {
        this.activeJobs[data.transfer_id].status = "FAILED";
        this.activeJobs[data.transfer_id].error = data.error;
      }
      this.renderActiveTransfers();
      showToast(`Transfer failed: ${data.error}`, "error");
    });

    // 6. Transfer rejected
    API.on("TRANSFER_REJECTED", (data) => {
      if (this.activeJobs[data.transfer_id]) {
        this.activeJobs[data.transfer_id].status = "REJECTED";
      }
      this.renderActiveTransfers();
      showToast(`Recipient rejected transfer: ${data.reason}`, "warning");
    });
  },

  updateIncomingBadge() {
    const badge = document.getElementById("incoming-count-badge");
    if (!badge) return;
    const count = this.pendingIncomingRequests.length;
    badge.textContent = count;
    badge.style.display = count > 0 ? "inline-block" : "none";
  },

  showIncomingModal(req) {
    const modal = document.getElementById("incoming-request-modal");
    if (!modal) return;

    document.getElementById("modal-sender-name").textContent =
      `${req.sender_username} — ${req.sender_hostname}`;
    document.getElementById("modal-file-name").textContent = req.item_name;
    document.getElementById("modal-file-size").textContent = formatBytes(req.total_bytes);

    const btnAccept = document.getElementById("modal-btn-accept");
    const btnReject = document.getElementById("modal-btn-reject");

    btnAccept.onclick = async () => {
      modal.classList.remove("active");
      this.pendingIncomingRequests = this.pendingIncomingRequests.filter(
        (r) => r.transfer_id !== req.transfer_id
      );
      this.updateIncomingBadge();
      await API.acceptTransfer(req.transfer_id);
      showToast(`Accepted transfer of ${req.item_name}`, "success");
      window.switchTab("tab-transfers");
    };

    btnReject.onclick = async () => {
      modal.classList.remove("active");
      this.pendingIncomingRequests = this.pendingIncomingRequests.filter(
        (r) => r.transfer_id !== req.transfer_id
      );
      this.updateIncomingBadge();
      await API.rejectTransfer(req.transfer_id);
      showToast(`Rejected transfer of ${req.item_name}`, "info");
    };

    modal.classList.add("active");
  },

  renderActiveTransfers() {
    const container = document.getElementById("active-transfers-container");
    if (!container) return;

    const jobs = Object.values(this.activeJobs);
    const inProgressJobs = jobs.filter((j) => j.status === "IN_PROGRESS");
    const elStatusTransfers = document.getElementById("status-transfers");
    if (elStatusTransfers) {
      elStatusTransfers.textContent = `${inProgressJobs.length} active transfer${inProgressJobs.length === 1 ? "" : "s"}`;
    }

    if (jobs.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
              <path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="m21 8-4-4-4 4"/><path d="M17 4v16"/>
            </svg>
          </div>
          <h3 class="empty-state-title">No active file transfers</h3>
          <p class="empty-state-desc">Transfers will appear here in real time as files are sent or received.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = "";
    jobs.forEach((job) => {
      const card = document.createElement("div");
      card.className = "transfer-card";

      const isIncoming = job.direction === "INCOMING";
      const dirIcon = isIncoming
        ? `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><line x1="17" x2="7" y1="7" y2="17"/><polyline points="17 17 7 17 7 7"/></svg>`
        : `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><line x1="7" x2="17" y1="17" y2="7"/><polyline points="7 7 17 7 17 17"/></svg>`;
      const dirText = isIncoming ? "Receiving from" : "Sending to";
      const peerText = job.peer_username || "Peer";

      let statusBadgeClass = "badge-neutral";
      if (job.status === "IN_PROGRESS") statusBadgeClass = "badge-info";
      if (job.status === "COMPLETED") statusBadgeClass = "badge-success";
      if (job.status === "FAILED") statusBadgeClass = "badge-danger";
      if (job.status === "REJECTED") statusBadgeClass = "badge-warning";

      let progressClass = "";
      if (job.status === "COMPLETED") progressClass = "progress-success";
      if (job.status === "FAILED" || job.status === "REJECTED") progressClass = "progress-danger";

      card.innerHTML = `
        <div class="transfer-header">
          <div class="transfer-title">
            <span class="transfer-dir-icon">${dirIcon}</span>
            <span class="transfer-item-name">${escapeHtml(job.name || "Transfer")}</span>
            <span class="transfer-peer-caption">(${dirText} ${escapeHtml(peerText)})</span>
          </div>
          <div>
            <span class="badge ${statusBadgeClass}">
              <span class="badge-dot"></span>
              ${job.status}
            </span>
          </div>
        </div>

        <div class="transfer-stats">
          <div class="transfer-stats-left">
            <span class="tabular-nums">${formatBytes(job.transferred_bytes || 0)} / ${formatBytes(job.total_bytes || 0)}</span>
            <span class="transfer-speed tabular-nums">${job.speed_mbps || 0} MB/s</span>
            <span class="transfer-chunk-size tabular-nums">(Fixed 64 KB Chunks)</span>
          </div>
          <div class="transfer-stats-right">
            <span class="transfer-percent tabular-nums">${job.progress_percent || job.percent || 0}%</span>
          </div>
        </div>

        <div class="progress-bar">
          <div class="progress-fill ${progressClass}" style="width: ${job.progress_percent || job.percent || 0}%;"></div>
        </div>
      `;

      container.appendChild(card);
    });
  },
};
