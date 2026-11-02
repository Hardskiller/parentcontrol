// ParentControl dashboard card: device list, PIN entry, settings and history.
// The integration serves this file and loads it on every dashboard.

const TEXTS = {
  de: {
    history: "Verlauf",
    general: "Allgemein",
    lock: "Sperren",
    unlock: "Entsperren",
    enterPin: "PIN eingeben",
    cancel: "Abbrechen",
    back: "Zurück",
    age: "Alter",
    defaultAge: "Standardalter",
    check: "Prüfung",
    minutes: "min",
    allowed: "Freigegebene Kanäle",
    blocked: "Gesperrte Kanäle",
    channel: "Kanal",
    allow: "Freigeben",
    block: "Sperren",
    remove: "Entfernen",
    noVideo: "Kein Video",
    noHistory: "Noch keine Videos",
    noEntries: "Keine Einträge",
    noLock: "ParentControl wurde nicht gefunden.",
    deviceOnly: "Diese Listen gelten nur für dieses Gerät, zusätzlich zu den Listen unter Allgemein.",
    fromAge: "ab",
    today: "Heute",
    services: "Dienste",
    reasonLabel: "Einstufung",
    more: "Mehr anzeigen",
    pedagogyLabel: "Pädagogik",
    blockLabel: "Gesperrt",
    wordsLabel: "Schimpfwörter",
    status: {
      frei: "Frei",
      blockiert: "Blockiert",
      wird_geprueft: "Wird geprüft",
      nicht_geprueft: "Nicht geprüft",
      keine_daten: "Keine Daten",
      inaktiv: "Inaktiv",
      aus: "Prüfung aus",
    },
    reasons: {
      alter: "zu jung",
      paedagogik: "nicht pädagogisch wertvoll",
      schimpfwoerter: "Schimpfwörter",
      keine_untertitel: "keine Untertitel",
      nicht_geprueft: "nicht geprüft",
      kanal_gesperrt: "Kanal gesperrt",
      short: "Short",
    },
    settings: {
      seek_to_start: "An den Anfang springen",
      require_pedagogy: "Nur pädagogisch wertvoll",
      block_profanity: "Schimpfwörter blockieren",
      strict: "Strenge Bewertung",
      skip_checks: "Freigegebene Kanäle ohne Prüfung",
      block_shorts: "Shorts sperren",
    },
    stats: {
      videos: "Videos",
      approved: "Genehmigt",
      valuable: "Pädagogisch wertvoll",
      skipped: "Geskippt",
    },
    health: { ollama: "Ollama", yt_dlp: "YouTube-Abfrage" },
    editor: {
      title: "Titel",
      entity: "Schloss-Entität (leer = automatisch)",
      show_valuable: "Symbol für pädagogisch wertvoll",
      show_profanity: "Symbol für Schimpfwörter",
      show_shorts: "Symbol für Shorts",
      show_age: "Alter in der Liste",
      show_watch_time: "Schauzeit in der Liste",
      history_limit: "Einträge im Verlauf vor „Mehr anzeigen“",
      nameFor: "Anzeigename für",
    },
    online: "verbunden",
    offline: "nicht erreichbar",
    unknown: "unbekannt",
  },
  en: {
    history: "History",
    general: "General",
    lock: "Lock",
    unlock: "Unlock",
    enterPin: "Enter PIN",
    cancel: "Cancel",
    back: "Back",
    age: "Age",
    defaultAge: "Default age",
    check: "Check",
    minutes: "min",
    allowed: "Allowed channels",
    blocked: "Blocked channels",
    channel: "Channel",
    allow: "Allow",
    block: "Block",
    remove: "Remove",
    noVideo: "No video",
    noHistory: "No videos yet",
    noEntries: "No entries",
    noLock: "ParentControl was not found.",
    deviceOnly: "These lists apply only to this device, in addition to the lists under General.",
    fromAge: "from",
    today: "Today",
    services: "Services",
    reasonLabel: "Rating",
    more: "Show more",
    pedagogyLabel: "Education",
    blockLabel: "Blocked",
    wordsLabel: "Swear words",
    status: {
      frei: "Allowed",
      blockiert: "Blocked",
      wird_geprueft: "Checking",
      nicht_geprueft: "Not checked",
      keine_daten: "No data",
      inaktiv: "Idle",
      aus: "Check off",
    },
    reasons: {
      alter: "too young",
      paedagogik: "not educational",
      schimpfwoerter: "swear words",
      keine_untertitel: "no subtitles",
      nicht_geprueft: "not checked",
      kanal_gesperrt: "channel blocked",
      short: "Short",
    },
    settings: {
      seek_to_start: "Jump to start",
      require_pedagogy: "Educational only",
      block_profanity: "Block swear words",
      strict: "Strict rating",
      skip_checks: "Allowed channels skip checks",
      block_shorts: "Block Shorts",
    },
    stats: {
      videos: "Videos",
      approved: "Approved",
      valuable: "Educational",
      skipped: "Skipped",
    },
    health: { ollama: "Ollama", yt_dlp: "YouTube lookup" },
    editor: {
      title: "Title",
      entity: "Lock entity (empty = automatic)",
      show_valuable: "Marker for educational videos",
      show_profanity: "Marker for swear words",
      show_shorts: "Marker for Shorts",
      show_age: "Age in the list",
      show_watch_time: "Watch time in the list",
      history_limit: "History entries before “Show more”",
      nameFor: "Display name for",
    },
    online: "connected",
    offline: "unreachable",
    unknown: "unknown",
  },
};

