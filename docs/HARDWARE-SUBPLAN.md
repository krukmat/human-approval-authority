# Hardware authenticator subplan

## Why it exists

The DIY terminal is justified only by properties the Mac path cannot fully provide:
- separate physical trust boundary from the agent host,
- dedicated display whose content is verified from HAA-signed data,
- portable/vendor-neutral approval endpoint,
- visible physical gate for high-risk agent actions.

It is not justified merely because fingerprint scanning is interesting. The Mac Secure Enclave path is expected to have stronger commodity-device hardening initially.

## Planned POC

- Seeed Studio XIAO ESP32-S3
- SparkFun FPC2534-class fingerprint module
- OLED display
- physical reject/cancel input
- USB transport only
- ESP32-protected signing key initially; ATECC608C-class secure element only in hardening if justified

## Limitations

- Not FIDO Certified or a qualified electronic-signature device.
- Fingerprint match does not cryptographically prove itself to the secure element; firmware is part of the TCB.
- Raw images/templates/minutiae must never leave the sensor boundary.
- Small display supports only compact deterministic ActionSpec profiles.
- Single principal per terminal in v0.x.
- Physical attacks and maker supply-chain risk remain residual risks.

## Gate

No firmware implementation before W4-T06 PASS.
