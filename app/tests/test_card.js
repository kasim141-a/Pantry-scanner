'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'www', 'smart-pantry-card.js'),
  'utf8'
);
const context = vm.createContext({
  console: { info() {}, error() {} },
  customElements: { define() {} },
  HTMLElement: class {},
  window: { customCards: [] },
});
vm.runInContext(`${source}\nthis.SmartPantryCard = SmartPantryCard;`, context);
const { SmartPantryCard } = context;

test('recipe loader deduplicates requests while one is pending', () => {
  const card = new SmartPantryCard();
  const calls = [];
  card._hass = {
    callService(domain, service, data) {
      calls.push({ domain, service, data });
      return new Promise(() => {});
    },
  };

  card._loadRecipes();
  card._loadRecipes();

  assert.equal(calls.length, 1);
  assert.equal(calls[0].service, 'get_recipes');
  assert.equal(card._recipesLoading, true);
});

test('recipe loader exposes errors and permits retry', async () => {
  const card = new SmartPantryCard();
  card._hass = {
    callService() { return Promise.reject(new Error('Service unavailable')); },
  };

  card._loadRecipes();
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(card._recipesLoading, false);
  assert.equal(card._recipesError, 'Service unavailable');
});

test('scan payload omits invalid optional values', () => {
  const card = new SmartPantryCard();
  card.content = {
    querySelector(selector) {
      if (selector === '#sp-scan-qty') return { value: '2' };
      if (selector === '#sp-scan-price') return { value: '-1' };
      return null;
    },
  };

  const payload = card._scanPayload('012345');
  assert.equal(payload.barcode, '012345');
  assert.equal(payload.quantity, 2);
  assert.equal(Object.hasOwn(payload, 'price'), false);
});

test('sibling entity derivation preserves the configured pantry prefix', () => {
  const card = new SmartPantryCard();
  assert.equal(
    card._deriveSibling('sensor.smart_pantry_kitchen_expiring_soon', 'total_items'),
    'sensor.smart_pantry_kitchen_total_items'
  );
});
