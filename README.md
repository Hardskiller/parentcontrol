# ParentControl

[Deutsche Version](README.de.md)

Home Assistant integration that estimates a minimum age for running YouTube videos with a local Ollama model and pauses unsuitable videos automatically.

## Features

- Monitors any number of media players
- Child profiles with their own age, rules, lists, and allowed swear words, optionally linked to a person in Home Assistant
- Several children per device; on a shared device the strictest rule applies
- "Who is watching?" per device, including "Unrestricted" for adults
- Rules per child: educational videos only, block swear words, strict rating, block Shorts
- Daily YouTube limit and viewing hours per child, separately for weekdays and weekends, with a warning before and extra time for today
- Allowed videos and the transcript of blocked videos, to decide from a notification
- PIN lock: without the PIN, users without admin rights cannot weaken the protection
- Dashboard card with device list, PIN pad, profiles, channel lists, and history
- Allowed and blocked channels and allowed swear words, globally and per child
- Editable prompts for the age rating and the educational rating
- Watch time per device and per child, the last seven days per child, the latest videos per device (20 by default, adjustable), and daily video statistics
- Warnings when Ollama or the YouTube lookup stop working
- Blueprints for notifications with buttons, announcements, the time limit, and a daily report
- Runs on any Home Assistant installation that supports HACS

## Requirements