const SETTINGS = [
  "seek_to_start",
  "require_pedagogy",
  "block_profanity",
  "strict",
  "skip_checks",
  "block_shorts",
];
const STATS = ["videos", "approved", "valuable", "skipped"];
const HEALTH = ["ollama", "yt_dlp"];

const STATUS_ICONS = {
  frei: ["mdi:check-circle", "var(--success-color, #43a047)"],
  blockiert: ["mdi:cancel", "var(--error-color, #db4437)"],
  wird_geprueft: ["mdi:progress-clock", "var(--warning-color, #ffa600)"],
  nicht_geprueft: ["mdi:help-circle", "var(--warning-color, #ffa600)"],
  keine_daten: ["mdi:help-circle-outline", "var(--secondary-text-color)"],
  inaktiv: ["mdi:sleep", "var(--secondary-text-color)"],
  aus: ["mdi:shield-off", "var(--secondary-text-color)"],
};

const OPTIONS = ["show_valuable", "show_profanity", "show_shorts", "show_age", "show_watch_time"];

const texts = (hass) =>
  TEXTS[(hass?.locale?.language || hass?.language || "en").slice(0, 2)] || TEXTS.en;

const findLock = (hass, config) => {
  const id =
    config.entity ||
    Object.values(hass.entities || {}).find(
      (entry) => entry.platform === "parentcontrol" && entry.entity_id.startsWith("lock."),
    )?.entity_id;
  return id ? hass.states[id] : undefined;
};

const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );

class ParentControlCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = "list";
    this._player = null;
    this._pin = "";
    this._pinTarget = null;
    this._message = "";
    this._drafts = {};
    this._expanded = new Set();
    this._limit = 0;
    this._signature = "";
    this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
    this.shadowRoot.addEventListener("input", (event) => {
      if (event.target.dataset.draft) this._drafts[event.target.dataset.draft] = event.target.value;
    });
  }

  static getStubConfig() {
    return {};
  }

  static getConfigElement() {
    return document.createElement("parentcontrol-card-editor");
  }

  setConfig(config) {
    this._config = config || {};
    this._signature = "";
    this._render();
  }

  getCardSize() {
    return 5;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  get _t() {
    return texts(this._hass);
  }

  _lock() {
    return findLock(this._hass, this._config);
  }

  _devices(lock) {
    return (lock.attributes.geraete || [])
      .map((id) => this._hass.states[id])
      .filter(Boolean);
  }

  _isOpen(lock) {
    return lock.state === "unlocked" || Boolean(this._hass.user?.is_admin);
  }

  _state(id) {
    return id ? this._hass.states[id] : undefined;
  }

  // Only redraw when something shown changed, and never while typing.
  _render() {
    if (!this._hass || !this._config) return;
    const lock = this._lock();
    const ids = lock
      ? [
          lock.entity_id,
          ...Object.values(lock.attributes.entitaeten || {}),
          ...this._devices(lock).flatMap((device) => [
            device.entity_id,
            ...Object.values(device.attributes.entitaeten || {}),
          ]),
        ]
      : [];
    const signature = JSON.stringify([
      ids.map((id) => this._hass.states[id]?.last_updated),
      this._view,
      this._player,
      this._pin,
      this._pinTarget,
      this._message,
      this._hass.user?.is_admin,
      [...this._expanded],
      this._limit,
    ]);
    if (signature === this._signature) return;
    const active = this.shadowRoot.activeElement;
    if (active && active.tagName === "INPUT") return;
    this._signature = signature;
    if (!lock) {
      this._draw(`<div class="empty">${this._t.noLock}</div>`);
      return;
    }
    if (!this._isOpen(lock) && this._view !== "list") {
      // The lock closed again after five minutes.
      this._view = "list";
    }
    let body;
    if (this._pinTarget) body = this._pinPad(lock);
    else if (this._view === "device") body = this._deviceView(lock);
    else if (this._view === "history") body = this._historyView(lock);
    else if (this._view === "general") body = this._generalView(lock);
    else body = this._listView(lock);
    this._draw(this._header(lock) + this._messageBar() + body);
  }

  _draw(html) {
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${html}</ha-card>`;
  }

  _header(lock) {
    const t = this._t;
    const open = this._isOpen(lock);
    const lockButton =
      lock.state === "unlocked"
        ? `<button class="chip" data-action="lock"><ha-icon icon="mdi:lock-open-variant"></ha-icon>${t.lock}</button>`
        : open
          ? ""
          : `<button class="chip" data-action="open" data-target="list"><ha-icon icon="mdi:lock"></ha-icon>${t.unlock}</button>`;
    return `<div class="header">
      <div class="title">${escape(this._config.title || "ParentControl")}</div>
      <div class="actions">
        <button class="chip" data-action="open" data-target="history"><ha-icon icon="mdi:history"></ha-icon>${t.history}</button>
        <button class="chip" data-action="open" data-target="general"><ha-icon icon="mdi:cog"></ha-icon>${t.general}</button>
        ${lockButton}
      </div>
    </div>`;
  }

  _messageBar() {
    return this._message
      ? `<div class="message" data-action="dismiss">${escape(this._message)}</div>`
      : "";
  }

  _statusIcon(status) {
    const [icon, color] = STATUS_ICONS[status] || STATUS_ICONS.inaktiv;
    return `<ha-icon class="status" icon="${icon}" style="color:${color}"></ha-icon>`;
  }

  _name(device) {
    return this._config.names?.[device.entity_id] || device.attributes.name;
  }

  _show(option) {
    return this._config[option] !== false;
  }

  _markers(attributes) {
    const t = this._t;
    let html = "";
    if (attributes.paedagogisch_wertvoll && this._show("show_valuable"))
      html += `<ha-icon class="marker valuable" icon="mdi:school" title="${t.stats.valuable}"></ha-icon>`;
    if (attributes.schimpfwoerter && this._show("show_profanity"))
      html += `<ha-icon class="marker profanity" icon="mdi:message-alert" title="${t.reasons.schimpfwoerter}"></ha-icon>`;
    if (attributes.short && this._show("show_shorts"))
      html += `<ha-icon class="marker" icon="mdi:cellphone-play" title="Short"></ha-icon>`;
    return html;
  }

  // The block reason always shows; the model's rating only when expanded.
  _reasonLines(attributes, full) {
    const t = this._t;
    let html = "";
    // Entries from before 0.3.3 have no block text, only the reason key.
    const blockText =
      attributes.sperrtext || (attributes.sperrgrund && (t.reasons[attributes.sperrgrund] || attributes.sperrgrund));
    if (blockText) html += `<div class="sub why">${t.blockLabel}: ${escape(blockText)}</div>`;
    const words = attributes.schimpfwoerter_liste || [];
    if (words.length && attributes.sperrgrund !== "schimpfwoerter")
      html += `<div class="sub">${t.wordsLabel}: ${escape(words.join(", "))}</div>`;
    if (full && attributes.grund)
      html += `<div class="sub wrap">${t.reasonLabel}: ${escape(attributes.grund)}</div>`;
    return html;
  }

  _listView(lock) {
    const t = this._t;
    const rows = this._devices(lock).map((device) => {
      const a = device.attributes;
      const watch = this._state(a.entitaeten?.watch_time)?.state;
      const age = this._state(a.entitaeten?.age)?.state ?? a.alter;
      return `<button class="row" data-action="open" data-target="device" data-player="${escape(device.entity_id)}">
        ${this._statusIcon(device.state)}
        <div class="main">
          <div class="name">${escape(this._name(device))}</div>
          <div class="sub">${a.titel ? escape(a.titel) : t.noVideo}</div>
        </div>
        <div class="markers">${this._markers(a)}</div>
        <div class="meta">
          ${this._show("show_age") ? `<div>${t.age} ${escape(age)}</div>` : ""}
          ${this._show("show_watch_time") ? `<div>${escape(watch ?? 0)} ${t.minutes}</div>` : ""}
        </div>
      </button>`;
    });
    return `<div class="list">${rows.join("")}</div>`;
  }

  _pinPad(lock) {
    const t = this._t;
    const blocked = lock.attributes.gesperrt_sekunden;
    const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "back", "0", "ok"].map((key) => {
      if (key === "back")
        return `<button class="key" data-action="pin-back"><ha-icon icon="mdi:backspace-outline"></ha-icon></button>`;
      if (key === "ok")
        return `<button class="key ok" data-action="pin-ok"><ha-icon icon="mdi:check"></ha-icon></button>`;
      return `<button class="key" data-action="pin-digit" data-digit="${key}">${key}</button>`;
    });
    const dots = "●".repeat(this._pin.length) || "&nbsp;";
    return `<div class="pin">
      <div class="pin-title">${t.enterPin}</div>
      <div class="dots">${dots}</div>
      ${blocked ? `<div class="hint">${Math.ceil(blocked / 60)} ${t.minutes}</div>` : ""}
      <div class="pad">${keys.join("")}</div>
      <button class="link" data-action="pin-cancel">${t.cancel}</button>
    </div>`;
  }

  _toggle(entityId, label) {
    const state = this._state(entityId);
    if (!state) return "";
    const on = state.state === "on";
    return `<button class="toggle ${on ? "on" : ""}" data-action="toggle" data-entity="${escape(entityId)}">
      <span>${escape(label)}</span><span class="switch"><span></span></span>
    </button>`;
  }

  _stepper(entityId, label) {
    const state = this._state(entityId);
    if (!state) return "";
    const value = Number(state.state);
    return `<div class="stepper">
      <span>${escape(label)}</span>
      <div>
        <button class="round" data-action="number" data-entity="${escape(entityId)}" data-value="${value - 1}"><ha-icon icon="mdi:minus"></ha-icon></button>
        <span class="value">${escape(state.state)}</span>
        <button class="round" data-action="number" data-entity="${escape(entityId)}" data-value="${value + 1}"><ha-icon icon="mdi:plus"></ha-icon></button>
      </div>
    </div>`;
  }

  _lists(allowed, blocked, player) {
    const t = this._t;
    const scope = player || "global";
    const target = player ? `data-player="${escape(player)}"` : "";
    const item = (entry, list) => `<li>
        <span>${escape(entry.kanal)}${list === "allowed" ? ` <small>${t.fromAge} ${entry.alter}</small>` : ""}</span>
        <button class="icon" title="${t.remove}" data-action="remove" data-list="${list}" data-channel="${escape(entry.kanal)}" ${target}><ha-icon icon="mdi:close"></ha-icon></button>
      </li>`;
    const list = (entries, name) =>
      entries.length
        ? `<ul>${entries.map((entry) => item(entry, name)).join("")}</ul>`
        : `<div class="hint">${t.noEntries}</div>`;
    return `<div class="section">
      ${player ? `<div class="hint">${t.deviceOnly}</div>` : ""}
      <h3>${t.allowed}</h3>${list(allowed || [], "allowed")}
      <h3>${t.blocked}</h3>${list(blocked || [], "blocked")}
      <div class="add">
        <input data-draft="channel-${scope}" placeholder="${t.channel}" value="${escape(this._drafts[`channel-${scope}`] || "")}">
        <input data-draft="age-${scope}" class="age" type="number" min="0" max="18" placeholder="${t.age}" value="${escape(this._drafts[`age-${scope}`] || "")}">
        <button class="chip" data-action="add" data-allow="1" data-scope="${scope}" ${target}>${t.allow}</button>
        <button class="chip" data-action="add" data-allow="0" data-scope="${scope}" ${target}>${t.block}</button>
      </div>
    </div>`;
  }

  _historyItems(entries, showDevice) {
    const t = this._t;
    if (!entries.length) return `<div class="hint">${t.noHistory}</div>`;
    const limit = this._limit || Number(this._config.history_limit) || 10;
    const more =
      entries.length > limit
        ? `<button class="link more" data-action="more" data-limit="${limit + 10}">${t.more}</button>`
        : "";
    return `<ul class="history">${entries
      .slice(0, limit)
      .map((entry) => {
        const key = `${entry.zeit}|${entry.titel}`;
        const expanded = this._expanded.has(key);
        const time = new Date(entry.zeit).toLocaleTimeString(this._hass.locale?.language, {
          hour: "2-digit",
          minute: "2-digit",
        });
        const age = entry.mindestalter != null ? ` · ${t.fromAge} ${entry.mindestalter}` : "";
        return `<li>
          ${this._statusIcon(entry.status)}
          <div class="main" data-action="expand" data-key="${escape(key)}">
            <div class="name ${expanded ? "wrap" : ""}">${escape(entry.titel)}</div>
            <div class="sub">${time}${showDevice ? ` · ${escape(entry.geraet)}` : ""} · ${escape(entry.kanal)}${age}</div>
            ${this._reasonLines(entry, expanded)}
          </div>
          <div class="markers">${this._markers(entry)}</div>
          ${
            entry.kanal
              ? `<div class="buttons">
            <button class="icon" title="${t.allow}" data-action="list-channel" data-allow="1" data-channel="${escape(entry.kanal)}"><ha-icon icon="mdi:check"></ha-icon></button>
            <button class="icon" title="${t.block}" data-action="list-channel" data-allow="0" data-channel="${escape(entry.kanal)}"><ha-icon icon="mdi:cancel"></ha-icon></button>
          </div>`
              : ""
          }
        </li>`;
      })
      .join("")}</ul>${more}`;
  }

  _deviceView(lock) {
    const t = this._t;
    const device = this._state(this._player);
    if (!device) return this._listView(lock);
    const a = device.attributes;
    const ids = a.entitaeten || {};
    const history = this._state(ids.history)?.attributes.videos || [];
    const current = a.titel
      ? `<div class="section current">
          ${this._statusIcon(device.state)}
          <div class="main">
            <div class="name">${escape(a.titel)}</div>
            <div class="sub">${escape(a.kanal)}${a.mindestalter != null ? ` · ${t.fromAge} ${a.mindestalter}` : ""}</div>
            ${this._reasonLines(a, true)}
            ${a.paedagogik_grund ? `<div class="sub">${t.pedagogyLabel}: ${escape(a.paedagogik_grund)}</div>` : ""}
          </div>
          <div class="markers">${this._markers(a)}</div>
        </div>`
      : "";
    return `<div class="crumb"><button class="link" data-action="back"><ha-icon icon="mdi:arrow-left"></ha-icon>${t.back}</button><span>${escape(this._name(device))}</span></div>
      ${current}
      <div class="section">
        ${this._stepper(ids.age, t.age)}
        ${SETTINGS.map((setting) => this._toggle(ids[setting], t.settings[setting])).join("")}
      </div>
      ${this._lists(a.freigegeben, a.gesperrt, a.player)}
      <div class="section"><h3>${t.history}</h3>${this._historyItems(history, false)}</div>`;
  }

  _historyView(lock) {
    const t = this._t;
    const entries = this._devices(lock)
      .flatMap((device) =>
        (this._state(device.attributes.entitaeten?.history)?.attributes.videos || []).map(
          (entry) => ({ ...entry, geraet: this._name(device) }),
        ),
      )
      .sort((first, second) => second.zeit.localeCompare(first.zeit));
    return `<div class="crumb"><button class="link" data-action="back"><ha-icon icon="mdi:arrow-left"></ha-icon>${t.back}</button><span>${t.history}</span></div>
      <div class="section">${this._historyItems(entries, true)}</div>`;
  }

  _generalView(lock) {
    const t = this._t;
    const ids = lock.attributes.entitaeten || {};
    const health = HEALTH.map((name) => {
      const state = this._state(ids[name])?.state;
      const label = state === "on" ? t.online : state === "off" ? t.offline : t.unknown;
      const color =
        state === "on"
          ? "var(--success-color, #43a047)"
          : state === "off"
            ? "var(--error-color, #db4437)"
            : "var(--secondary-text-color)";
      return `<div class="line"><span>${t.health[name]}</span><span style="color:${color}">${label}</span></div>`;
    }).join("");
    const stats = STATS.map(
      (stat) =>
        `<div class="line"><span>${t.stats[stat]}</span><span>${escape(this._state(ids[stat])?.state ?? 0)}</span></div>`,
    ).join("");
    return `<div class="crumb"><button class="link" data-action="back"><ha-icon icon="mdi:arrow-left"></ha-icon>${t.back}</button><span>${t.general}</span></div>
      <div class="section">
        ${this._toggle(ids.check, t.check)}
        ${this._stepper(ids.age, t.defaultAge)}
      </div>
      ${this._lists(lock.attributes.freigegeben, lock.attributes.gesperrt, null)}
      <div class="section"><h3>${t.today}</h3>${stats}</div>
      <div class="section"><h3>${t.services}</h3>${health}</div>`;
  }

  async _call(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data);
      this._message = "";
      return true;
    } catch (error) {
      this._message = error?.message || String(error);
      return false;
    } finally {
      this._signature = "";
      this._render();
    }
  }

  async _onClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    // Safari keeps the focus in a field after tapping a button, which would
    // block every redraw.
    this.shadowRoot.activeElement?.blur();
    const data = button.dataset;
    const lock = this._lock();
    switch (data.action) {
      case "open":
        this._player = data.player || this._player;
        if (this._isOpen(lock)) this._view = data.target;
        else {
          this._pinTarget = data.target;
          this._pin = "";
        }
        break;
      case "back":
        this._view = "list";
        this._limit = 0;
        break;
      case "more":
        this._limit = Number(data.limit);
        break;
      case "expand":
        if (this._expanded.has(data.key)) this._expanded.delete(data.key);
        else this._expanded.add(data.key);
        break;
      case "dismiss":
        this._message = "";
        break;
      case "pin-digit":
        if (this._pin.length < 8) this._pin += data.digit;
        break;
      case "pin-back":
        this._pin = this._pin.slice(0, -1);
        break;
      case "pin-cancel":
        this._pinTarget = null;
        this._pin = "";
        break;
      case "pin-ok": {
        const target = this._pinTarget;
        const code = this._pin;
        this._pin = "";
        if (await this._call("lock", "unlock", { entity_id: lock.entity_id, code })) {
          this._pinTarget = null;
          this._view = target;
          this._signature = "";
          this._render();
        }
        return;
      }
      case "lock":
        this._view = "list";
        await this._call("lock", "lock", { entity_id: lock.entity_id });
        return;
      case "toggle": {
        const on = this._hass.states[data.entity]?.state === "on";
        await this._call("switch", on ? "turn_off" : "turn_on", { entity_id: data.entity });
        return;
      }
      case "number": {
        const value = Number(data.value);
        if (value < 0 || value > 18) return;
        await this._call("number", "set_value", { entity_id: data.entity, value });
        return;
      }
      case "remove": {
        const payload = { list: data.list, channel: data.channel };
        if (data.player) Object.assign(payload, { player: data.player, only_this_device: true });
        await this._call("parentcontrol", "remove_channel", payload);
        return;
      }
      case "add": {
        const channel = (this._drafts[`channel-${data.scope}`] || "").trim();
        if (!channel) return;
        const allow = data.allow === "1";
        const payload = { channel };
        const age = this._drafts[`age-${data.scope}`];
        if (allow && age !== undefined && age !== "") payload.age = Number(age);
        if (data.player) Object.assign(payload, { player: data.player, only_this_device: true });
        if (await this._call("parentcontrol", allow ? "allow_channel" : "block_channel", payload)) {
          this._drafts[`channel-${data.scope}`] = "";
          this._drafts[`age-${data.scope}`] = "";
          this._signature = "";
          this._render();
        }
        return;
      }
      case "list-channel":
        await this._call("parentcontrol", data.allow === "1" ? "allow_channel" : "block_channel", {
          channel: data.channel,
        });
        return;
      default:
        return;
    }
    this._signature = "";
    this._render();
  }
}

const STYLE = `
  ha-card { padding: 12px 16px 16px; }
  button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; }
  .header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
  .title { font-size: 1.2em; font-weight: 500; }
  .actions { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 4px; padding: 6px 10px; border-radius: 16px;
    background: var(--secondary-background-color); font-size: 0.9em; }
  .chip ha-icon { --mdc-icon-size: 18px; }
  .message { margin-top: 10px; padding: 8px 12px; border-radius: 8px; cursor: pointer;
    background: var(--error-color, #db4437); color: var(--text-primary-color, #fff); }
  .list { margin-top: 8px; }
  .row, .history li, .current { display: flex; align-items: center; gap: 12px; width: 100%;
    padding: 10px 0; border-bottom: 1px solid var(--divider-color); text-align: left; }
  .row:last-child, .history li:last-child { border-bottom: none; }
  .main { flex: 1; min-width: 0; }
  .name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; }
  .sub { color: var(--secondary-text-color); font-size: 0.9em; overflow: hidden; text-overflow: ellipsis; }
  .meta { text-align: right; color: var(--secondary-text-color); font-size: 0.9em; white-space: nowrap; }
  .markers { display: flex; gap: 2px; }
  .marker { --mdc-icon-size: 20px; color: var(--secondary-text-color); }
  .marker.valuable { color: var(--success-color, #43a047); }
  .marker.profanity { color: var(--warning-color, #ffa600); }
  .why, .wrap { white-space: normal; }
  .why { color: var(--error-color, #db4437); }
  .history .main { cursor: pointer; }
  .history .name:not(.wrap), .history .sub:not(.why):not(.wrap) { white-space: nowrap; }
  .more { margin-top: 8px; }
  .crumb { display: flex; align-items: center; gap: 8px; margin: 10px 0 4px; font-weight: 500; }
  .link { display: inline-flex; align-items: center; gap: 4px; color: var(--primary-color); }
  .section { margin-top: 12px; }
  h3 { margin: 12px 0 4px; font-size: 1em; font-weight: 500; }
  ul { list-style: none; margin: 0; padding: 0; }
  .section > ul > li { display: flex; align-items: center; justify-content: space-between;
    padding: 4px 0; border-bottom: 1px solid var(--divider-color); }
  small { color: var(--secondary-text-color); }
  .icon { padding: 6px; border-radius: 50%; color: var(--secondary-text-color); }
  .icon ha-icon { --mdc-icon-size: 20px; }
  .buttons { display: flex; }
  .toggle, .stepper, .line { display: flex; align-items: center; justify-content: space-between;
    width: 100%; padding: 8px 0; text-align: left; }
  .switch { width: 36px; height: 20px; border-radius: 10px; background: var(--disabled-color, #bdbdbd);
    position: relative; flex: none; transition: background 0.2s; }
  .switch span { position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
    background: #fff; transition: left 0.2s; }
  .toggle.on .switch { background: var(--primary-color); }
  .toggle.on .switch span { left: 18px; }
  .stepper > div { display: flex; align-items: center; gap: 8px; }
  .round { width: 32px; height: 32px; border-radius: 50%; background: var(--secondary-background-color);
    display: inline-flex; align-items: center; justify-content: center; }
  .value { min-width: 2ch; text-align: center; font-weight: 500; }
  .add { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  input { flex: 1; min-width: 120px; padding: 6px 10px; border-radius: 8px; font: inherit;
    border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  input.age { flex: 0 0 70px; min-width: 0; }
  .hint, .empty { color: var(--secondary-text-color); padding: 8px 0; }
  .pin { display: flex; flex-direction: column; align-items: center; gap: 8px; padding-top: 12px; }
  .pin-title { font-weight: 500; }
  .dots { font-size: 1.4em; letter-spacing: 6px; min-height: 1.5em; }
  .pad { display: grid; grid-template-columns: repeat(3, 64px); gap: 10px; }
  .key { height: 56px; border-radius: 50%; font-size: 1.3em; background: var(--secondary-background-color);
    display: inline-flex; align-items: center; justify-content: center; }
  .key.ok { background: var(--primary-color); color: var(--text-primary-color, #fff); }
`;

// Visual editor; booleans are only stored when switched off, names only when set.
class ParentControlCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _devices() {
    const lock = findLock(this._hass, this._config);
    return (lock?.attributes.geraete || [])
      .map((id) => this._hass.states[id])
      .filter(Boolean);
  }

  _update() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (event) => this._changed(event.detail.value));
      this.appendChild(this._form);
    }
    const labels = texts(this._hass).editor;
    const devices = this._devices();
    this._form.computeLabel = (schema) => {
      const device = devices[Number(schema.name.replace("name_", ""))];
      return schema.name.startsWith("name_")
        ? `${labels.nameFor} ${device?.attributes.name ?? ""}`
        : labels[schema.name];
    };
    this._form.hass = this._hass;
    this._form.schema = [
      { name: "title", selector: { text: {} } },
      { name: "entity", selector: { entity: { domain: "lock", integration: "parentcontrol" } } },
      ...OPTIONS.map((name) => ({ name, selector: { boolean: {} } })),
      { name: "history_limit", selector: { number: { min: 5, max: 60, step: 5, mode: "box" } } },
      ...devices.map((_, index) => ({ name: `name_${index}`, selector: { text: {} } })),
    ];
    const names = this._config.names || {};
    this._form.data = {
      title: this._config.title || "",
      entity: this._config.entity || "",
      history_limit: this._config.history_limit || 10,
      ...Object.fromEntries(OPTIONS.map((name) => [name, this._config[name] !== false])),
      ...Object.fromEntries(
        devices.map((device, index) => [`name_${index}`, names[device.entity_id] || ""]),
      ),
    };
  }

  _changed(value) {
    const config = { type: this._config.type };
    if (value.title) config.title = value.title;
    if (value.entity) config.entity = value.entity;
    for (const name of OPTIONS) if (value[name] === false) config[name] = false;
    if (value.history_limit && Number(value.history_limit) !== 10)
      config.history_limit = Number(value.history_limit);
    const names = {};
    this._devices().forEach((device, index) => {
      if (value[`name_${index}`]) names[device.entity_id] = value[`name_${index}`];
    });
    if (Object.keys(names).length) config.names = names;
    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }),
    );
  }
}

customElements.define("parentcontrol-card", ParentControlCard);
customElements.define("parentcontrol-card-editor", ParentControlCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "parentcontrol-card",
  name: "ParentControl",
  description: "Devices, PIN, settings and history of ParentControl.",
});
