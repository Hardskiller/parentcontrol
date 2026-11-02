"""Constants for ParentControl."""

DOMAIN = "parentcontrol"

CONF_AGE = "age"
CONF_MODEL = "model"
CONF_OLLAMA_URL = "ollama_url"
CONF_PLAYERS = "players"
CONF_AGE_PROMPT = "age_prompt"
CONF_PEDAGOGY_PROMPT = "pedagogy_prompt"
CONF_ALLOWED = "allowed_channels"
CONF_BLOCKED = "blocked_channels"
CONF_ALLOWED_WORDS = "allowed_words"
CONF_PIN = "pin"
CONF_PIN_HASH = "pin_hash"
CONF_HISTORY_SIZE = "history_size"
CONF_NAME = "name"
CONF_PERSON = "person"
CONF_PROFILE = "profile"
# {profile id: {"name", "person", "age"}}; the age is only the start value.
CONF_PROFILES = "profiles"
# {player: [profile id, ...]}
CONF_DEVICE_PROFILES = "device_profiles"
# {profile id: list text}
CONF_PROFILE_ALLOWED = "profile_allowed_channels"
CONF_PROFILE_BLOCKED = "profile_blocked_channels"
CONF_PROFILE_WORDS = "profile_allowed_words"

DEFAULT_OLLAMA_URL = "http://localhost:11434"
MAX_AGE = 18
RETRY_SECONDS = 600
PAUSE_DEBOUNCE_SECONDS = 2
MAX_EVENTS = 500
STORAGE_VERSION = 1
PIN_PATTERN = r"^\d{4,8}$"
UNLOCK_SECONDS = 300
PIN_ATTEMPTS = 5
PIN_LOCKOUT_SECONDS = 900
HISTORY_SIZE = 20
MAX_HISTORY_SIZE = 100
SHORT_MAX_SECONDS = 180
# Cast reports the title up to two minutes late.
NO_DATA_GRACE_SECONDS = 150
HEALTH_INTERVAL_SECONDS = 300
REPAIR_AFTER_SECONDS = 600

STATUS_BLOCKED = "blockiert"
STATUS_CHECKING = "wird_geprueft"
STATUS_DISABLED = "aus"
STATUS_FREE = "frei"
STATUS_IDLE = "inaktiv"
STATUS_NO_DATA = "keine_daten"
STATUS_UNCHECKED = "nicht_geprueft"
STATUS_UNRESTRICTED = "unbeschraenkt"
STATUSES = [
    STATUS_BLOCKED,
    STATUS_CHECKING,
    STATUS_DISABLED,
    STATUS_FREE,
    STATUS_IDLE,
    STATUS_NO_DATA,
    STATUS_UNCHECKED,
    STATUS_UNRESTRICTED,
]

# "Who is watching": all assigned profiles, one profile id, or no check.
SELECT_AUTO = "auto"
SELECT_UNRESTRICTED = "unrestricted"

SETTING_SEEK_TO_START = "seek_to_start"
SETTING_REQUIRE_PEDAGOGY = "require_pedagogy"
SETTING_BLOCK_PROFANITY = "block_profanity"
SETTING_STRICT = "strict"
SETTING_SKIP_CHECKS = "skip_checks"
SETTING_BLOCK_SHORTS = "block_shorts"
SETTING_INHERIT_CHANNELS = "inherit_channels"
SETTING_INHERIT_WORDS = "inherit_words"
DEVICE_SETTINGS = [SETTING_SEEK_TO_START]
# Rules of a child; on a shared device the strictest value wins.
RULES = [
    SETTING_REQUIRE_PEDAGOGY,
    SETTING_BLOCK_PROFANITY,
    SETTING_STRICT,
    SETTING_SKIP_CHECKS,
    SETTING_BLOCK_SHORTS,
]
PROFILE_SETTINGS = [*RULES, SETTING_INHERIT_CHANNELS, SETTING_INHERIT_WORDS]
SETTING_DEFAULTS = {
    SETTING_BLOCK_SHORTS: True,
    SETTING_INHERIT_CHANNELS: True,
    SETTING_INHERIT_WORDS: True,
}
# The value that weakens the protection; changing to it needs the PIN.
LOOSENING_VALUES = {
    SETTING_SKIP_CHECKS: True,
    SETTING_INHERIT_CHANNELS: True,
    SETTING_INHERIT_WORDS: True,
}

BLOCK_AGE = "alter"
BLOCK_PEDAGOGY = "paedagogik"
BLOCK_PROFANITY = "schimpfwoerter"
BLOCK_NO_SUBTITLES = "keine_untertitel"
BLOCK_UNCHECKED = "nicht_geprueft"
BLOCK_CHANNEL = "kanal_gesperrt"
BLOCK_SHORT = "short"
BLOCK_NO_DATA = "keine_daten"

LIST_ALLOWED = "freigegeben"
LIST_BLOCKED = "gesperrt"

STAT_VIDEOS = "videos"
STAT_APPROVED = "approved"
STAT_VALUABLE = "valuable"
STAT_SKIPPED = "skipped"
STATS = [STAT_VIDEOS, STAT_APPROVED, STAT_VALUABLE, STAT_SKIPPED]

SERVICE_ALLOW_CHANNEL = "allow_channel"
SERVICE_BLOCK_CHANNEL = "block_channel"
SERVICE_REMOVE_CHANNEL = "remove_channel"
SERVICE_ALLOW_WORD = "allow_word"
SERVICE_REMOVE_WORD = "remove_word"

EVENT_PAUSED = f"{DOMAIN}_paused"
EVENT_PIN_FAILED = f"{DOMAIN}_pin_failed"

HEALTH_OLLAMA = "ollama"
HEALTH_YTDLP = "yt_dlp"
HEALTH = [HEALTH_OLLAMA, HEALTH_YTDLP]
