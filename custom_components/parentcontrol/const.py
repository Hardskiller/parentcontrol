"""Constants for ParentControl."""

DOMAIN = "parentcontrol"

CONF_AGE = "age"
CONF_MODEL = "model"
CONF_OLLAMA_URL = "ollama_url"
CONF_PLAYERS = "players"
CONF_DEVICE_AGES = "device_ages"
CONF_AGE_PROMPT = "age_prompt"
CONF_PEDAGOGY_PROMPT = "pedagogy_prompt"
CONF_ALLOWED = "allowed_channels"
CONF_BLOCKED = "blocked_channels"
CONF_DEVICE_ALLOWED = "device_allowed_channels"
CONF_DEVICE_BLOCKED = "device_blocked_channels"

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

SETTING_SEEK_TO_START = "seek_to_start"
SETTING_REQUIRE_PEDAGOGY = "require_pedagogy"
SETTING_BLOCK_PROFANITY = "block_profanity"
SETTING_STRICT = "strict"
SETTING_SKIP_CHECKS = "skip_checks"
SETTINGS = [
    SETTING_SEEK_TO_START,
    SETTING_REQUIRE_PEDAGOGY,
    SETTING_BLOCK_PROFANITY,
    SETTING_STRICT,
    SETTING_SKIP_CHECKS,
]

BLOCK_AGE = "alter"
BLOCK_PEDAGOGY = "paedagogik"
BLOCK_PROFANITY = "schimpfwoerter"
BLOCK_NO_SUBTITLES = "keine_untertitel"
BLOCK_UNCHECKED = "nicht_geprueft"
BLOCK_CHANNEL = "kanal_gesperrt"

LIST_ALLOWED = "freigegeben"
LIST_BLOCKED = "gesperrt"

STAT_VIDEOS = "videos"
STAT_APPROVED = "approved"
STAT_VALUABLE = "valuable"
STAT_SKIPPED = "skipped"
STATS = [STAT_VIDEOS, STAT_APPROVED, STAT_VALUABLE, STAT_SKIPPED]

SERVICE_ALLOW_CHANNEL = "allow_channel"
SERVICE_BLOCK_CHANNEL = "block_channel"

EVENT_PAUSED = f"{DOMAIN}_paused"
