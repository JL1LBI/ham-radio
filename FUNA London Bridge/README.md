# FUNA London Bridge

Software that bridges the QSO One Beacon "Japan-X" room and a Yaesu FT-736M, in both directions.

This is the very code that is running live in the public experiment at 09:00 JST (00:00 UTC) on November 21, 2026 — bridging the Japan-X room and the FT-736M at that moment.

## The point of this software

The crux is that it can control QSO One's PTT from the outside. Rig control, by contrast, can be done any number of classic ways — and indeed, all this implementation uses on the FT-736M side are the most basic CAT functions: squelch detection, S-meter reading, and PTT control.

The FT-736M is an old rig, but because only such basic functions are used, any Yaesu rig with standard CAT support should work (other models are untested).

## Planned

A more general version — a serial-conversion type, using the classic method of switching the rig's PTT on and off through pin I/O — will be published in due course.

## Files

- funa_qso_one_bridge.py — the software itself (FUNA QSO One Bridge v1.3)
- funa_qso_one_bridge.spec — PyInstaller build settings for a single-file EXE

Japan-X room: https://qso1.net/beacon/r/r-7bad2a17

JL1LBI
