# ParentControl

[Deutsche Version](README.de.md)

Home Assistant integration that estimates a minimum age for running YouTube videos with a local Ollama model and pauses unsuitable videos automatically.

## Features

- Monitors any number of media players
- Minimum age from 0 to 18, with a default age and an optional age per device
- Optional per device: jump to the start, educational videos only, block swear words, strict rating
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
- **YouTube check:** shows status, title, minimum age, ratings, and reasons.
- **Watch time today:** counts the minutes the device is playing, in any app.

Anyone with access to the dashboard can change these switches.

If a video fails the check, it is paused. The integration checks this every 3 seconds while the video keeps playing and fires the `parentcontrol_paused` event.

## How it works

The integration finds the video by title, channel, and duration, loads the description and subtitles, and sends excerpts to Ollama. Title and channel go to YouTube for this, the rating itself stays local.

## Limits

- The minimum age is an estimate by a language model, not an official age rating. It can be wrong.
- Only text is checked, not the picture.
- The start of a video always plays unchecked until title and rating are available.
- Without strict rating, a video keeps playing when Ollama fails or no data is available.
- Only monitored media players are covered. Browsers on laptops, phones, tablets, and game consoles can bypass the check.
- Fetching data with `yt-dlp` isn't intended by YouTube and can stop working at any time.

This integration doesn't replace supervision.

## License

MIT