- Home Assistant 2026.8 or newer with [HACS](https://www.hacs.xyz)
- A reachable [Ollama](https://ollama.com) server with at least one model
- Media players that report app, title, and state, see [Supported devices](#supported-devices)

## Installation

1. In HACS, open **⋮ → Custom repositories** and add `https://github.com/Hardskiller/parentcontrol` as type **Integration**.
2. Download **ParentControl** and restart Home Assistant. Home Assistant installs `yt-dlp` automatically.
3. Go to **Settings → Devices & services → Add integration** and select **ParentControl**.
4. Enter the Ollama address, model, media players, a PIN with 4 to 8 digits, and the first child with name, age, and optionally a person. This child applies to all selected players.

Version 0.3.6 changes the structure to child profiles. When updating from an older version, remove ParentControl and set it up again.

## Child profiles

Each child is a profile and appears as its own device under ParentControl. A profile has a name and can be linked to a person in Home Assistant; the card then shows the person's picture.

You add, rename, and remove children in the integration options, and assign them to the players there. Every player needs at least one child. The rules of a child are set in the card or with these entities:

- **Age:** minimum age that applies to this child.
- **Educational only:** also blocks age-appropriate videos without learning value. When off, the rating is only shown.
- **Block swear words:** also blocks age-appropriate videos, for example music videos. Detection uses a word list on the full transcript and the model. Without subtitles the model only sees title and description, so lyrics can go unnoticed.
- **Strict rating:** blocks videos without subtitles and videos whose check failed, for example when Ollama is unreachable. It also pauses YouTube when the device reports no title for 150 seconds. This also hits many harmless videos, especially music.
- **Block Shorts:** pauses every YouTube Short, also from allowed channels. On by default.
- **Allowed channels skip all checks:** when on, an allowed channel plays without any check. When off, it is still checked for age and swear words, but missing subtitles and missing educational value don't block it.
- **Inherit global allowed channels** and **Inherit global words:** whether the global lists apply to this child as well. On by default.
- **Watch time today:** minutes in which a player with this child is playing, in any app.
- **YouTube limit Mon–Fri** and **YouTube limit Sat–Sun:** minutes of YouTube per day, 0 means no limit. Raising or removing a limit needs the PIN.
- **Viewing time Mon–Fri from/until** and **Sat–Sun from/until:** when the child may watch YouTube. The same start and end means all day, which is the default. Widening the window needs the PIN.
- **Remaining time today:** YouTube minutes left, unknown without a limit.

Only YouTube counts for the limit. On a shared device with "Automatic" the time counts for every assigned child, and YouTube pauses as soon as one of them reaches its limit or leaves its viewing time. Limit and viewing time also apply to allowed channels and allowed videos, but not to "Unrestricted". A few minutes before, ParentControl fires `parentcontrol_limit_warning`, and when reached it pauses and fires `parentcontrol_limit_reached`, each once per day and child. The warning time is set in the integration options, 5 minutes by default.

**Extra time:** the card offers "+15 min" and "+30 min" per child, and the action `parentcontrol.add_time` takes any number of minutes. It needs the PIN, applies only today, and ends at midnight.

If several children are assigned to one player, the strictest rule applies: the youngest age, every blocking switch that any child has on, and "skip all checks" only if every child has it on. A channel or word is allowed only if every child may have it.

## Who is watching?

Each player has a selection **Who is watching?**, in the card and as an entity:

- **Automatic:** all children assigned to the player, with the strictest rule. Choosing it never needs the PIN.
- **A single child:** only this child's rules apply. Needs the PIN.
- **Unrestricted:** no check at all, for example when adults watch. Needs the PIN. The history still records the videos, but the time counts for no child.

A choice lasts until the player turns off, at midnight at the latest. Then it returns to **Automatic**.

## Usage

These apply to all devices:

- **Check:** switch that turns the check off for all devices.
- **Videos, Approved, Educational, and Skipped today:** count each video once per day. The `gesamt` attribute holds the count since installation.
- **Integration options:** model, device selection, PIN, stored videos per device (5 to 100, 20 by default), warning time, children and their assignment, lists, and the editable prompts. After a prompt change, videos are checked again. Only admins can open them.
- **Settings:** lock that guards the settings, see [PIN lock](#pin-lock).
- **Ollama and YouTube lookup:** show whether both services work. After 10 minutes of failure, Home Assistant shows a warning under **Settings → Repairs**.
- **Daily report:** the number of blocked videos today; the attributes hold YouTube time, limit, extra time, videos, and blocks per child, and the blocked videos with the kind of block.

Each monitored player appears as its own device under ParentControl, with these entities:

- **Who is watching?:** see above.
- **Jump to start:** jumps to the beginning of the video after pausing. The default is pausing only.
- **YouTube check:** shows status, title, minimum age, ratings, reasons, and the active children.
- **Watch time today:** counts the minutes the device is playing, in any app.
- **Latest videos:** the newest title as state, the latest videos in the `videos` attribute with time, channel, decision, reasons, active children, and markers for educational value, swear words, and Shorts. Every blocked video has a `sperrtext` that names the trigger. For swear words it lists the words found, in `schimpfwoerter_liste` as well.

If a video fails the check, it is paused. The integration checks this every 3 seconds while the video keeps playing and fires the `parentcontrol_paused` event with `block_reason`, `block_text`, `swear_words`, `profiles`, `profile_ids`, `video_id`, and `url`. The logbook shows the same text.

## Allowed videos and transcripts

A blocked video can be allowed for the children who were watching: with the button in the notification, or with the action `parentcontrol.allow_video` and the `player`. It plays on right away and from then on stays allowed for these children. Shorts, limit, and viewing time still apply, and a blocked channel still wins. The card lists the allowed videos per child; removing one needs no PIN.

ParentControl keeps the transcript of the last 50 blocked videos, up to 20,000 characters each. It comes from the subtitles YouTube provides; music videos often have none. In the card, an expanded history entry offers **Show transcript** and a link to the video on YouTube. The transcript can contain swear words in plain text, so it needs the PIN, also through the action `parentcontrol.get_transcript`.

## PIN lock

The **Settings** lock decides who may weaken the protection. While it is locked, users without admin rights cannot turn a check off, raise an age, allow a channel or a word, take a channel off the blocked list, inherit global lists again, or choose a single child or "Unrestricted". Making the protection stricter always works: turning a check on, lowering an age, blocking a channel, or choosing "Automatic".

Unlock it with the PIN on the lock. It stays open for 5 minutes, and every change starts the 5 minutes again. Locking it again needs no PIN. After 5 wrong PINs, no PIN is accepted for 15 minutes, and every further lockout lasts twice as long. Every wrong PIN appears in the logbook and fires the `parentcontrol_pin_failed` event.

Admins and automations are not affected by the lock. The PIN is stored only as a hash; if you forget it, set a new one in the integration options.

Home Assistant cannot hide states from users. Everyone who is logged in can read statuses and the latest videos.

## Dashboard card

The integration brings its own card and loads it on every dashboard; no extra download is needed. Add it in the dashboard editor under **ParentControl**, or with YAML:

```yaml
type: custom:parentcontrol-card
```

Without the PIN, the card shows the device list: status, age, watch time, the running title, the active children, markers for educational videos and swear words, and the **Who is watching?** dropdown. Choosing "Automatic" there works right away; anything else asks for the PIN. Tapping a device, **History**, **Profiles**, or **General** asks for the PIN first. Then you see:

- **Device:** the current video, **Who is watching?**, **Jump to start**, and its latest videos
- **History:** the latest videos of all devices. Every blocked entry shows the kind of block in red; tap an entry to see the full block text with the swear words found and the model's rating. The buttons to allow or block a channel ask whether it applies to all children or only to the children who were watching. **Show more** loads further entries.
- **Profiles:** per child the age, YouTube today with limit and remaining time, the buttons "+15 min" and "+30 min", limits, viewing times, a chart of the last seven days with the limit, all rules, the inherit switches, channel lists, allowed words, and allowed videos
- **General:** the check switch, the lists for all children, today's statistics, and the state of Ollama and the YouTube lookup

When the lock closes again, the card returns to the device list. Admins see everything without a PIN.

The card has a visual editor with these settings:

| Option | Meaning |
|---|---|
| `title` | Card title |
| `entity` | Lock entity, if it can't be found automatically |
| `show_valuable`, `show_profanity`, `show_shorts` | Markers for educational videos, swear words, and Shorts, on by default |
| `show_age`, `show_watch_time` | Age and watch time in the device list, on by default |
| `history_limit` | History entries before **Show more**, 10 by default |
| `names` | Display names per device, keyed by its status sensor |

## Lists

There are lists for all children and lists per child. You edit them in the card or in the integration options, with one entry per line.

**Channels:** allowed channels can have a minimum age after a semicolon. Without a number the age is 0.

```text
Die Maus; 0
Checker Tobi; 6
```

Names must match completely, ignoring case, spaces, and symbols. A block always wins, and the global blocked list always applies. For allowed channels, the child's entry comes before the global one, and the global list only applies if the child inherits it. If a child is younger than the listed age, the video gets the normal check. An allowed channel is trusted as a whole, including videos nobody has reviewed.

The global allowed list starts with well-known German children's channels. Their ages are estimates, not official ratings, and you can change or delete every line.

**Allowed swear words:** a word matches as a whole word, ignoring case. `Mist*` allows every word that starts with "Mist". Words that YouTube censored as `[ __ ]` can never be allowed. If the model reports swear words without naming them, the video stays blocked.

These actions change the lists without opening the options. Without `profile` they change the lists for all children:

| Action | Effect | PIN |
|---|---|---|
| `parentcontrol.allow_channel` | allows a channel, optionally with `age`, and removes it from the blocked list | yes |
| `parentcontrol.block_channel` | blocks a channel and removes it from the allowed list | no |
| `parentcontrol.remove_channel` | removes a channel from the list in `list` (`allowed` or `blocked`) | for `blocked` |
| `parentcontrol.allow_word` | allows a swear word | yes |
| `parentcontrol.remove_word` | forbids a swear word again | no |
| `parentcontrol.add_time` | gives a child extra minutes for today | yes |
| `parentcontrol.allow_video` | allows the video running on `player` and plays it on | yes |
| `parentcontrol.remove_video` | takes a video off the allowed videos | no |
| `parentcontrol.get_transcript` | returns the transcript of a blocked video | yes |

Without `channel`, the channel actions use the channel running on `player`, which makes a dashboard button easy:

```yaml
type: button
name: Block channel
tap_action:
  action: perform-action
  perform_action: parentcontrol.block_channel
  data:
    player: media_player.tv
```

## Blueprints

Ready-made automations for notifications to the Home Assistant app:

| Blueprint | Import |
|---|---|
| Notify on block: title, device, children, and the kind of block, with buttons to allow the video, allow the channel for the children watching, or keep it blocked, and links to the video and to the dashboard | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fnotify_on_block.yaml) |
| Time limit: before the limit or the end of the viewing time, and when reached | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Ftime_limit.yaml) |
| Announce on pause: tells the child on a speaker why YouTube stopped or how much time is left, without swear words. Use a speaker other than the TV, because an announcement through Cast on the TV closes YouTube. | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fannounce.yaml) |
| Daily report: YouTube time, limit, extra time, and videos per child, and the blocked videos, at a time you choose (20:00 by default) | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fdaily_report.yaml) |
| Wrong PIN, optionally from a certain attempt on | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fwrong_pin.yaml) |
| Service down: Ollama or the YouTube lookup failed for a set time, and back again | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FHardskiller%2Fparentcontrol%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fparentcontrol%2Fservice_down.yaml) |

