# Shiny Calculator

Shiny hunters often run several games at once. Paste a Twitch or YouTube link and Shiny Calculator watches
the video, finds each game screen, spots the shiny sparkle, and tells you which games hit a shiny, when, and
what percent of the games got one.

- Works on a channel videos page, a single VOD, or a clip.
- On a channel page it only scans videos with "shiny" (or a similar spelling, "sparkle", or a sparkle emoji) in the title.
- Finds the game windows on its own and re-checks the layout every 5 minutes.
- Gives you the game (row and column), a timestamp link that opens the video at that moment, and a screenshot for each hit.
- Light and dark mode.
- Videos are streamed, not saved to disk.

> **Status:** the detector is tuned for the Gen 3 shiny sparkle and has been tested on synthetic footage.
> Real-stream results may need threshold tuning. Please open an issue with a timestamp and a clip if it misses one
> or reports a false hit.

## Quick start

1. Install [Python 3.10+](https://www.python.org/downloads/) (on Windows, tick **Add Python to PATH** during setup).
2. Get the code:

   ```bash
   git clone https://github.com/thattallguyyeli-dev/shiny-calculator.git
   cd shiny-calculator
   ```

   No git? Click **Code -> Download ZIP** on the GitHub page and extract it.
3. Start it (see below). The first run creates a virtual environment and installs everything, so it takes a minute.
4. Paste a Twitch or YouTube link, pick a quality, and press scan.


## Install

Requires Python 3.10 or newer. ffmpeg is bundled through `imageio-ffmpeg`, so you do not need to install it separately.

**Windows:** double-click `run.bat`, or in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

**macOS / Linux:**

```bash
./run.sh
```

The app opens in your browser at http://localhost:8501.

## How it works

1. `yt-dlp` resolves the link to a direct stream address.
2. `ffmpeg` decodes frames at low resolution (480p by default).
3. Game windows are found by looking for solid 3:2 blocks that stay in place. Webcam and other tiles are ignored.
4. Only the enemy area of each window is watched. A hit is 3 or more small bright blobs that newly appear, in at
   least 2 of 3 consecutive samples. Full-area flashes are rejected, and if several windows "sparkle" within
   3 seconds of each other it is treated as a scene transition, not a shiny.

Tuning values live at the top of `scanner.py` (`SAMPLE_FPS`, `ENEMY`, `CHUNK`) and in `scan_video(threshold=...)`.

## Project layout

```
shiny-calculator/
|-- app.py            Streamlit interface
|-- scanner.py        Video scanning and shiny detection
|-- requirements.txt  Python dependencies
|-- run.bat / run.sh  One-step launchers (Windows / macOS, Linux)
|-- assets/           Logo
|-- .streamlit/       Streamlit theme config
|-- LICENSE           MIT
`-- README.md
```

## Notes

- A long VOD takes a while because the whole video is decoded. 720p catches smaller stars but is slower.
- Sites change often. If a link stops working, update the downloader: `pip install -U yt-dlp`.
- This tool only reads publicly available videos. Follow the terms of service of the platforms you use it with.
- Running it as a public web service is not recommended: scans are CPU and bandwidth heavy, and Twitch and YouTube
  commonly block requests from cloud servers. Running locally is the reliable way.

## Contributing

Issues and pull requests are welcome. The most useful contribution is a short clip of a known shiny, with the
timestamp, and which game/stream layout it came from.

## Disclaimer

Not affiliated with or endorsed by Nintendo, Game Freak, The Pokemon Company, Twitch or YouTube.
Pokemon and related names are trademarks of their respective owners.
