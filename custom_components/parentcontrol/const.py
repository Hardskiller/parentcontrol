"""Constants for ParentControl."""

DOMAIN = "parentcontrol"

CONF_AGE = "age"
CONF_MODEL = "model"
CONF_OLLAMA_URL = "ollama_url"
CONF_PLAYERS = "players"
CONF_DEVICE_AGES = "device_ages"

DEFAULT_OLLAMA_URL = "http://localhost:11434"
MAX_AGE = 18
RETRY_SECONDS = 600
PAUSE_DEBOUNCE_SECONDS = 2
MAX_EVENTS = 500
STORAGE_VERSION = 1

STATUS_BLOCKED = "blockiert"
STATUS_CHECKING = "wird_geprueft"
STATUS_DISABLED = "aus"
STATUS_FREE = "frei"
STATUS_IDLE = "inaktiv"
STATUS_NO_DATA = "keine_daten"
STATUS_UNCHECKED = "nicht_geprueft"
STATUSES = [
    STATUS_BLOCKED,
    STATUS_CHECKING,
    STATUS_DISABLED,
    STATUS_FREE,
    STATUS_IDLE,
    STATUS_NO_DATA,
    STATUS_UNCHECKED,
]

EVENT_PAUSED = f"{DOMAIN}_paused"