## Supported devices

ParentControl recognizes YouTube by the app name, app ID, or source of a media player. To rate a video, the player must also report its title.

| Device and integration | Title | Status |
|---|---|---|
| Google TV, Chromecast, and TVs with Chromecast built-in via Google Cast | yes, sometimes up to 2 minutes late | tested |
| Apple TV via the Apple TV integration | title expected, channel unknown | not tested |
| Fire TV and Android TV via ADB or Android TV Remote | no | only "No data" |
| LG webOS via the LG webOS integration | no, only for live TV | only "No data" |

Without a title, ParentControl shows "No data". Only with strict rating does it pause YouTube on such a device. Without a channel, channel lists don't apply.

## How it works

The integration finds the video by title, channel, and duration, loads the description and subtitles, and sends excerpts to Ollama. Title and channel go to YouTube for this, the rating itself stays local.

## Limits

- The minimum age is an estimate by a language model, not an official age rating. It can be wrong.
- Only text is checked, not the picture.
- The start of a video always plays unchecked until title and rating are available. This also applies to Shorts: each Short starts before it is recognized, and the next one starts again after a swipe. Only YouTube itself can hide Shorts completely, for example with a supervised account.
- Without strict rating, a video keeps playing when Ollama fails or no data is available.
- ParentControl can't tell who is really in front of a shared device. With "Automatic" the strictest rule of all assigned children applies, and the watch time counts for each of them.
- Only monitored media players are covered. Browsers on laptops, phones, tablets, and game consoles can bypass the check. The Home Assistant app on iPhone doesn't report what other apps play.
- Fetching data with `yt-dlp` isn't intended by YouTube and can stop working at any time.

This integration doesn't replace supervision.

## License

MIT
