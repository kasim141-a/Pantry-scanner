// Smart Pantry Card v1.5.1 - Lovelace custom card for the Smart Pantry Scanner integration.
// Views: main (dashboard + suggestions), inventory (browse/edit items), recipes, scan.
// - Auto-discovers Smart Pantry entities (no exact entity id needed).
// - Shopping suggestions for low-stock and expiring items with one-tap add.
// - Scan via mobile camera (ZXing, HTTPS) or BT/USB keyboard-wedge scanner.
// - Syncs additions to Home Assistant's default Shopping List.

const SMART_PANTRY_CARD_VERSION = '1.5.1';

// Category fallback icons used when an item has no product image.
const SP_CATEGORY_ICONS = {
  produce: '\ud83e\udd6c', dairy: '\ud83e\udd5b', meat: '\ud83c\udf57', seafood: '\ud83e\udd90',
  bakery: '\ud83c\udf5e', pantry: '\ud83e\udd6b', frozen: '\ud83e\uddca', beverages: '\ud83e\udd64',
  condiments: '\ud83e\uddc2', snacks: '\ud83c\udf7f', other: '\ud83d\udce6',
};

class SmartPantryCard extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._view = 'main';
    this._recipes = [];
    this._lastScan = null;
    this._cameraActive = false;
    this._codeReader = null;
    this._unsubRecipes = null;
    this._unsubScan = null;
    this._entityBase = null;   // resolved base entity id (total_items sensor)
    this._wedgeBuffer = '';
    this._wedgeTimer = null;
    this._wedgeListener = null;
    this._invSearch = '';      // inventory search text
    this._invCategory = 'all'; // inventory category filter
    this._invLocation = 'all'; // inventory storage-location filter
    this._invEditing = null;   // name of item being edited inline
    this._rapidMode = false;   // external-scanner rapid scan mode
    this._rapidCount = 0;      // scans this rapid session
  }

  static getConfigElement() {
    return document.createElement('smart-pantry-card-editor');
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    // `entity` is now optional — the card auto-discovers Smart Pantry sensors.
    this._config = config || {};
  }

  set hass(hass) {
    this._hass = hass;

    if (this._unsubRecipes === null && hass && hass.connection) {
      try {
        hass.connection
          .subscribeEvents((event) => {
            this._recipes = (event && event.data && event.data.recipes) || [];
            this._view = 'recipes';
            this._renderCard();
          }, 'smart_pantry_recipes_suggested')
          .then((unsub) => { this._unsubRecipes = unsub; })
          .catch((err) => {
            console.error('SmartPantryCard: failed to subscribe to recipes event', err);
          });

        hass.connection
          .subscribeEvents((event) => {
            this._lastScan = (event && event.data) || null;
            this._view = 'scan';
            this._renderCard();
          }, 'smart_pantry_scan_result')
          .then((unsub) => { this._unsubScan = unsub; })
          .catch((err) => {
            console.error('SmartPantryCard: failed to subscribe to scan event', err);
          });

        this._unsubRecipes = this._unsubRecipes || (() => {});
      } catch (err) {
        console.error('SmartPantryCard: event subscription error', err);
      }
    }

    if (this._config) {
      this._renderCard();
    }
  }

  disconnectedCallback() {
    if (typeof this._unsubRecipes === 'function') {
      try { this._unsubRecipes(); } catch (err) { /* already gone */ }
    }
    if (typeof this._unsubScan === 'function') {
      try { this._unsubScan(); } catch (err) { /* already gone */ }
    }
    this._stopCamera();
    this._detachWedgeListener();
  }

  getCardSize() {
    return 6;
  }

  // ---- Entity resolution ---------------------------------------------------

  /**
   * Resolve the "total_items" sensor entity id.
   * Priority: explicit config entity that exists → auto-discovery by suffix
   * across all sensor entities → null.
   */
  _resolveBaseEntity() {
    const hass = this._hass;
    if (!hass) return null;

    const configured = this._config.entity;
    if (configured && hass.states[configured]) {
      // Accept either the total_items sensor directly or any smart pantry
      // sensor from which we can derive the base.
      if (configured.includes('total_items')) return configured;
      const derived = this._deriveSibling(configured, 'total_items');
      if (derived && hass.states[derived]) return derived;
      return configured;
    }

    if (this._entityBase && hass.states[this._entityBase]) {
      return this._entityBase;
    }

    // Auto-discover: any sensor ending in `total_items` whose id contains `pantry`.
    const candidates = Object.keys(hass.states).filter((id) =>
      id.startsWith('sensor.') && id.endsWith('total_items') && id.includes('pantry')
    );
    this._entityBase = candidates.length > 0 ? candidates[0] : null;
    return this._entityBase;
  }

  /** Derive a sibling sensor id by swapping known suffixes. */
  _deriveSibling(entityId, targetSuffix) {
    const suffixes = ['total_items', 'expiring_soon', 'expired_items', 'expired',
      'savings', 'shopping_list', 'shopping_suggestions', 'suggestions',
      'weekly_budget', 'waste_prevented'];
    for (const s of suffixes) {
      if (entityId.endsWith(s)) {
        return entityId.slice(0, entityId.length - s.length) + targetSuffix;
      }
    }
    return null;
  }

  /** Find a sibling entity that actually exists, trying alternative suffixes. */
  _sibling(baseId, targetSuffixes) {
    const hass = this._hass;
    if (!hass || !baseId) return null;
    for (const suffix of targetSuffixes) {
      const id = this._deriveSibling(baseId, suffix);
      if (id && hass.states[id]) return hass.states[id];
    }
    return null;
  }

  // ---- Rendering ----------------------------------------------------------

  _ensureShell() {
    if (this.content) return;
    const card = document.createElement('ha-card');
    card.header = this._config.title || '🥦 Smart Pantry';
    this.content = document.createElement('div');
    this.content.style.padding = '16px';
    card.appendChild(this.content);
    this.appendChild(card);
  }

  _styles() {
    return '<style>' +
      '.sp-container { font-family: var(--ha-card-font-family, "Roboto"); color: var(--primary-text-color); }' +
      '.sp-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 16px; }' +
      '.sp-stat { background: var(--card-background-color, #fff); border-radius: 12px; padding: 12px 8px; text-align: center; border: 1px solid var(--divider-color, #e0e0e0); }' +
      '.sp-stat-value { font-size: 24px; font-weight: 700; color: #2E7D32; }' +
      '.sp-stat-label { font-size: 11px; color: var(--secondary-text-color); margin-top: 4px; }' +
      '.sp-stat.warning .sp-stat-value { color: #FF9800; }' +
      '.sp-stat.danger .sp-stat-value { color: #E53935; }' +
      '.sp-section { margin-bottom: 16px; }' +
      '.sp-section-title { font-size: 14px; font-weight: 700; color: var(--primary-text-color); margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }' +
      '.sp-item-list { display: flex; flex-direction: column; gap: 6px; }' +
      '.sp-item { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; background: var(--card-background-color, #fff); border-radius: 10px; border: 1px solid var(--divider-color, #e0e0e0); font-size: 13px; }' +
      '.sp-item-left { display: flex; align-items: center; gap: 10px; }' +
      '.sp-item-icon { font-size: 20px; }' +
      '.sp-item-avatar { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 20px; background: var(--secondary-background-color, #f0f0f0); flex-shrink: 0; overflow: hidden; }' +
      '.sp-item-avatar img { width: 100%; height: 100%; object-fit: cover; border-radius: 8px; }' +
      '.sp-version { text-align: right; font-size: 10px; color: var(--secondary-text-color); margin-top: 8px; opacity: 0.7; }' +
      '.sp-item-name { font-weight: 600; }' +
      '.sp-item-meta { font-size: 11px; color: var(--secondary-text-color); }' +
      '.sp-badge { padding: 3px 10px; border-radius: 100px; font-size: 11px; font-weight: 700; }' +
      '.sp-badge.green { background: #E8F5E9; color: #2E7D32; }' +
      '.sp-badge.orange { background: #FFF3E0; color: #E65100; }' +
      '.sp-badge.red { background: #FFEBEE; color: #C62828; }' +
      '.sp-progress { width: 100%; height: 6px; background: #e0e0e0; border-radius: 100px; overflow: hidden; margin-top: 6px; }' +
      '.sp-progress-fill { height: 100%; background: #2E7D32; border-radius: 100px; }' +
      '.sp-progress-fill.warning { background: #FF9800; }' +
      '.sp-progress-fill.danger { background: #E53935; }' +
      '.sp-empty { text-align: center; padding: 20px; color: var(--secondary-text-color); font-size: 13px; }' +
      '.sp-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }' +
      '.sp-category-chip { padding: 6px 10px; background: var(--card-background-color, #fff); border-radius: 8px; border: 1px solid var(--divider-color, #e0e0e0); font-size: 12px; display: flex; justify-content: space-between; }' +
      '.sp-btn-row { display: flex; gap: 8px; margin-top: 12px; }' +
      '.sp-btn { flex: 1; padding: 10px; border: none; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; }' +
      '.sp-btn-primary { background: #2E7D32; color: white; }' +
      '.sp-btn-secondary { background: #FF9800; color: white; }' +
      '.sp-btn-ghost { background: var(--card-background-color, #fff); color: var(--primary-text-color); border: 1px solid var(--divider-color, #e0e0e0); }' +
      '.sp-btn-mini { padding: 5px 10px; border: none; border-radius: 8px; font-size: 11px; font-weight: 600; cursor: pointer; background: #2E7D32; color: white; }' +
      '.sp-btn-mini:disabled { opacity: 0.5; cursor: default; }' +
      '.sp-btn-back { background: none; border: none; color: var(--primary-text-color); font-size: 14px; cursor: pointer; padding: 4px 0; margin-bottom: 12px; display: flex; align-items: center; gap: 4px; }' +
      '.sp-recipe-card { border: 1px solid var(--divider-color); border-radius: 12px; padding: 14px; margin-bottom: 10px; }' +
      '.sp-match-bar { height: 8px; border-radius: 100px; margin: 8px 0; }' +
      '.sp-chip { display: inline-block; padding: 3px 8px; border-radius: 100px; font-size: 11px; margin: 2px; }' +
      '.sp-chip.green { background: #E8F5E9; color: #2E7D32; }' +
      '.sp-chip.gray { background: #F5F5F5; color: #757575; }' +
      '.sp-camera-modal { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 9999; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; }' +
      '.sp-input { width: 100%; padding: 10px 14px; border: 1px solid var(--divider-color); border-radius: 10px; font-size: 14px; background: var(--card-background-color); color: var(--primary-text-color); box-sizing: border-box; }' +
      '.sp-warning { padding: 10px 14px; background: #FFF3E0; border-radius: 10px; color: #E65100; font-size: 13px; margin: 8px 0; }' +
      '.sp-suggest { padding: 10px 14px; background: #E3F2FD; border-radius: 10px; color: #1565C0; font-size: 13px; margin: 8px 0; display: flex; align-items: center; justify-content: space-between; gap: 8px; }' +
      '.sp-filter-row { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0; }' +
      '.sp-filter-chip { padding: 5px 10px; border-radius: 100px; font-size: 11px; cursor: pointer; border: 1px solid var(--divider-color, #e0e0e0); background: var(--card-background-color, #fff); color: var(--primary-text-color); }' +
      '.sp-filter-chip.active { background: #2E7D32; color: white; border-color: #2E7D32; }' +
      '.sp-inv-item { padding: 10px 12px; background: var(--card-background-color, #fff); border-radius: 10px; border: 1px solid var(--divider-color, #e0e0e0); border-left: 4px solid #2E7D32; font-size: 13px; margin-bottom: 6px; }' +
      '.sp-inv-item.exp-orange { border-left-color: #FF9800; }' +
      '.sp-inv-item.exp-red { border-left-color: #E53935; }' +
      '.sp-rename-row { display: flex; gap: 8px; margin-top: 8px; }' +
      '.sp-rename-row input { flex: 1; }' +
      '.sp-inv-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }' +
      '.sp-stepper { display: flex; align-items: center; gap: 6px; }' +
      '.sp-step-btn { width: 30px; height: 30px; border: 1px solid var(--divider-color, #e0e0e0); border-radius: 8px; background: var(--card-background-color, #fff); color: var(--primary-text-color); font-size: 16px; font-weight: 700; cursor: pointer; line-height: 1; }' +
      '.sp-step-qty { min-width: 42px; text-align: center; font-weight: 700; font-size: 13px; }' +
      '.sp-edit-form { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--divider-color, #e0e0e0); display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }' +
      '.sp-edit-form label { font-size: 11px; color: var(--secondary-text-color); display: block; margin-bottom: 3px; }' +
      '.sp-edit-full { grid-column: 1 / -1; }' +
      '.sp-select { width: 100%; padding: 8px 10px; border: 1px solid var(--divider-color); border-radius: 8px; font-size: 13px; background: var(--card-background-color); color: var(--primary-text-color); box-sizing: border-box; }' +
      '.sp-btn-danger { background: #E53935; color: white; }' +
      '</style>';
  }

  _renderCard() {
    this._ensureShell();

    const baseId = this._resolveBaseEntity();
    if (!baseId) {
      this.content.innerHTML = this._styles() +
        '<div style="color:#E53935;text-align:center;padding:20px;">' +
        'No Smart Pantry sensors found.<br>' +
        '<span style="font-size:12px;color:var(--secondary-text-color);">' +
        'Make sure the Smart Pantry Scanner integration is set up ' +
        '(Settings → Devices &amp; Services), then reload this page. ' +
        'You can also set <code>entity:</code> to your ' +
        '<code>…_total_items</code> sensor explicitly.</span></div>';
      return;
    }

    if (this._view === 'recipes') { this._renderRecipes(); return; }
    if (this._view === 'scan') { this._renderScan(); return; }
    this._detachWedgeListener();
    if (this._view === 'inventory') { this._renderInventory(baseId); return; }
    this._renderMain(baseId);
  }

  // ---- Main view ----------------------------------------------------------

  _renderMain(baseId) {
    const hass = this._hass;

    const totalItems = hass.states[baseId];
    const expiringSoon = this._sibling(baseId, ['expiring_soon']);
    const savings = this._sibling(baseId, ['savings']);
    const shoppingList = this._sibling(baseId, ['shopping_list']);
    const weeklyBudget = this._sibling(baseId, ['weekly_budget']);
    const suggestions = this._sibling(baseId, ['shopping_suggestions', 'suggestions']);

    const expiringItems = (expiringSoon && expiringSoon.attributes && expiringSoon.attributes.items) || [];
    const shoppingItems = (shoppingList && shoppingList.attributes && shoppingList.attributes.items) || [];
    const pantryCategories = (totalItems && totalItems.attributes && totalItems.attributes.categories) || {};
    const lowStockItems = (totalItems && totalItems.attributes && totalItems.attributes.low_stock_items) || [];
    const suggestionItems = (suggestions && suggestions.attributes && suggestions.attributes.suggestions) || [];

    let html = this._styles() + '<div class="sp-container">';

    // Stats
    const budgetPct = parseInt((weeklyBudget && weeklyBudget.state) || 0, 10) || 0;
    html += '<div class="sp-stats">' +
      '<div class="sp-stat"><div class="sp-stat-value">' + this._escape((totalItems && totalItems.state) || '0') + '</div><div class="sp-stat-label">Items</div></div>' +
      '<div class="sp-stat ' + (parseInt((expiringSoon && expiringSoon.state) || 0, 10) > 0 ? 'warning' : '') + '"><div class="sp-stat-value">' + this._escape((expiringSoon && expiringSoon.state) || '0') + '</div><div class="sp-stat-label">Expiring</div></div>' +
      '<div class="sp-stat"><div class="sp-stat-value">' + this._escape((savings && savings.state) || '0') + this._escape((savings && savings.attributes && savings.attributes.unit_of_measurement) || '') + '</div><div class="sp-stat-label">Saved</div></div>' +
      '<div class="sp-stat ' + (budgetPct > 80 ? 'danger' : '') + '"><div class="sp-stat-value">' + this._escape((weeklyBudget && weeklyBudget.state) || '0') + '%</div><div class="sp-stat-label">Budget</div></div>' +
      '</div>';

    // Budget bar
    html += '<div class="sp-section"><div class="sp-section-title">💰 Weekly Budget</div>' +
      '<div style="font-size:12px;color:var(--secondary-text-color);margin-bottom:4px;">' +
      this._escape((weeklyBudget && weeklyBudget.attributes && weeklyBudget.attributes.estimated_spent) || '0') + ' / ' +
      this._escape((weeklyBudget && weeklyBudget.attributes && weeklyBudget.attributes.weekly_budget) || '120') + ' ' +
      this._escape((weeklyBudget && weeklyBudget.attributes && weeklyBudget.attributes.currency) || 'USD') + '</div>' +
      '<div class="sp-progress"><div class="sp-progress-fill ' + (budgetPct > 80 ? 'danger' : budgetPct > 60 ? 'warning' : '') + '" style="width:' + budgetPct + '%"></div></div></div>';

    // Shopping suggestions (low stock + expiring, deduped by backend)
    html += '<div class="sp-section"><div class="sp-section-title">💡 Suggested for Shopping List';
    if (suggestionItems.length > 0) {
      html += ' <span class="sp-badge orange">' + suggestionItems.length + '</span>';
    }
    html += '</div>';
    if (suggestionItems.length === 0) {
      html += '<div class="sp-empty">Nothing to suggest — pantry looks good ✅</div>';
    } else {
      html += '<div class="sp-item-list">';
      suggestionItems.slice(0, 8).forEach((item, idx) => {
        html += '<div class="sp-item"><div class="sp-item-left">' + this._itemIcon(item) + '<div>' +
          '<div class="sp-item-name">' + this._escape(item.name) + '</div>' +
          '<div class="sp-item-meta">' + this._escape(item.detail || item.reason || '') + '</div>' +
          '</div></div>' +
          '<button class="sp-btn-mini" data-suggest="' + idx + '">🛒 Add</button></div>';
      });
      html += '</div>';
      html += '<button class="sp-btn sp-btn-primary" id="btn-add-all-suggestions" style="margin-top:8px;width:100%;">🛒 Add all to Shopping List</button>';
    }
    html += '</div>';

    // Expiring detail list
    html += '<div class="sp-section"><div class="sp-section-title">⏰ Expiring Soon</div>';
    if (expiringItems.length === 0) {
      html += '<div class="sp-empty">No items expiring soon 🎉</div>';
    } else {
      html += '<div class="sp-item-list">';
      expiringItems.slice(0, 5).forEach((item, idx) => {
        const days = item.days_until_expiry;
        const badgeClass = days <= 1 ? 'red' : days <= 3 ? 'orange' : 'green';
        const badgeText = days < 0 ? 'Expired' : days === 0 ? 'Today' : days === 1 ? '1 day' : days + ' days';
        html += '<div class="sp-item"><div class="sp-item-left">' + this._itemIcon(item) + '<div>' +
          '<div class="sp-item-name">' + this._escape(item.name) + '</div>' +
          '<div class="sp-item-meta">' + this._escape(item.quantity) + ' ' + this._escape(item.unit || '') + ' • ' + this._escape(item.storage_location || '') + '</div>' +
          '</div></div>' +
          '<div style="display:flex;align-items:center;gap:8px;">' +
          '<span class="sp-badge ' + badgeClass + '">' + this._escape(badgeText) + '</span>' +
          '<button class="sp-btn-mini" data-expiring="' + idx + '">Add to list</button>' +
          '</div></div>';
      });
      html += '</div>';
    }
    html += '</div>';

    // Categories
    const catEntries = Object.entries(pantryCategories);
    if (catEntries.length > 0) {
      html += '<div class="sp-section"><div class="sp-section-title">📦 Categories</div><div class="sp-grid-2">';
      catEntries.forEach(([cat, count]) => {
        html += '<div class="sp-category-chip"><span>' + this._escape(cat) + '</span><strong>' + this._escape(count) + '</strong></div>';
      });
      html += '</div></div>';
    }

    // Shopping list
    html += '<div class="sp-section"><div class="sp-section-title">🛒 Shopping List (' + shoppingItems.length + ')</div>';
    if (shoppingItems.length === 0) {
      html += '<div class="sp-empty">Your shopping list is empty</div>';
    } else {
      html += '<div class="sp-item-list">';
      shoppingItems.slice(0, 5).forEach((item) => {
        html += '<div class="sp-item"><div class="sp-item-left">' + this._itemIcon(item) + '<div>' +
          '<div class="sp-item-name">' + this._escape(item.name) + '</div>' +
          (item.notes ? '<div class="sp-item-meta">' + this._escape(item.notes) + '</div>' : '') +
          '</div></div><span class="sp-badge green">' + this._escape(item.quantity) + ' ' + this._escape(item.unit || '') + '</span></div>';
      });
      html += '</div>';
    }
    html += '</div>';

    // Inventory value line (only when at least one item has a price)
    const invValue = (totalItems && totalItems.attributes && totalItems.attributes.inventory_value) || 0;
    const invCurrency = (totalItems && totalItems.attributes && totalItems.attributes.currency) || '';
    if (invValue > 0) {
      html += '<div class="sp-section" style="font-size:12px;color:var(--secondary-text-color);">' +
        '💵 Stock value: <strong>' + this._escape(invValue) + ' ' + this._escape(invCurrency) + '</strong></div>';
    }

    // Action buttons
    html += '<div class="sp-btn-row">' +
      '<button class="sp-btn sp-btn-ghost" id="btn-inventory">📦 Inventory</button>' +
      '<button class="sp-btn sp-btn-primary" id="btn-recipes">🍳 Recipes</button>' +
      '<button class="sp-btn sp-btn-secondary" id="btn-scan">📷 Scan</button>' +
      '<button class="sp-btn sp-btn-ghost" id="btn-clear">🗑️ Clear</button>' +
      '</div>';

    // Version footer — makes stale browser caches visible at a glance.
    html += '<div class="sp-version">Smart Pantry Card v' + SMART_PANTRY_CARD_VERSION + '</div>';

    html += '</div>';
    this.content.innerHTML = html;

    const inventoryBtn = this.content.querySelector('#btn-inventory');
    if (inventoryBtn) {
      inventoryBtn.onclick = () => {
        this._view = 'inventory';
        this._invEditing = null;
        this._renderCard();
      };
    }

    const recipesBtn = this.content.querySelector('#btn-recipes');
    if (recipesBtn) {
      recipesBtn.onclick = () => {
        this._view = 'recipes';
        hass.callService('smart_pantry', 'get_recipes', { recipe_count: 8 });
        this._renderCard();
      };
    }

    const scanBtn = this.content.querySelector('#btn-scan');
    if (scanBtn) {
      scanBtn.onclick = () => {
        this._view = 'scan';
        this._renderCard();
      };
    }

    const clearBtn = this.content.querySelector('#btn-clear');
    if (clearBtn) {
      clearBtn.onclick = () => {
        hass.callService('smart_pantry', 'clear_shopping_list', {});
      };
    }

    // Individual suggestion add buttons.
    this.content.querySelectorAll('[data-suggest]').forEach((btn) => {
      btn.onclick = () => {
        const item = suggestionItems[parseInt(btn.getAttribute('data-suggest'), 10)];
        if (item) {
          this._addToLists(item.name, 1, item.unit || 'piece');
          btn.textContent = '✓ Added';
          btn.disabled = true;
        }
      };
    });

    // Add all suggestions via the backend service (also syncs to HA list).
    const addAllBtn = this.content.querySelector('#btn-add-all-suggestions');
    if (addAllBtn) {
      addAllBtn.onclick = () => {
        hass.callService('smart_pantry', 'sync_suggestions_to_shopping_list', {});
        addAllBtn.textContent = '✓ All added to Shopping List';
        addAllBtn.disabled = true;
      };
    }

    // Expiring add-to-list buttons.
    this.content.querySelectorAll('[data-expiring]').forEach((btn) => {
      btn.onclick = () => {
        const item = expiringItems[parseInt(btn.getAttribute('data-expiring'), 10)];
        if (item) {
          this._addToLists(item.name, 1, item.unit || 'piece');
          btn.textContent = '✓ Added';
          btn.disabled = true;
        }
      };
    });
  }

  // ---- Inventory view -------------------------------------------------------

  _catIcons() {
    return SP_CATEGORY_ICONS;
  }

  _categories() {
    return ['produce', 'dairy', 'meat', 'seafood', 'bakery', 'pantry', 'frozen', 'beverages', 'condiments', 'snacks', 'other'];
  }

  _units() {
    return ['piece', 'g', 'kg', 'oz', 'lb', 'ml', 'l', 'cup', 'tbsp', 'tsp', 'bottle', 'can', 'box', 'bag', 'pack'];
  }

  _locations() {
    return ['pantry', 'refrigerator', 'freezer', 'countertop', 'wine_cellar', 'other'];
  }

  _renderInventory(baseId) {
    const hass = this._hass;
    const totalItems = hass.states[baseId];
    const attrs = (totalItems && totalItems.attributes) || {};
    const inventory = attrs.inventory || [];
    const currency = attrs.currency || '';
    const icons = this._catIcons();

    // Filter by search text, category, and storage location.
    const search = (this._invSearch || '').toLowerCase();
    const filtered = inventory.filter((item) => {
      if (this._invCategory !== 'all' && (item.category || 'other') !== this._invCategory) return false;
      if (this._invLocation !== 'all' && (item.storage_location || 'pantry') !== this._invLocation) return false;
      if (search && !(item.name || '').toLowerCase().includes(search)) return false;
      return true;
    });

    // Category chips: 'all' plus only categories present in inventory.
    const presentCats = Array.from(new Set(inventory.map((i) => i.category || 'other')));
    // Location chips: 'all' plus only locations present in inventory.
    const presentLocs = Array.from(new Set(inventory.map((i) => i.storage_location || 'pantry')));

    let html = this._styles() + '<div class="sp-container">';
    html += '<button class="sp-btn-back" id="sp-back">← Back</button>';
    html += '<div class="sp-section-title">📦 Inventory (' + inventory.length + ' items' +
      (attrs.inventory_value > 0 ? ' • ' + this._escape(attrs.inventory_value) + ' ' + this._escape(currency) : '') + ')</div>';

    html += '<input type="text" id="sp-inv-search" class="sp-input" placeholder="🔍 Search items…" value="' + this._escape(this._invSearch) + '">';

    html += '<div class="sp-filter-row">';
    html += '<span class="sp-filter-chip ' + (this._invCategory === 'all' ? 'active' : '') + '" data-cat="all">All</span>';
    presentCats.forEach((cat) => {
      html += '<span class="sp-filter-chip ' + (this._invCategory === cat ? 'active' : '') + '" data-cat="' + this._escape(cat) + '">' +
        (icons[cat] || '📦') + ' ' + this._escape(cat) + '</span>';
    });
    html += '</div>';

    // Storage-location filter chips (fridge/freezer/pantry… like NoWaste lists).
    if (presentLocs.length > 1) {
      const locIcons = { pantry: '🚪', refrigerator: '🧊', freezer: '❄️', countertop: '🍽️', wine_cellar: '🍷', other: '📍' };
      html += '<div class="sp-filter-row">';
      html += '<span class="sp-filter-chip ' + (this._invLocation === 'all' ? 'active' : '') + '" data-loc="all">All locations</span>';
      presentLocs.forEach((loc) => {
        html += '<span class="sp-filter-chip ' + (this._invLocation === loc ? 'active' : '') + '" data-loc="' + this._escape(loc) + '">' +
          (locIcons[loc] || '📍') + ' ' + this._escape(loc.replace('_', ' ')) + '</span>';
      });
      html += '</div>';
    }

    if (inventory.length === 0) {
      html += '<div class="sp-empty">Your pantry is empty — scan or add items to get started.<br>' +
        '<span style="font-size:11px;">(If you recently updated, restart Home Assistant so the integration exposes the new inventory attribute.)</span></div>';
    } else if (filtered.length === 0) {
      html += '<div class="sp-empty">No items match your filter.</div>';
    }

    filtered.forEach((item, idx) => {
      const days = item.days_until_expiry;
      let expiryBadge = '';
      if (days != null) {
        const badgeClass = days < 0 ? 'red' : days <= 3 ? 'orange' : 'green';
        const badgeText = days < 0 ? 'Expired' : days === 0 ? 'Today' : days + 'd';
        expiryBadge = '<span class="sp-badge ' + badgeClass + '">' + this._escape(badgeText) + '</span>';
      }
      const priceText = item.price != null ? this._escape(Number(item.price).toFixed(2)) + ' ' + this._escape(currency) : '';
      const isEditing = this._invEditing === item.name;

      // Traffic-light left border (smartpantry.ch style): red = use now,
      // orange = expiring soon, green = fine.
      let expClass = '';
      if (days != null) expClass = days <= 1 ? ' exp-red' : days <= 3 ? ' exp-orange' : '';

      html += '<div class="sp-inv-item' + expClass + '">';
      html += '<div class="sp-inv-row">' +
        '<div class="sp-item-left">' + this._itemIcon(item) + '<div>' +
        '<div class="sp-item-name">' + this._escape(item.name) + '</div>' +
        '<div class="sp-item-meta">' + this._escape(item.category || 'other') + ' • ' + this._escape(item.storage_location || 'pantry') +
        (priceText ? ' • ' + priceText : '') +
        (item.expiration_date ? ' • exp ' + this._escape(item.expiration_date) : '') +
        '</div></div></div>' +
        '<div style="display:flex;align-items:center;gap:8px;">' + expiryBadge +
        '<div class="sp-stepper">' +
        '<button class="sp-step-btn" data-dec="' + idx + '">−</button>' +
        '<span class="sp-step-qty">' + this._escape(item.quantity) + '<br><span style="font-weight:400;font-size:10px;color:var(--secondary-text-color);">' + this._escape(item.unit || '') + '</span></span>' +
        '<button class="sp-step-btn" data-inc="' + idx + '">+</button>' +
        '</div>' +
        '<button class="sp-btn-mini" data-edit="' + idx + '" style="background:var(--card-background-color,#fff);color:var(--primary-text-color);border:1px solid var(--divider-color,#e0e0e0);">' + (isEditing ? '✕' : '✏️') + '</button>' +
        '</div></div>';

      if (isEditing) {
        html += '<div class="sp-edit-form">';
        html += '<div class="sp-edit-full"><label>Name</label><input type="text" class="sp-select" data-f="item_new_name" value="' + this._escape(item.name) + '"></div>';
        html += '<div><label>Quantity</label><input type="number" step="0.1" min="0" class="sp-select" data-f="quantity" value="' + this._escape(item.quantity) + '"></div>';
        html += '<div><label>Unit</label><select class="sp-select" data-f="unit">' +
          this._units().map((u) => '<option value="' + u + '"' + (u === item.unit ? ' selected' : '') + '>' + u + '</option>').join('') + '</select></div>';
        html += '<div><label>Category</label><select class="sp-select" data-f="category">' +
          this._categories().map((c) => '<option value="' + c + '"' + (c === item.category ? ' selected' : '') + '>' + c + '</option>').join('') + '</select></div>';
        html += '<div><label>Location</label><select class="sp-select" data-f="storage_location">' +
          this._locations().map((l) => '<option value="' + l + '"' + (l === item.storage_location ? ' selected' : '') + '>' + l + '</option>').join('') + '</select></div>';
        html += '<div><label>Price (' + this._escape(currency || 'per unit') + ')</label><input type="number" step="0.01" min="0" class="sp-select" data-f="price" value="' + (item.price != null ? this._escape(item.price) : '') + '" placeholder="—"></div>';
        html += '<div><label>Expiry date</label><input type="date" class="sp-select" data-f="expiration_date" value="' + this._escape(item.expiration_date || '') + '"></div>';
        html += '<div class="sp-edit-full" style="display:flex;gap:8px;">' +
          '<button class="sp-btn sp-btn-primary" data-save="' + idx + '" style="flex:2;">💾 Save</button>' +
          '<button class="sp-btn sp-btn-ghost" data-consume="' + idx + '" style="flex:1;">🍽️ Use 1</button>' +
          '<button class="sp-btn sp-btn-danger" data-delete="' + idx + '" style="flex:1;">🗑️</button>' +
          '</div>';
        html += '</div>';
      }
      html += '</div>';
    });

    html += '</div>';
    this.content.innerHTML = html;
    this._wireBack();

    // Search box (debounced re-render, keep focus).
    const searchEl = this.content.querySelector('#sp-inv-search');
    if (searchEl) {
      searchEl.oninput = () => {
        this._invSearch = searchEl.value;
        clearTimeout(this._invSearchTimer);
        this._invSearchTimer = setTimeout(() => {
          const pos = searchEl.selectionStart;
          this._renderCard();
          const el = this.content.querySelector('#sp-inv-search');
          if (el) { el.focus(); try { el.setSelectionRange(pos, pos); } catch (e) { /* ok */ } }
        }, 250);
      };
    }

    // Category chips.
    this.content.querySelectorAll('[data-cat]').forEach((chip) => {
      chip.onclick = () => {
        this._invCategory = chip.getAttribute('data-cat');
        this._renderCard();
      };
    });

    // Location chips.
    this.content.querySelectorAll('[data-loc]').forEach((chip) => {
      chip.onclick = () => {
        this._invLocation = chip.getAttribute('data-loc');
        this._renderCard();
      };
    });

    // Quantity steppers.
    this.content.querySelectorAll('[data-inc]').forEach((btn) => {
      btn.onclick = () => {
        const item = filtered[parseInt(btn.getAttribute('data-inc'), 10)];
        if (item) hass.callService('smart_pantry', 'update_item', { item_name: item.name, quantity: Math.round((Number(item.quantity) + 1) * 10) / 10 });
      };
    });
    this.content.querySelectorAll('[data-dec]').forEach((btn) => {
      btn.onclick = () => {
        const item = filtered[parseInt(btn.getAttribute('data-dec'), 10)];
        if (!item) return;
        const next = Math.round((Number(item.quantity) - 1) * 10) / 10;
        if (next <= 0 && !window.confirm('Remove "' + item.name + '" from the pantry?')) return;
        hass.callService('smart_pantry', 'update_item', { item_name: item.name, quantity: Math.max(0, next) });
      };
    });

    // Edit toggles.
    this.content.querySelectorAll('[data-edit]').forEach((btn) => {
      btn.onclick = () => {
        const item = filtered[parseInt(btn.getAttribute('data-edit'), 10)];
        if (!item) return;
        this._invEditing = this._invEditing === item.name ? null : item.name;
        this._renderCard();
      };
    });

    // Save edited fields.
    this.content.querySelectorAll('[data-save]').forEach((btn) => {
      btn.onclick = () => {
        const item = filtered[parseInt(btn.getAttribute('data-save'), 10)];
        if (!item) return;
        const form = btn.closest('.sp-edit-form');
        const payload = { item_name: item.name };
        let newName = null;
        form.querySelectorAll('[data-f]').forEach((f) => {
          const field = f.getAttribute('data-f');
          const val = f.value;
          if (val === '' || val == null) return;
          if (field === 'item_new_name') { newName = val.trim(); return; }
          if (field === 'quantity' || field === 'price') payload[field] = Number(val);
          else payload[field] = val;
        });
        const finish = () => {
          hass.callService('smart_pantry', 'update_item', payload);
          this._invEditing = null;
          this._renderCard();
        };
        if (newName && newName !== item.name) {
          // Rename first (also teaches the barcode library), then apply edits.
          hass.callService('smart_pantry', 'rename_item', { old_name: item.name, new_name: newName })
            .then(() => { payload.item_name = newName; finish(); })
            .catch(() => finish());
        } else {
          finish();
        }
      };
    });

    // Consume one.
    this.content.querySelectorAll('[data-consume]').forEach((btn) => {
      btn.onclick = () => {
        const item = filtered[parseInt(btn.getAttribute('data-consume'), 10)];
        if (item) hass.callService('smart_pantry', 'mark_consumed', { item_name: item.name, quantity: 1 });
        this._invEditing = null;
      };
    });

    // Delete item.
    this.content.querySelectorAll('[data-delete]').forEach((btn) => {
      btn.onclick = () => {
        const item = filtered[parseInt(btn.getAttribute('data-delete'), 10)];
        if (!item) return;
        if (!window.confirm('Delete "' + item.name + '" from the pantry?')) return;
        hass.callService('smart_pantry', 'remove_item', { item_name: item.name });
        this._invEditing = null;
      };
    });
  }

  // ---- Recipes view -------------------------------------------------------

  _renderRecipes() {
    const hass = this._hass;
    let html = this._styles() + '<div class="sp-container">';
    html += '<button class="sp-btn-back" id="sp-back">← Back</button>';
    html += '<div class="sp-section-title">🍳 Recipes from Your Pantry</div>';

    if (!this._recipes || this._recipes.length === 0) {
      html += '<div class="sp-empty">⏳ Finding recipes from your pantry…</div>';
      html += '</div>';
      this.content.innerHTML = html;
      this._wireBack();
      hass.callService('smart_pantry', 'get_recipes', { recipe_count: 8 });
      return;
    }

    this._recipes.slice(0, 8).forEach((recipe, idx) => {
      const matched = recipe.matched_ingredients || recipe.matching_ingredients || [];
      const missing = recipe.missing_ingredients || [];
      const total = matched.length + missing.length;
      const rawPct = typeof recipe.match_percent === 'number'
        ? recipe.match_percent
        : (total > 0 ? Math.round((matched.length / total) * 100) : 0);
      const pct = Math.max(0, Math.min(100, rawPct));
      const barColor = pct > 70 ? '#2E7D32' : pct > 40 ? '#FF9800' : '#E53935';
      const cookTime = recipe.cook_time || recipe.cooking_time || recipe.time;

      html += '<div class="sp-recipe-card">';
      html += '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">' +
        '<div class="sp-item-name" style="font-size:15px;">' + this._escape(recipe.name || 'Recipe') + '</div>' +
        (cookTime ? '<span class="sp-badge orange">⏱ ' + this._escape(cookTime) + '</span>' : '') +
        '</div>';

      if (recipe.uses_expiring && recipe.uses_expiring.length > 0) {
        html += '<div style="margin-top:4px;"><span class="sp-badge orange">⏰ Use it up: ' +
          this._escape(recipe.uses_expiring.join(', ')) + '</span></div>';
      }
      html += '<div style="font-size:12px;color:var(--secondary-text-color);margin-top:4px;">' + pct + '% match — you have ' + matched.length + ' of ' + (recipe.total_ingredients || total) + ' ingredients</div>';
      html += '<div class="sp-match-bar" style="background:' + barColor + ';width:' + pct + '%;"></div>';

      if (matched.length > 0) {
        html += '<div style="margin-top:6px;">';
        matched.forEach((ing) => {
          html += '<span class="sp-chip green">✓ ' + this._escape(this._ingredientName(ing)) + '</span>';
        });
        html += '</div>';
      }

      if (missing.length > 0) {
        html += '<div style="margin-top:4px;">';
        missing.forEach((ing) => {
          html += '<span class="sp-chip gray">' + this._escape(this._ingredientName(ing)) + '</span>';
        });
        html += '</div>';
        html += '<button class="sp-btn-mini" style="margin-top:10px;" data-recipe-missing="' + idx + '">🛒 Add ' + missing.length + ' missing to list</button>';
        html += '<span class="sp-added-marker" data-added-marker="' + idx + '" style="display:none;font-size:12px;color:#2E7D32;margin-left:8px;">✓ Added!</span>';
      } else {
        html += '<div style="margin-top:8px;font-size:12px;color:#2E7D32;font-weight:600;">🎉 You have everything — cook it now!</div>';
        html += '<button class="sp-btn-mini" style="margin-top:6px;" data-recipe-cook="' + idx + '">👨‍🍳 Mark cooked (consume)</button>';
      }

      html += '</div>';
    });

    html += '</div>';
    this.content.innerHTML = html;

    this._wireBack();

    this.content.querySelectorAll('[data-recipe-missing]').forEach((btn) => {
      btn.onclick = () => {
        const idx = parseInt(btn.getAttribute('data-recipe-missing'), 10);
        const recipe = this._recipes[idx];
        if (!recipe) return;
        // Use the dedicated backend service so both lists stay in sync.
        hass.callService('smart_pantry', 'add_recipe_missing_to_shopping_list', {
          recipe_name: recipe.name,
        });
        const marker = this.content.querySelector('[data-added-marker="' + idx + '"]');
        if (marker) marker.style.display = 'inline';
        btn.disabled = true;
      };
    });

    this.content.querySelectorAll('[data-recipe-cook]').forEach((btn) => {
      btn.onclick = () => {
        const idx = parseInt(btn.getAttribute('data-recipe-cook'), 10);
        const recipe = this._recipes[idx];
        if (!recipe) return;
        const matched = recipe.matched_ingredients || [];
        matched.forEach((ing) => {
          hass.callService('smart_pantry', 'mark_consumed', {
            item_name: this._ingredientName(ing), quantity: 1,
          });
        });
        btn.textContent = '✓ Enjoy your meal!';
        btn.disabled = true;
      };
    });
  }

  // ---- Scan view ----------------------------------------------------------

  _renderScan() {
    const hass = this._hass;
    let html = this._styles() + '<div class="sp-container">';
    html += '<button class="sp-btn-back" id="sp-back">← Back</button>';
    html += '<div class="sp-section-title">📷 Scan Barcode</div>';

    // Scanner / manual entry
    html += '<div class="sp-section">' +
      '<div class="sp-section-title">🔌 Scanner / Manual Entry</div>' +
      '<div style="font-size:12px;color:var(--secondary-text-color);margin-bottom:6px;">' +
      'Bluetooth/USB scanners work like keyboards — just scan while this view is open. ' +
      'You can also type a barcode manually:</div>' +
      '<input type="text" id="sp-barcode-input" class="sp-input" placeholder="Scan with BT/USB or type here…" autofocus>' +
      '<label style="display:flex;align-items:center;gap:6px;font-size:12px;margin-top:8px;cursor:pointer;">' +
      '<input type="checkbox" id="sp-rapid-mode"' + (this._rapidMode ? ' checked' : '') + '> ⚡ Rapid scan mode (external scanner: auto-add each scan' +
      (this._rapidMode && this._rapidCount > 0 ? ' — <b>' + this._rapidCount + ' scanned</b>' : '') + ')</label>' +
      '<div style="display:flex;gap:8px;margin-top:8px;">' +
      '<div style="flex:1;"><label style="font-size:11px;color:var(--secondary-text-color);">Quantity</label>' +
      '<input type="number" id="sp-scan-qty" class="sp-input" min="1" step="1" value="1"></div>' +
      '<div style="flex:1;"><label style="font-size:11px;color:var(--secondary-text-color);">Price (optional)</label>' +
      '<input type="number" id="sp-scan-price" class="sp-input" min="0" step="0.01" placeholder="—"></div>' +
      '</div>' +
      '<button class="sp-btn sp-btn-primary" id="sp-barcode-submit" style="margin-top:10px;">Submit</button>' +
      '</div>';

    // Camera section
    html += '<div class="sp-section"><div class="sp-section-title">📱 Mobile Camera</div>';
    const canUseCamera = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    const isSecure = (location.protocol === 'https:' || location.hostname === 'localhost');
    if (canUseCamera && isSecure) {
      html += '<button class="sp-btn sp-btn-secondary" id="sp-use-camera">📷 Live Scan</button>';
    } else if (!isSecure) {
      html += '<div class="sp-warning">⚠️ Live camera scanning needs an <b>https://</b> connection (yours is ' + this._escape(location.protocol + '//' + location.hostname) + '). Switch the Companion App server URL to your HTTPS/Nabu Casa address to enable it — or use 📸 Take Photo below, which works on any connection.</div>';
    } else {
      html += '<div class="sp-warning">⚠️ This app/browser does not expose the live camera API. Use 📸 Take Photo below — it opens your phone\'s native camera instead and works everywhere.</div>';
    }
    // Photo-capture fallback: uses the native camera app via a file input,
    // works in every WebView/browser regardless of protocol or mediaDevices.
    html += '<button class="sp-btn sp-btn-secondary" id="sp-photo-scan" style="margin-top:8px;">📸 Take Photo of Barcode</button>' +
      '<input type="file" id="sp-photo-input" accept="image/*" capture="environment" style="display:none;">' +
      '<div id="sp-photo-status" style="font-size:12px;color:var(--secondary-text-color);margin-top:6px;"></div>';
    html += '</div>';

    // Last scan result
    if (this._lastScan && this._lastScan.error === 'empty_barcode') {
      html += '<div class="sp-section"><div class="sp-warning">⚠️ Empty barcode ignored — please scan or type a valid barcode.</div></div>';
    } else if (this._lastScan) {
      const s = this._lastScan;
      const suggest = s.suggest_shopping_list === true || s.low_stock === true || s.expiring === true;
      const isUnknown = s.lookup_failed === true ||
        ((s.item_name || '').toLowerCase().indexOf('unknown item') === 0);
      html += '<div class="sp-section"><div class="sp-section-title">✅ Last Scan</div>' +
        '<div class="sp-recipe-card">' +
        '<div style="display:flex;align-items:center;gap:10px;">' + this._itemIcon(s) +
        '<div class="sp-item-name" style="font-size:15px;">' + this._escape(s.item_name || s.name || 'Unknown item') + '</div></div>' +
        '<div class="sp-item-meta" style="margin-top:4px;">' +
        'Qty: ' + this._escape(s.quantity != null ? s.quantity : '—') + ' ' + this._escape(s.unit || '') +
        (s.expiration_date ? ' • Expires: ' + this._escape(s.expiration_date) : '') +
        (s.source === 'openfoodfacts' ? ' • via Open Food Facts' : '') +
        (s.source === 'library' ? ' • from your Product Library' : '') +
        '</div>';
      if (isUnknown) {
        // The barcode was not found anywhere: let the user name it right here.
        // The name is learned, so the next scan of this barcode resolves instantly.
        html += '<div class="sp-rename-row">' +
          '<input type="text" id="sp-rename-input" class="sp-input" placeholder="What is this product? e.g. Basmati Rice 1kg">' +
          '<button class="sp-btn-mini" id="sp-rename-save">💾 Save name</button>' +
          '</div>' +
          '<div style="font-size:11px;color:var(--secondary-text-color);margin-top:4px;">' +
          'Not found in any database. Name it once — it\'s remembered, and the next scan of barcode ' +
          this._escape(s.barcode || '') + ' will recognise it automatically.</div>';
      }
      if (s.auto_added === true) {
        html += '<div class="sp-suggest" style="margin-top:8px;"><span>🛒 Automatically added to your Shopping List</span></div>';
      } else if (suggest) {
        const reason = s.expiring ? 'expiring soon' : 'low in stock';
        html += '<div class="sp-suggest" style="margin-top:8px;">' +
          '<span>⚠️ This item is ' + reason + '. Add to Shopping List?</span>' +
          '<button class="sp-btn-mini" id="sp-scan-add">🛒 Add</button>' +
          '</div>';
      }
      html += '</div></div>';
    }

    html += '</div>';
    this.content.innerHTML = html;

    this._wireBack();

    const input = this.content.querySelector('#sp-barcode-input');
    const submit = this.content.querySelector('#sp-barcode-submit');

    const submitBarcode = () => {
      if (!input) return;
      const value = input.value.trim();
      // Guard: never submit an empty barcode (was the "Unknown Item ()" bug).
      if (value.length === 0) return;
      if (this._rapidMode) this._rapidCount += 1;
      hass.callService('smart_pantry', 'scan_barcode', this._scanPayload(value));
      input.value = '';
    };

    const rapidToggle = this.content.querySelector('#sp-rapid-mode');
    if (rapidToggle) {
      rapidToggle.onchange = () => {
        this._rapidMode = rapidToggle.checked;
        if (!this._rapidMode) this._rapidCount = 0;
        this._renderCard();
      };
    }

    if (submit) submit.onclick = submitBarcode;
    if (input) {
      input.onkeydown = (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          submitBarcode();
        }
      };
      setTimeout(() => { try { input.focus(); } catch (err) { /* not focusable yet */ } }, 0);
    }

    // Global keyboard-wedge capture: BT/USB scanners type very fast and end
    // with Enter. Capture even when the input is not focused.
    this._attachWedgeListener(input);

    const useCamera = this.content.querySelector('#sp-use-camera');
    if (useCamera) {
      useCamera.onclick = () => { this._openCamera(); };
    }

    // Photo-capture fallback wiring.
    const photoBtn = this.content.querySelector('#sp-photo-scan');
    const photoInput = this.content.querySelector('#sp-photo-input');
    if (photoBtn && photoInput) {
      photoBtn.onclick = () => { photoInput.click(); };
      photoInput.onchange = () => {
        const f = photoInput.files && photoInput.files[0];
        if (f) this._decodePhoto(f);
        photoInput.value = '';
      };
    }

    // Rename flow for unknown items.
    const renameSave = this.content.querySelector('#sp-rename-save');
    const renameInput = this.content.querySelector('#sp-rename-input');
    if (renameSave && renameInput && this._lastScan) {
      const doRename = () => {
        const newName = renameInput.value.trim();
        if (!newName) return;
        const oldName = this._lastScan.item_name || this._lastScan.name;
        hass.callService('smart_pantry', 'rename_item', { old_name: oldName, new_name: newName });
        this._lastScan = Object.assign({}, this._lastScan, {
          item_name: newName, lookup_failed: false, source: 'library',
        });
        this._renderCard();
      };
      renameSave.onclick = doRename;
      renameInput.onkeydown = (ev) => {
        if (ev.key === 'Enter') { ev.preventDefault(); doRename(); }
      };
    }

    const scanAdd = this.content.querySelector('#sp-scan-add');
    if (scanAdd && this._lastScan) {
      scanAdd.onclick = () => {
        const s = this._lastScan;
        this._addToLists(s.item_name || s.name, 1, s.unit || 'piece');
        scanAdd.textContent = '✓ Added';
        scanAdd.disabled = true;
      };
    }
  }

  // ---- Keyboard-wedge (BT/USB scanner) capture ------------------------------

  _attachWedgeListener(inputEl) {
    this._detachWedgeListener();
    const hass = this._hass;
    this._wedgeListener = (ev) => {
      // Ignore when user is typing in the manual input (it has its own handler).
      if (document.activeElement === inputEl) return;
      if (ev.key === 'Enter') {
        if (this._wedgeBuffer.length >= 6) {
          const code = this._wedgeBuffer;
          this._wedgeBuffer = '';
          if (this._rapidMode) this._rapidCount += 1;
          hass.callService('smart_pantry', 'scan_barcode', this._scanPayload(code));
          ev.preventDefault();
        } else {
          this._wedgeBuffer = '';
        }
        return;
      }
      if (ev.key && ev.key.length === 1 && /[0-9A-Za-z\-]/.test(ev.key)) {
        this._wedgeBuffer += ev.key;
        // Scanners type in bursts; a human pause resets the buffer.
        clearTimeout(this._wedgeTimer);
        this._wedgeTimer = setTimeout(() => { this._wedgeBuffer = ''; }, 250);
      }
    };
    window.addEventListener('keydown', this._wedgeListener, true);
  }

  _detachWedgeListener() {
    if (this._wedgeListener) {
      window.removeEventListener('keydown', this._wedgeListener, true);
      this._wedgeListener = null;
    }
    clearTimeout(this._wedgeTimer);
    this._wedgeBuffer = '';
  }

  // ---- Camera -------------------------------------------------------------

  _openCamera() {
    if (this._cameraActive) return;
    this._cameraActive = true;

    const modal = document.createElement('div');
    modal.className = 'sp-camera-modal';
    modal.innerHTML = this._styles() +
      '<video id="sp-camera-video" autoplay muted playsinline style="width:100%;max-width:480px;border-radius:8px;background:#000;min-height:200px;"></video>' +
      '<div id="sp-camera-status" style="color:white;margin-top:12px;font-size:14px;text-align:center;max-width:480px;">Requesting camera access…</div>' +
      '<button class="sp-btn sp-btn-ghost" id="sp-stop-camera" style="margin-top:16px;max-width:200px;">Stop Camera</button>';
    document.body.appendChild(modal);
    this._cameraModal = modal;

    const statusEl = modal.querySelector('#sp-camera-status');
    const videoEl = modal.querySelector('#sp-camera-video');
    const stopBtn = modal.querySelector('#sp-stop-camera');

    if (stopBtn) {
      stopBtn.onclick = () => { this._stopCamera(); };
    }

    const hass = this._hass;
    const setStatus = (msg) => { if (statusEl) statusEl.innerHTML = msg; };

    // WebView-safe flow: acquire the camera stream explicitly FIRST so
    // permission errors surface immediately (the HA Companion App's WebView
    // fails silently when ZXing enumerates devices before permission exists).
    const start = async () => {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw Object.assign(new Error('Camera API unavailable'), { name: 'NotSupportedError' });
      }
      let stream;
      try {
        // Prefer the rear camera on phones.
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
      } catch (e) {
        // Some WebViews reject the facingMode constraint — retry with any camera.
        if (e.name === 'OverconstrainedError' || e.name === 'NotFoundError') {
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        } else {
          throw e;
        }
      }
      if (!this._cameraActive) { stream.getTracks().forEach((t) => t.stop()); return; }
      this._cameraStream = stream;
      videoEl.srcObject = stream;
      try { await videoEl.play(); } catch (e) { /* autoplay may already be running */ }
      setStatus('Loading barcode decoder…');
      await this._loadZXing();
      if (!this._cameraActive) return;
      setStatus('Point the camera at a barcode…');
      this._codeReader = new window.ZXing.BrowserMultiFormatReader();
      const onResult = (result, err) => {
        if (result) {
          const barcode = result.getText();
          hass.callService('smart_pantry', 'scan_barcode', this._scanPayload(barcode));
          this._stopCamera();
        } else if (err && err.name && err.name !== 'NotFoundException' && err.name !== 'NotFoundException2') {
          setStatus('Decoder error: ' + this._escape(err.message || err.name));
        }
      };
      // Decode from the stream we already own (never re-enumerates devices).
      if (typeof this._codeReader.decodeFromStream === 'function') {
        this._codeReader.decodeFromStream(stream, videoEl, onResult);
      } else {
        this._codeReader.decodeFromVideoDevice(undefined, videoEl, onResult);
      }
    };

    start().catch((err) => {
      const name = (err && err.name) || '';
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        setStatus('🚫 Camera permission denied.<br><br>' +
          '<b>HA Companion App (Android):</b> long-press the app icon → App info → Permissions → Camera → Allow, then reopen this page.<br>' +
          '<b>iOS:</b> Settings → Home Assistant → enable Camera.<br>' +
          '<b>Browser:</b> tap the 🔒 icon in the address bar and allow the camera.');
      } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        setStatus('🚫 No camera found on this device. Use the scanner/manual input instead.');
      } else if (name === 'NotReadableError') {
        setStatus('🚫 Camera is in use by another app. Close it and try again.');
      } else if (name === 'NotSupportedError') {
        setStatus('🚫 This app/browser does not expose the camera API. Update the HA Companion App, or open this dashboard in Chrome/Safari over HTTPS.');
      } else {
        setStatus('Camera error: ' + this._escape((err && err.message) || String(err)));
      }
    });
  }

  /** Build a scan_barcode payload including optional qty/price from the scan view inputs. */
  _scanPayload(barcode) {
    const payload = { barcode: barcode };
    const qtyEl = this.content && this.content.querySelector('#sp-scan-qty');
    const priceEl = this.content && this.content.querySelector('#sp-scan-price');
    const qty = qtyEl ? parseFloat(qtyEl.value) : NaN;
    const price = priceEl ? parseFloat(priceEl.value) : NaN;
    if (!isNaN(qty) && qty > 0) payload.quantity = qty;
    if (!isNaN(price) && price >= 0) payload.price = price;
    return payload;
  }

  _stopCamera() {
    this._cameraActive = false;

    if (this._codeReader) {
      try { this._codeReader.reset(); } catch (err) { /* already reset */ }
      this._codeReader = null;
    }

    if (this._cameraStream) {
      try { this._cameraStream.getTracks().forEach((t) => t.stop()); } catch (err) { /* ok */ }
      this._cameraStream = null;
    }

    if (this._cameraModal) {
      const videoEl = this._cameraModal.querySelector('#sp-camera-video');
      if (videoEl && videoEl.srcObject) {
        const tracks = videoEl.srcObject.getTracks ? videoEl.srcObject.getTracks() : [];
        tracks.forEach((track) => {
          try { track.stop(); } catch (err) { /* already stopped */ }
        });
        videoEl.srcObject = null;
      }
      if (this._cameraModal.parentNode) {
        this._cameraModal.parentNode.removeChild(this._cameraModal);
      }
      this._cameraModal = null;
    }
  }

  /**
   * Decode a barcode from a photo taken with the native camera app.
   * Tries multiple scales and rotations because hand-held photos are rarely
   * perfectly framed. Works without navigator.mediaDevices.
   */
  async _decodePhoto(file) {
    const statusEl = this.content && this.content.querySelector('#sp-photo-status');
    const setStatus = (msg) => { if (statusEl) statusEl.innerHTML = msg; };
    try {
      setStatus('⏳ Decoding photo…');
      await this._loadZXing();
      const url = URL.createObjectURL(file);
      const img = new Image();
      await new Promise((res, rej) => { img.onload = res; img.onerror = () => rej(new Error('Could not read the photo')); img.src = url; });

      const hints = new Map();
      const Z = window.ZXing;
      hints.set(Z.DecodeHintType.TRY_HARDER, true);
      hints.set(Z.DecodeHintType.POSSIBLE_FORMATS, [
        Z.BarcodeFormat.EAN_13, Z.BarcodeFormat.EAN_8, Z.BarcodeFormat.UPC_A,
        Z.BarcodeFormat.UPC_E, Z.BarcodeFormat.CODE_128, Z.BarcodeFormat.CODE_39,
        Z.BarcodeFormat.QR_CODE, Z.BarcodeFormat.ITF, Z.BarcodeFormat.CODABAR,
      ]);
      const mfReader = new Z.MultiFormatReader();
      mfReader.setHints(hints);

      const tryDecode = (canvas) => {
        try {
          const source = new Z.HTMLCanvasElementLuminanceSource(canvas);
          const bitmap = new Z.BinaryBitmap(new Z.HybridBinarizer(source));
          const result = mfReader.decode(bitmap);
          return result ? result.getText() : null;
        } catch (e) { return null; }
      };

      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      let text = null;
      // Try a few sizes (large first for small barcodes, then downscaled for blur)
      // and 4 rotations each.
      const widths = [Math.min(img.naturalWidth, 1600), 1024, 640];
      outer: for (const w of widths) {
        const scale = w / img.naturalWidth;
        const h = Math.round(img.naturalHeight * scale);
        for (const deg of [0, 90, 180, 270]) {
          const rot = (deg % 180 !== 0);
          canvas.width = rot ? h : w;
          canvas.height = rot ? w : h;
          ctx.save();
          ctx.translate(canvas.width / 2, canvas.height / 2);
          ctx.rotate((deg * Math.PI) / 180);
          ctx.drawImage(img, -w / 2, -h / 2, w, h);
          ctx.restore();
          text = tryDecode(canvas);
          if (text) break outer;
        }
      }
      URL.revokeObjectURL(url);

      if (text) {
        setStatus('✅ Barcode found: <b>' + this._escape(text) + '</b> — adding…');
        this._hass.callService('smart_pantry', 'scan_barcode', this._scanPayload(text));
      } else {
        setStatus('❌ No barcode found in the photo. Hold the phone closer (fill the frame with the barcode), keep it flat and well lit, then try again.');
      }
    } catch (err) {
      setStatus('❌ ' + this._escape((err && err.message) || String(err)));
    }
  }

  _loadZXing() {
    return new Promise((resolve, reject) => {
      if (window.ZXing) { resolve(); return; }
      const s = document.createElement('script');
      s.src = 'https://unpkg.com/@zxing/library@0.19.2/umd/index.min.js';
      s.onload = resolve;
      s.onerror = () => reject(new Error('Failed to load ZXing from CDN'));
      document.head.appendChild(s);
    });
  }

  // ---- Helpers ------------------------------------------------------------

  _addToLists(name, quantity, unit) {
    // The backend service also syncs into HA's default shopping_list,
    // so a single call keeps both lists consistent (no duplicates).
    this._hass.callService('smart_pantry', 'add_to_shopping_list', {
      item_name: name, quantity: quantity, unit: unit,
    });
  }

  _wireBack() {
    const back = this.content.querySelector('#sp-back');
    if (back) {
      back.onclick = () => {
        this._view = 'main';
        this._renderCard();
      };
    }
  }

  _ingredientName(ing) {
    if (ing == null) return '';
    if (typeof ing === 'string') return ing;
    return ing.name || ing.ingredient || String(ing);
  }

  _escape(value) {
    if (value == null) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /**
   * Visual representation for an item: product photo when available
   * (e.g. from Open Food Facts after a barcode scan), else a category emoji.
   */
  _itemIcon(item) {
    const url = item && item.image_url;
    if (url && /^https?:\/\//i.test(url)) {
      const fallback = this._escape(SP_CATEGORY_ICONS[(item.category || 'other')] || SP_CATEGORY_ICONS.other);
      return '<span class="sp-item-avatar"><img src="' + this._escape(url) + '" alt="" loading="lazy" ' +
        'onerror="this.parentNode.textContent=\'' + fallback + '\'"></span>';
    }
    const icon = SP_CATEGORY_ICONS[(item && item.category) || 'other'] || SP_CATEGORY_ICONS.other;
    return '<span class="sp-item-avatar">' + icon + '</span>';
  }
}

customElements.define('smart-pantry-card', SmartPantryCard);

class SmartPantryCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
  }
}
customElements.define('smart-pantry-card-editor', SmartPantryCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'smart-pantry-card',
  name: 'Smart Pantry Card',
  description: 'Interactive dashboard for Smart Pantry Scanner with suggestions, recipes and barcode scanning',
});

console.info(
  '%c SMART-PANTRY-CARD %c v' + SMART_PANTRY_CARD_VERSION + ' loaded ',
  'color: white; background: #2E7D32; font-weight: 700;',
  'color: #2E7D32; background: white; font-weight: 700;'
);
