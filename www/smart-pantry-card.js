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
  }

  static getConfigElement() {
    return document.createElement('smart-pantry-card-editor');
  }

  static getStubConfig() {
    return { entity: 'sensor.smart_pantry_my_home_total_items' };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('You need to define an entity');
    }
    this._config = config;
  }

  set hass(hass) {
    this._hass = hass;

    // Subscribe to backend events exactly once. subscribeEvents resolves to an
    // unsubscribe function; we store it so a later disconnect can clean up and
    // so we never double-subscribe on repeated hass assignments.
    if (this._unsubRecipes === null && hass && hass.connection) {
      try {
        hass.connection
          .subscribeEvents((event) => {
            this._recipes = (event && event.data && event.data.recipes) || [];
            this._view = 'recipes';
            this._renderCard();
          }, 'smart_pantry_recipes_suggested')
          .then((unsub) => {
            this._unsubRecipes = unsub;
          })
          .catch((err) => {
            // Keep the flag null so a future hass assignment can retry.
            console.error('SmartPantryCard: failed to subscribe to recipes event', err);
          });

        hass.connection
          .subscribeEvents((event) => {
            this._lastScan = (event && event.data) || null;
            this._view = 'scan';
            this._renderCard();
          }, 'smart_pantry_scan_result')
          .then((unsub) => {
            this._unsubScan = unsub;
          })
          .catch((err) => {
            console.error('SmartPantryCard: failed to subscribe to scan event', err);
          });

        // Set a non-null sentinel synchronously so the block above does not run
        // again before the async subscriptions resolve.
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
    // Clean up subscriptions and any live camera so the card leaves nothing running.
    if (typeof this._unsubRecipes === 'function') {
      try { this._unsubRecipes(); } catch (err) { /* already gone */ }
    }
    if (typeof this._unsubScan === 'function') {
      try { this._unsubScan(); } catch (err) { /* already gone */ }
    }
    this._stopCamera();
  }

  getCardSize() {
    return 6;
  }

  // ---- Rendering ----------------------------------------------------------

  _ensureShell() {
    if (this.content) {
      return;
    }
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
      '.sp-btn-back { background: none; border: none; color: var(--primary-text-color); font-size: 14px; cursor: pointer; padding: 4px 0; margin-bottom: 12px; display: flex; align-items: center; gap: 4px; }' +
      '.sp-recipe-card { border: 1px solid var(--divider-color); border-radius: 12px; padding: 14px; margin-bottom: 10px; }' +
      '.sp-match-bar { height: 8px; border-radius: 100px; margin: 8px 0; }' +
      '.sp-chip { display: inline-block; padding: 3px 8px; border-radius: 100px; font-size: 11px; margin: 2px; }' +
      '.sp-chip.green { background: #E8F5E9; color: #2E7D32; }' +
      '.sp-chip.gray { background: #F5F5F5; color: #757575; }' +
      '.sp-camera-modal { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 9999; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; }' +
      '.sp-input { width: 100%; padding: 10px 14px; border: 1px solid var(--divider-color); border-radius: 10px; font-size: 14px; background: var(--card-background-color); color: var(--primary-text-color); box-sizing: border-box; }' +
      '.sp-warning { padding: 10px 14px; background: #FFF3E0; border-radius: 10px; color: #E65100; font-size: 13px; margin: 8px 0; }' +
      '</style>';
  }

  _renderCard() {
    this._ensureShell();

    const entityId = this._config.entity;
    const state = this._hass ? this._hass.states[entityId] : null;
    if (!state) {
      this.content.innerHTML = this._styles() +
        '<div style="color:#E53935;text-align:center;padding:20px;">Entity not found: ' +
        this._escape(entityId) + '</div>';
      return;
    }

    if (this._view === 'recipes') {
      this._renderRecipes();
      return;
    }
    if (this._view === 'scan') {
      this._renderScan();
      return;
    }
    this._renderMain();
  }

  // ---- Main view ----------------------------------------------------------

  _renderMain() {
    const hass = this._hass;
    const entityId = this._config.entity;

    const totalItems = hass.states[entityId];
    const expiringSoon = hass.states[entityId.replace('total_items', 'expiring_soon')];
    const savings = hass.states[entityId.replace('total_items', 'savings')];
    const shoppingList = hass.states[entityId.replace('total_items', 'shopping_list')];
    const weeklyBudget = hass.states[entityId.replace('total_items', 'weekly_budget')];

    const expiringItems = (expiringSoon && expiringSoon.attributes && expiringSoon.attributes.items) || [];
    const shoppingItems = (shoppingList && shoppingList.attributes && shoppingList.attributes.items) || [];
    const pantryCategories = (totalItems && totalItems.attributes && totalItems.attributes.categories) || {};
    const lowStockItems = (totalItems && totalItems.attributes && totalItems.attributes.low_stock_items) || [];

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

    // Low stock
    if (lowStockItems.length > 0) {
      html += '<div class="sp-section"><div class="sp-section-title">🔴 Low Stock</div><div class="sp-item-list">';
      lowStockItems.forEach((item, idx) => {
        html += '<div class="sp-item"><div class="sp-item-left"><span class="sp-item-icon">🔴</span><div>' +
          '<div class="sp-item-name">' + this._escape(item.name) + '</div>' +
          '<div class="sp-item-meta">' + this._escape(item.quantity) + ' ' + this._escape(item.unit || '') + '</div>' +
          '</div></div>' +
          '<button class="sp-btn-mini" data-lowstock="' + idx + '">Restock</button></div>';
      });
      html += '</div></div>';
    }

    // Expiring
    html += '<div class="sp-section"><div class="sp-section-title">⏰ Expiring Soon</div>';
    if (expiringItems.length === 0) {
      html += '<div class="sp-empty">No items expiring soon 🎉</div>';
    } else {
      html += '<div class="sp-item-list">';
      expiringItems.slice(0, 5).forEach((item, idx) => {
        const days = item.days_until_expiry;
        const badgeClass = days <= 1 ? 'red' : days <= 3 ? 'orange' : 'green';
        const badgeText = days < 0 ? 'Expired' : days === 0 ? 'Today' : days === 1 ? '1 day' : days + ' days';
        const icons = { produce: '🥬', dairy: '🥛', meat: '🍗', seafood: '🦐', bakery: '🍞', pantry: '🥫', frozen: '🧊', beverages: '🥤', condiments: '🧂', snacks: '🍿', other: '📦' };
        const icon = icons[item.category] || '📦';
        html += '<div class="sp-item"><div class="sp-item-left"><span class="sp-item-icon">' + icon + '</span><div>' +
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
        html += '<div class="sp-item"><div class="sp-item-left"><span class="sp-item-icon">📝</span><div>' +
          '<div class="sp-item-name">' + this._escape(item.name) + '</div>' +
          (item.notes ? '<div class="sp-item-meta">' + this._escape(item.notes) + '</div>' : '') +
          '</div></div><span class="sp-badge green">' + this._escape(item.quantity) + ' ' + this._escape(item.unit || '') + '</span></div>';
      });
      html += '</div>';
    }
    html += '</div>';

    // Action buttons
    html += '<div class="sp-btn-row">' +
      '<button class="sp-btn sp-btn-primary" id="btn-recipes">🍳 Recipes</button>' +
      '<button class="sp-btn sp-btn-secondary" id="btn-scan">📷 Scan</button>' +
      '<button class="sp-btn sp-btn-ghost" id="btn-clear">🗑️ Clear</button>' +
      '</div>';

    html += '</div>';
    this.content.innerHTML = html;

    // Re-attach handlers — innerHTML assignment drops all prior listeners.
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

    // Low stock restock buttons.
    this.content.querySelectorAll('[data-lowstock]').forEach((btn) => {
      btn.onclick = () => {
        const item = lowStockItems[parseInt(btn.getAttribute('data-lowstock'), 10)];
        if (item) {
          this._addToLists(item.name, 1, item.unit || 'piece');
        }
      };
    });

    // Expiring add-to-list buttons.
    this.content.querySelectorAll('[data-expiring]').forEach((btn) => {
      btn.onclick = () => {
        const item = expiringItems[parseInt(btn.getAttribute('data-expiring'), 10)];
        if (item) {
          this._addToLists(item.name, 1, item.unit || 'piece');
        }
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
      // Re-request recipes; the subscribed event will re-render when they arrive.
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

      html += '<div style="font-size:12px;color:var(--secondary-text-color);margin-top:4px;">' + pct + '% match</div>';
      html += '<div class="sp-match-bar" style="background:' + barColor + ';width:' + pct + '%;"></div>';

      if (matched.length > 0) {
        html += '<div style="margin-top:6px;">';
        matched.forEach((ing) => {
          html += '<span class="sp-chip green">' + this._escape(this._ingredientName(ing)) + '</span>';
        });
        html += '</div>';
      }

      if (missing.length > 0) {
        html += '<div style="margin-top:4px;">';
        missing.forEach((ing) => {
          html += '<span class="sp-chip gray">' + this._escape(this._ingredientName(ing)) + '</span>';
        });
        html += '</div>';
        html += '<button class="sp-btn-mini" style="margin-top:10px;" data-recipe-missing="' + idx + '">Add missing to list</button>';
        html += '<span class="sp-added-marker" data-added-marker="' + idx + '" style="display:none;font-size:12px;color:#2E7D32;margin-left:8px;">✓ Added!</span>';
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
        if (!recipe) {
          return;
        }
        const missing = recipe.missing_ingredients || [];
        missing.forEach((ing) => {
          const name = this._ingredientName(ing);
          hass.callService('smart_pantry', 'add_to_shopping_list', { item_name: name, quantity: 1, unit: 'piece' });
          hass.callService('shopping_list', 'add_item', { name: name });
        });
        const marker = this.content.querySelector('[data-added-marker="' + idx + '"]');
        if (marker) {
          marker.style.display = 'inline';
        }
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
      '<div class="sp-section-title">Scanner / Manual Entry</div>' +
      '<div style="font-size:12px;color:var(--secondary-text-color);margin-bottom:6px;">Scan or type barcode:</div>' +
      '<input type="text" id="sp-barcode-input" class="sp-input" placeholder="Scan with BT/USB or type here…" autofocus>' +
      '<button class="sp-btn sp-btn-primary" id="sp-barcode-submit" style="margin-top:10px;">Submit</button>' +
      '</div>';

    // Camera section
    html += '<div class="sp-section"><div class="sp-section-title">Camera (HTTPS only)</div>';
    if (location.protocol !== 'https:') {
      html += '<div class="sp-warning">⚠️ Camera requires HTTPS. Use scanner input above.</div>';
    } else {
      html += '<button class="sp-btn sp-btn-secondary" id="sp-use-camera">Use Camera</button>';
    }
    html += '</div>';

    // Last scan result
    if (this._lastScan) {
      const s = this._lastScan;
      html += '<div class="sp-section"><div class="sp-section-title">Last Scan</div>' +
        '<div class="sp-recipe-card">' +
        '<div class="sp-item-name" style="font-size:15px;">' + this._escape(s.name || s.item_name || 'Unknown item') + '</div>' +
        '<div class="sp-item-meta" style="margin-top:4px;">' +
        'Qty: ' + this._escape(s.quantity != null ? s.quantity : '—') +
        (s.expiry || s.expiry_date ? ' • Expires: ' + this._escape(s.expiry || s.expiry_date) : '') +
        '</div>' +
        (s.low_stock === true ? '<div class="sp-warning" style="margin-top:8px;">⚠️ Low stock — added to shopping list suggestion</div>' : '') +
        '</div></div>';
    }

    html += '</div>';
    this.content.innerHTML = html;

    this._wireBack();

    const input = this.content.querySelector('#sp-barcode-input');
    const submit = this.content.querySelector('#sp-barcode-submit');

    const submitBarcode = () => {
      if (!input) {
        return;
      }
      const value = input.value.trim();
      if (value.length === 0) {
        return;
      }
      hass.callService('smart_pantry', 'scan_barcode', { barcode: value });
      input.value = '';
    };

    if (submit) {
      submit.onclick = submitBarcode;
    }
    if (input) {
      input.onkeydown = (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          submitBarcode();
        }
      };
      // Focus after the DOM settles so autofocus works reliably in Lovelace.
      setTimeout(() => { try { input.focus(); } catch (err) { /* not focusable yet */ } }, 0);
    }

    const useCamera = this.content.querySelector('#sp-use-camera');
    if (useCamera) {
      useCamera.onclick = () => {
        this._openCamera();
      };
    }
  }

  // ---- Camera -------------------------------------------------------------

  _openCamera() {
    if (this._cameraActive) {
      return;
    }
    this._cameraActive = true;

    // The modal overlays the whole viewport, so it must live on document.body,
    // not inside this.content.
    const modal = document.createElement('div');
    modal.className = 'sp-camera-modal';
    modal.innerHTML = this._styles() +
      '<video id="sp-camera-video" autoplay playsinline style="width:100%;max-width:480px;border-radius:8px;"></video>' +
      '<div id="sp-camera-status" style="color:white;margin-top:12px;font-size:14px;">Loading scanner…</div>' +
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

    this._loadZXing()
      .then(() => {
        if (!this._cameraActive) {
          // User stopped the camera while the library was loading.
          return;
        }
        if (statusEl) {
          statusEl.textContent = 'Scanning…';
        }
        this._codeReader = new window.ZXing.BrowserMultiFormatReader();
        this._codeReader.decodeFromVideoDevice(undefined, videoEl, (result, err) => {
          if (result) {
            const barcode = result.getText();
            hass.callService('smart_pantry', 'scan_barcode', { barcode: barcode });
            this._stopCamera();
          } else if (err && err.name && err.name !== 'NotFoundException') {
            // NotFoundException fires continuously between frames — ignore it.
            if (statusEl) {
              statusEl.textContent = 'Camera error: ' + err.message;
            }
          }
        });
      })
      .catch((err) => {
        if (statusEl) {
          statusEl.textContent = 'Camera error: ' + err.message;
        }
      });
  }

  _stopCamera() {
    this._cameraActive = false;

    if (this._codeReader) {
      try { this._codeReader.reset(); } catch (err) { /* already reset */ }
      this._codeReader = null;
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

  _loadZXing() {
    return new Promise((resolve, reject) => {
      if (window.ZXing) {
        resolve();
        return;
      }
      const s = document.createElement('script');
      s.src = 'https://unpkg.com/@zxing/library@0.19.2/umd/index.min.js';
      s.onload = resolve;
      s.onerror = () => reject(new Error('Failed to load ZXing from CDN'));
      document.head.appendChild(s);
    });
  }

  // ---- Helpers ------------------------------------------------------------

  _addToLists(name, quantity, unit) {
    const hass = this._hass;
    hass.callService('smart_pantry', 'add_to_shopping_list', { item_name: name, quantity: quantity, unit: unit });
    hass.callService('shopping_list', 'add_item', { name: name });
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
    // Ingredients may arrive as plain strings or as objects with a name field.
    if (ing == null) {
      return '';
    }
    if (typeof ing === 'string') {
      return ing;
    }
    return ing.name || ing.ingredient || String(ing);
  }

  _escape(value) {
    if (value == null) {
      return '';
    }
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
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
  description: 'Interactive dashboard for Smart Pantry Scanner',
});
