# FUNA Web DSTAR Bridge

Software that bridges two QSO One instances running on a single Windows PC, in both directions: the Chrome Web version (a Beacon room such as Japan-X) and the Windows app (D-STAR and other networks).

This is the code that, on November 21, 2026, bridged the D-STAR XLX reflector XLX158 (module X) and the Beacon "Japan-X" room — a QSO with 7K3WNX was completed through it. It was also tested the same day relaying DMR BrandMeister TG91 audio into the Japan-X room.

## How it works

The two instances sit in the same room using the Web version's multi-login (the Web side appears with a "-WEB" suffix on the callsign).

- Web version (Chrome): monitored and keyed over CDP (127.0.0.1:9222) — the DOM talker frame is watched for received audio, and Pointer/Mouse events are sent to button[data-beacon-tx] to transmit.
- Windows version: the UIA tree is watched for the RX-detected text, and PTT is controlled by CLICK or SPACE.

The bridge runs in the background and avoids stealing window focus as much as possible.

## Files

- funa_web_dstar_bridge.py — the software itself (FUNA QSO One Web(Beacon) <-> Windows(D-STAR) Bridge v1.0). Settings are kept in funa_web_dstar_config.json, created next to the script at runtime.

## Requirements

- Windows, Python 3, pywinauto and pywin32
- Chrome with remote debugging on port 9222 (the app can launch Chrome with a dedicated bridge profile)

Japan-X room: https://qso1.net/beacon/r/r-7bad2a17

JL1LBI
