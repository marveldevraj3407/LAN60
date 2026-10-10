/**
 * API client and Server-Sent Events (SSE) connector for 60% scope.
 */

const API = {
  // --- REST ENDPOINTS ---
  async getStatus() {
    const res = await fetch("/api/status");
    return await res.json();
  },

  async setupUser(username) {
    const res = await fetch("/api/user/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringify({ username }),
    });
    return await res.json();
  },

  async updateUser(username) {
    const res = await fetch("/api/user/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringify({ username }),
    });
    return await res.json();
  },

  async getPeers() {
    const res = await fetch("/api/peers");
    return await res.json();
  },

  async pingPeer(ip) {
    const res = await fetch("/api/peers/ping", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringify({ ip }),
    });
    return await res.json();
  },

  async refreshPeersBroadcast() {
    const res = await fetch("/api/peers/refresh", { method: "POST" });
    return await res.json();
  },

  async selectFileNative() {
    const res = await fetch("/api/select_file", { method: "POST" });
    return await res.json();
  },

  async selectPathDirect(path) {
    const res = await fetch("/api/select_path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringify({ path }),
    });
    return await res.json();
  },

  async sendTransfer(payload) {
    const res = await fetch("/api/transfers/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringify(payload),
    });
    return await res.json();
  },

  async acceptTransfer(transferId) {
    const res = await fetch(`/api/transfers/${transferId}/accept`, { method: "POST" });
    return await res.json();
  },

  async rejectTransfer(transferId) {
    const res = await fetch(`/api/transfers/${transferId}/reject`, { method: "POST" });
    return await res.json();
  },

  async getSettings() {
    const res = await fetch("/api/settings");
    return await res.json();
  },

  async saveSettings(settings) {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringify(settings),
    });
    return await res.json();
  },

  async chooseDownloadDirNative() {
    const res = await fetch("/api/settings/choose_download_dir", { method: "POST" });
    return await res.json();
  },

  // --- SSE EVENT BUS ---
  _eventHandlers: {},

  on(eventName, handler) {
    if (!this._eventHandlers[eventName]) {
      this._eventHandlers[eventName] = [];
    }
    this._eventHandlers[eventName].push(handler);
  },

  emit(eventName, payload) {
    const handlers = this._eventHandlers[eventName] || [];
    handlers.forEach((fn) => {
      try {
        fn(payload);
      } catch (err) {
        console.error(`Error in handler for ${eventName}:`, err);
      }
    });
  },

  initEventStream() {
    console.log("Connecting to real-time SSE event stream...");
    const evtSource = new EventSource("/api/events");

    evtSource.onmessage = (e) => {
      try {
        const message = JSON.parse(e.data);
        if (message.event && message.event !== "PING") {
          this.emit(message.event, message.data);
        }
      } catch (err) {
        console.debug("SSE Parse error:", err);
      }
    };

    evtSource.onerror = (err) => {
      console.warn("SSE connection interrupted. Auto-reconnecting...", err);
    };
  },
};

function jsonStringify(obj) {
  return JSON.stringify(obj);
}
