"""Config flow for Smart Pantry Scanner integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN, CONF_HOUSEHOLD_NAME, CONF_CURRENCY, CONF_WEEKLY_BUDGET, CONF_DIET_PREFERENCE,
    CONF_LOW_STOCK_THRESHOLD, CONF_EXPIRY_WARNING_DAYS, CONF_AUTO_ADD_TO_HA_LIST,
    DEFAULT_HOUSEHOLD_NAME, DEFAULT_CURRENCY, DEFAULT_WEEKLY_BUDGET, DEFAULT_DIET_PREFERENCE, DIET_OPTIONS,
    DEFAULT_LOW_STOCK_THRESHOLD, DEFAULT_EXPIRY_WARNING_DAYS, DEFAULT_AUTO_ADD_TO_HA_LIST,
)

CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"]


class SmartPantryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Pantry Scanner."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"smart_pantry_{user_input[CONF_HOUSEHOLD_NAME].lower().replace(' ', '_')}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_HOUSEHOLD_NAME], data={}, options=user_input,
            )
        data_schema = vol.Schema({
            vol.Required(CONF_HOUSEHOLD_NAME, default=DEFAULT_HOUSEHOLD_NAME): str,
            vol.Required(CONF_CURRENCY, default=DEFAULT_CURRENCY): vol.In(CURRENCIES),
            vol.Required(CONF_WEEKLY_BUDGET, default=DEFAULT_WEEKLY_BUDGET): vol.Coerce(int),
            vol.Required(CONF_DIET_PREFERENCE, default=DEFAULT_DIET_PREFERENCE): vol.In(DIET_OPTIONS),
            vol.Required(CONF_LOW_STOCK_THRESHOLD, default=DEFAULT_LOW_STOCK_THRESHOLD): vol.Coerce(float),
            vol.Required(CONF_EXPIRY_WARNING_DAYS, default=DEFAULT_EXPIRY_WARNING_DAYS): vol.Coerce(int),
            vol.Required(CONF_AUTO_ADD_TO_HA_LIST, default=DEFAULT_AUTO_ADD_TO_HA_LIST): bool,
        })
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SmartPantryOptionsFlow(config_entry)


class SmartPantryOptionsFlow(OptionsFlow):
    """Handle options flow for Smart Pantry Scanner."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        data_schema = vol.Schema({
            vol.Required(CONF_HOUSEHOLD_NAME, default=options.get(CONF_HOUSEHOLD_NAME, DEFAULT_HOUSEHOLD_NAME)): str,
            vol.Required(CONF_CURRENCY, default=options.get(CONF_CURRENCY, DEFAULT_CURRENCY)): vol.In(CURRENCIES),
            vol.Required(CONF_WEEKLY_BUDGET, default=options.get(CONF_WEEKLY_BUDGET, DEFAULT_WEEKLY_BUDGET)): vol.Coerce(int),
            vol.Required(CONF_DIET_PREFERENCE, default=options.get(CONF_DIET_PREFERENCE, DEFAULT_DIET_PREFERENCE)): vol.In(DIET_OPTIONS),
            vol.Required(CONF_LOW_STOCK_THRESHOLD, default=options.get(CONF_LOW_STOCK_THRESHOLD, DEFAULT_LOW_STOCK_THRESHOLD)): vol.Coerce(float),
            vol.Required(CONF_EXPIRY_WARNING_DAYS, default=options.get(CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS)): vol.Coerce(int),
            vol.Required(CONF_AUTO_ADD_TO_HA_LIST, default=options.get(CONF_AUTO_ADD_TO_HA_LIST, DEFAULT_AUTO_ADD_TO_HA_LIST)): bool,
        })
        return self.async_show_form(step_id="init", data_schema=data_schema, errors=errors)
