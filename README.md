# ParentControl

[Deutsche Version](README.de.md)

Home Assistant integration that estimates a minimum age for running YouTube videos with a local Ollama model and pauses unsuitable videos automatically.

## Features

- Monitors any number of media players
- Minimum age from 0 to 18, with a default age and an optional age per device
- Optional per device: jump to the start, educational videos only, block swear words, strict rating
- Allowed and blocked channels, globally and per device, with an optional minimum age
- Editable prompts for the age rating and the educational rating
- Watch time per device and daily video statistics
- Runs on any Home Assistant installation that supports HACS

## Requirements

- Home Assistant with [HACS](https://www.hacs.xyz)
- A reachable [Ollama](https://ollama.com) server with at least one model
- Media players that report app, title, and state. So far only Google Cast has been tested.

## Installation

1. In HACS, open **⋮ → Custom repositories** and add `https://github.com/Hardskiller/parentcontrol` as type **Integration**.
2. Download **ParentControl** and restart Home Assistant. Home Assistant installs `yt-dlp` automatically.
3. Go to **Settings → Devices & services → Add integration** and select **ParentControl**.
4. Enter the Ollama address, model, media players, and default age.

## Usage

These apply to all devices:

- **Default age:** used by every device without an age of its own.
- **Check:** switch that turns the check off for all devices.
- **Videos, Approved, Educational, and Skipped today:** count each video once per day. The `gesamt` attribute holds the count since installation.
- **Integration options:** model, device selection, age per device, and the editable prompts. After a prompt change, videos are checked again.

Each monitored player appears as its own device under ParentControl, with these entities:

- **Jump to start:** jumps to the beginning of the video after pausing. The default is pausing only.
- **Educational only:** also blocks age-appropriate videos without learning value. When off, the rating is only shown.
- **Block swear words:** also blocks age-appropriate videos, for example music videos. Detection uses a word list on the full transcript and the model. Without subtitles the model only sees title and description, so lyrics can go unnoticed.
- **Strict rating:** blocks videos without subtitles and videos whose check failed, for example when Ollama is unreachable. This also hits many harmless videos, especially music.
- **Allowed channels skip all checks:** when on, an allowed channel plays without any check. When off, it is still checked for age and swear words, but missing subtitles and missing educational value don't block it.
- **YouTube check:** shows status, title, minimum age, ratings, and reasons.
- **Watch time today:** counts the minutes the device is playing, in any app.

Anyone with access to the dashboard can change these switches.

If a video fails the check, it is paused. The integration checks this every 3 seconds while the video keeps playing and fires the `parentcontrol_paused` event.

## Channel lists

You edit the lists in the integration options, globally and per device, with one channel per line. Allowed channels can have a minimum age after a semicolon. Without a number the age is 0.

```text
Die Maus; 0
Checker Tobi; 6
```

Names must match completely, ignoring case, spaces, and symbols. Both lists count together for a device. A block always wins, and for allowed channels the device entry comes before the global one. If a child is younger than the listed age, the video gets the normal check. An allowed channel is trusted as a whole, including videos nobody has reviewed.

The allowed list starts with well-known German children's channels. Their ages are estimates, not official ratings, and you can change or delete every line.

Two actions change the lists without opening the options: `parentcontrol.allow_channel` and `parentcontrol.block_channel`. Each moves a channel from the opposite list. Without `channel` they use the channel running on `player`, which makes a dashboard button easy:

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
- The start of a video always plays unchecked until title and rating are available.
- Without strict rating, a video keeps playing when Ollama fails or no data is available.
- Only monitored media players are covered. Browsers on laptops, phones, tablets, and game consoles can bypass the check. The Home Assistant app on iPhone doesn't report what other apps play.
- Fetching data with `yt-dlp` isn't intended by YouTube and can stop working at any time.

This integration doesn't replace supervision.

## License

MIT
