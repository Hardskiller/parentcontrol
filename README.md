# ParentControl

[Deutsche Version](README.de.md)

Home Assistant integration that estimates a minimum age for running YouTube videos with a local Ollama model and pauses unsuitable videos automatically.

## Features

- Monitors any number of media players
- Minimum age from 0 to 18, with a default age and an optional age per device
- Optional per device: jump to the start, educational videos only, block swear words, strict rating, block Shorts
- PIN lock: without the PIN, users without admin rights cannot weaken the protection
- Dashboard card with device list, PIN pad, settings, channel lists, and history
- Allowed and blocked channels, globally and per device, with an optional minimum age
- Editable prompts for the age rating and the educational rating
- Watch time per device, the latest 20 videos per device, and daily video statistics
- Warnings when Ollama or the YouTube lookup stop working
- Runs on any Home Assistant installation that supports HACS

## Requirements

- Home Assistant with [HACS](https://www.hacs.xyz)
- A reachable [Ollama](https://ollama.com) server with at least one model
- Media players that report app, title, and state. So far only Google Cast has been tested.

## Installation

1. In HACS, open **⋮ → Custom repositories** and add `https://github.com/Hardskiller/parentcontrol` as type **Integration**.
2. Download **ParentControl** and restart Home Assistant. Home Assistant installs `yt-dlp` automatically.
3. Go to **Settings → Devices & services → Add integration** and select **ParentControl**.
4. Enter the Ollama address, model, media players, default age, and a PIN with 4 to 8 digits.

## Usage

These apply to all devices:

- **Default age:** used by every device without an age of its own.
- **Check:** switch that turns the check off for all devices.
- **Videos, Approved, Educational, and Skipped today:** count each video once per day. The `gesamt` attribute holds the count since installation.
- **Integration options:** model, device selection, PIN, age per device, and the editable prompts. After a prompt change, videos are checked again. Only admins can open them.
- **Settings:** lock that guards the settings, see [PIN lock](#pin-lock).
- **Ollama and YouTube lookup:** show whether both services work. After 10 minutes of failure, Home Assistant shows a warning under **Settings → Repairs**.

Each monitored player appears as its own device under ParentControl, with these entities:

- **Jump to start:** jumps to the beginning of the video after pausing. The default is pausing only.
- **Educational only:** also blocks age-appropriate videos without learning value. When off, the rating is only shown.
- **Block swear words:** also blocks age-appropriate videos, for example music videos. Detection uses a word list on the full transcript and the model. Without subtitles the model only sees title and description, so lyrics can go unnoticed.
- **Strict rating:** blocks videos without subtitles and videos whose check failed, for example when Ollama is unreachable. This also hits many harmless videos, especially music.
- **Block Shorts:** pauses every YouTube Short, also from allowed channels. On by default.
- **Allowed channels skip all checks:** when on, an allowed channel plays without any check. When off, it is still checked for age and swear words, but missing subtitles and missing educational value don't block it.
- **YouTube check:** shows status, title, minimum age, ratings, and reasons.
- **Age:** the age of this device. It shows the default age until you change it.
- **Watch time today:** counts the minutes the device is playing, in any app.
- **Latest videos:** the newest title as state, the latest 20 videos in the `videos` attribute with time, channel, decision, reasons, and markers for educational value, swear words, and Shorts. Every blocked video has a `sperrtext` that names the trigger. For swear words it lists the words found, in `schimpfwoerter_liste` as well.

## PIN lock

The **Settings** lock decides who may weaken the protection. While it is locked, users without admin rights cannot turn a check off, raise an age, allow a channel, or take a channel off the blocked list. Making the protection stricter always works: turning a check on, lowering an age, or blocking a channel.

Unlock it with the PIN on the lock. It stays open for 5 minutes, and every change starts the 5 minutes again. Locking it again needs no PIN. After 5 wrong PINs, no PIN is accepted for 15 minutes, and every further lockout lasts twice as long. Every wrong PIN appears in the logbook and fires the `parentcontrol_pin_failed` event, for example for a notification.

Admins and automations are not affected by the lock. The PIN is stored only as a hash; if you forget it, set a new one in the integration options.

Home Assistant cannot hide states from users. Everyone who is logged in can read statuses and the latest videos.

If a video fails the check, it is paused. The integration checks this every 3 seconds while the video keeps playing and fires the `parentcontrol_paused` event with `block_reason`, `block_text`, and `swear_words`. The logbook shows the same text. Swear words come from the word list over the full transcript and from the model, which names the words it found.

## Dashboard card

The integration brings its own card and loads it on every dashboard; no extra download is needed. Add it in the dashboard editor under **ParentControl**, or with YAML:

```yaml
type: custom:parentcontrol-card
```

Without the PIN, the card only shows the device list: status, age, watch time, the running title, and markers for educational videos and swear words. Tapping a device, **History**, or **General** asks for the PIN first. Then you see:

- **Device:** the current video with its reasons, the age, all switches, the channel lists of this device, and its latest videos
- **History:** the latest videos of all devices, each with buttons to allow or block its channel
- **General:** the check switch, the default age, the lists for all devices, today's statistics, and the state of Ollama and the YouTube lookup

When the lock closes again, the card returns to the device list. Admins see everything without a PIN. Optional settings are `title` and `entity`, the lock entity, if it can't be found automatically.

## Channel lists

You edit the lists in the integration options, globally and per device, with one channel per line. Allowed channels can have a minimum age after a semicolon. Without a number the age is 0.

```text
Die Maus; 0
Checker Tobi; 6
```

Names must match completely, ignoring case, spaces, and symbols. Both lists count together for a device. A block always wins, and for allowed channels the device entry comes before the global one. If a child is younger than the listed age, the video gets the normal check. An allowed channel is trusted as a whole, including videos nobody has reviewed.

The allowed list starts with well-known German children's channels. Their ages are estimates, not official ratings, and you can change or delete every line.

Three actions change the lists without opening the options: `parentcontrol.allow_channel` and `parentcontrol.block_channel` move a channel from the opposite list, and `parentcontrol.remove_channel` takes it off the list given in `list` (`allowed` or `blocked`). Allowing a channel and taking it off the blocked list need the PIN. Without `channel` they use the channel running on `player`, which makes a dashboard button easy:

```yaml
type: button
name: Allow channel
tap_action:
  action: perform-action
  perform_action: parentcontrol.allow_channel
  data:
    player: media_player.tv
    age: 6
```

## How it works

The integration finds the video by title, channel, and duration, loads the description and subtitles, and sends excerpts to Ollama. Title and channel go to YouTube for this, the rating itself stays local.

## Limits

- The minimum age is an estimate by a language model, not an official age rating. It can be wrong.
- Only text is checked, not the picture.
- The start of a video always plays unchecked until title and rating are available. This also applies to Shorts: each Short starts before it is recognized, and the next one starts again after a swipe. Only YouTube itself can hide Shorts completely, for example with a supervised account.
- Without strict rating, a video keeps playing when Ollama fails or no data is available.
- Only monitored media players are covered. Browsers on laptops, phones, tablets, and game consoles can bypass the check. The Home Assistant app on iPhone doesn't report what other apps play.
- Fetching data with `yt-dlp` isn't intended by YouTube and can stop working at any time.

This integration doesn't replace supervision.

## License

MIT
