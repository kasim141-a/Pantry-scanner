"""Constants for the Smart Pantry Scanner integration."""

from typing import Final

DOMAIN: Final = "smart_pantry"
PLATFORMS: Final = ["sensor", "button"]

CONF_HOUSEHOLD_NAME: Final = "household_name"
CONF_CURRENCY: Final = "currency"
CONF_WEEKLY_BUDGET: Final = "weekly_budget"
CONF_DIET_PREFERENCE: Final = "diet_preference"
CONF_LOW_STOCK_THRESHOLD: Final = "low_stock_threshold"
CONF_EXPIRY_WARNING_DAYS: Final = "expiry_warning_days"
CONF_AUTO_ADD_TO_HA_LIST: Final = "auto_add_to_ha_shopping_list"

DEFAULT_HOUSEHOLD_NAME: Final = "My Home"
DEFAULT_CURRENCY: Final = "USD"
DEFAULT_WEEKLY_BUDGET: Final = 120
DEFAULT_DIET_PREFERENCE: Final = "none"
DEFAULT_LOW_STOCK_THRESHOLD: Final = 1
DEFAULT_EXPIRY_WARNING_DAYS: Final = 3
DEFAULT_AUTO_ADD_TO_HA_LIST: Final = False

DIET_OPTIONS: Final = ["none", "vegetarian", "vegan", "keto", "gluten_free", "dairy_free", "paleo"]

STORAGE_KEY_PANTRY: Final = "smart_pantry_data"
STORAGE_VERSION: Final = 1

ENTITY_TOTAL_ITEMS: Final = "total_items"
ENTITY_EXPIRING_SOON: Final = "expiring_soon"
ENTITY_EXPIRED: Final = "expired"
ENTITY_WASTE_PREVENTED: Final = "waste_prevented"
ENTITY_SAVINGS: Final = "savings"
ENTITY_SHOPPING_LIST_COUNT: Final = "shopping_list_count"
ENTITY_WEEKLY_BUDGET_STATUS: Final = "weekly_budget_status"
ENTITY_SUGGESTIONS: Final = "suggestions"

SERVICE_ADD_ITEM: Final = "add_item"
SERVICE_REMOVE_ITEM: Final = "remove_item"
SERVICE_UPDATE_ITEM: Final = "update_item"
SERVICE_SCAN_BARCODE: Final = "scan_barcode"
SERVICE_GET_RECIPES: Final = "get_recipes"
SERVICE_ADD_TO_SHOPPING_LIST: Final = "add_to_shopping_list"
SERVICE_CLEAR_SHOPPING_LIST: Final = "clear_shopping_list"
SERVICE_MARK_CONSUMED: Final = "mark_consumed"
SERVICE_SYNC_SUGGESTIONS: Final = "sync_suggestions_to_shopping_list"
SERVICE_ADD_RECIPE_MISSING: Final = "add_recipe_missing_to_shopping_list"

ATTR_ITEM_NAME: Final = "item_name"
ATTR_QUANTITY: Final = "quantity"
ATTR_UNIT: Final = "unit"
ATTR_CATEGORY: Final = "category"
ATTR_EXPIRATION_DATE: Final = "expiration_date"
ATTR_STORAGE_LOCATION: Final = "storage_location"
ATTR_BARCODE: Final = "barcode"
ATTR_NOTES: Final = "notes"
ATTR_RECIPE_COUNT: Final = "recipe_count"
ATTR_INGREDIENTS: Final = "ingredients"
ATTR_RECIPE_NAME: Final = "recipe_name"
ATTR_SUGGEST: Final = "suggest_shopping_list"

CATEGORIES: Final = [
    "produce", "dairy", "meat", "seafood", "bakery",
    "pantry", "frozen", "beverages", "condiments", "snacks", "other"
]

STORAGE_LOCATIONS: Final = [
    "pantry", "refrigerator", "freezer", "countertop", "wine_cellar", "other"
]

UNITS: Final = [
    "piece", "pieces", "g", "kg", "oz", "lb", "ml", "l",
    "cup", "cups", "tbsp", "tsp", "bottle", "bottles",
    "can", "cans", "box", "boxes", "bag", "bags", "pack", "packs"
]

EXPIRE_WARNING_DAYS: Final = 3
EXPIRE_CRITICAL_DAYS: Final = 1
LOW_STOCK_THRESHOLD: Final = 1

