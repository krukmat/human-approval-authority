# HAA hardware terminal — gated subplan

Implementation intentionally has not started. W5 is blocked until `W4-T06` records a PASS after a real macOS Touch ID end-to-end scenario.

Planned POC: XIAO ESP32-S3 + FPC2534 + OLED + USB. Firmware must verify HAA-signed payload bytes before rendering, match fingerprints locally, and sign only after the verify → display → match sequence.