BUILT_IN_RECIPES: Final = [
    {
        "name": "Vegetable Stir Fry",
        "ingredients": ["rice", "broccoli", "carrot", "soy sauce", "garlic"],
        "time": "20 min",
        "diet": ["vegetarian", "vegan"],
        "missing_usual": ["soy sauce"]
    },
    {
        "name": "Chicken Alfredo",
        "ingredients": ["chicken", "pasta", "cream", "parmesan", "garlic"],
        "time": "25 min",
        "diet": ["none"],
        "missing_usual": ["cream", "parmesan"]
    },
    {
        "name": "Greek Salad",
        "ingredients": ["tomato", "cucumber", "feta", "olive oil", "olives"],
        "time": "10 min",
        "diet": ["vegetarian", "keto", "gluten_free"],
        "missing_usual": ["feta", "olives"]
    },
    {
        "name": "Egg Fried Rice",
        "ingredients": ["rice", "egg", "soy sauce", "green onion", "peas"],
        "time": "15 min",
        "diet": ["vegetarian"],
        "missing_usual": ["soy sauce", "green onion"]
    },
    {
        "name": "Beef Tacos",
        "ingredients": ["beef", "tortilla", "lettuce", "tomato", "cheese", "salsa"],
        "time": "20 min",
        "diet": ["none"],
        "missing_usual": ["tortilla", "salsa"]
    },
    {
        "name": "Smoothie Bowl",
        "ingredients": ["banana", "berries", "yogurt", "granola", "honey"],
        "time": "5 min",
        "diet": ["vegetarian", "gluten_free"],
        "missing_usual": ["granola", "honey"]
    },
    {
        "name": "Tomato Soup",
        "ingredients": ["tomato", "onion", "garlic", "vegetable broth", "cream"],
        "time": "30 min",
        "diet": ["vegetarian", "gluten_free"],
        "missing_usual": ["vegetable broth", "cream"]
    },
    {
        "name": "Grilled Salmon",
        "ingredients": ["salmon", "lemon", "dill", "olive oil", "asparagus"],
        "time": "18 min",
        "diet": ["keto", "paleo", "gluten_free"],
        "missing_usual": ["dill", "asparagus"]
    }
]

BARCODE_DB: Final = {
    "038000138133": {"name": "Kellogg's Corn Flakes", "category": "pantry", "typical_expiry_days": 365},
    "0044000028838": {"name": "Heinz Tomato Ketchup", "category": "condiments", "typical_expiry_days": 730},
    "0028400009085": {"name": "Nestle Toll House Chocolate Chips", "category": "pantry", "typical_expiry_days": 540},
    "5000157024671": {"name": "Heinz Baked Beans", "category": "pantry", "typical_expiry_days": 730},
    "5010044000138": {"name": "Weetabix", "category": "pantry", "typical_expiry_days": 365},
    "5000169005545": {"name": "Semi-Skimmed Milk 2L", "category": "dairy", "typical_expiry_days": 7},
    "0000000000000": {"name": "Unknown Item", "category": "other", "typical_expiry_days": 30},
}

# Open Food Facts public API used as fallback when a barcode is not in BARCODE_DB.
OFF_API_URL: Final = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_TIMEOUT: Final = 8

# Map Open Food Facts category keywords to Smart Pantry categories.
OFF_CATEGORY_MAP: Final = {
    "fruits": "produce", "vegetables": "produce", "fresh": "produce",
    "dairy": "dairy", "milk": "dairy", "cheese": "dairy", "yogurt": "dairy",
    "meat": "meat", "poultry": "meat",
    "fish": "seafood", "seafood": "seafood",
    "bread": "bakery", "bakery": "bakery", "pastries": "bakery",
    "frozen": "frozen",
    "beverages": "beverages", "drinks": "beverages", "water": "beverages", "juice": "beverages",
    "sauces": "condiments", "condiments": "condiments", "spreads": "condiments",
    "snacks": "snacks", "chips": "snacks", "biscuits": "snacks", "chocolate": "snacks",
    "canned": "pantry", "cereals": "pantry", "pasta": "pantry", "rice": "pantry",
}

# Default expiry guesses (days) per category when scanning unknown products.
CATEGORY_DEFAULT_EXPIRY_DAYS: Final = {
    "produce": 7, "dairy": 10, "meat": 4, "seafood": 3, "bakery": 5,
    "pantry": 365, "frozen": 180, "beverages": 180, "condiments": 365,
    "snacks": 120, "other": 30,
}
