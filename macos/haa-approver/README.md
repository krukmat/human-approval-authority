# macOS HAA Approver

Native macOS authenticator for the HAA protocol. It verifies the HAA-signed challenge bytes before rendering the structured approval claims. The signing key is P-256 in Secure Enclave with private-key usage protected by `biometryCurrentSet`; use of the key triggers system biometric authorization.

This source must be validated on a real Apple Silicon Mac with Touch ID before W3 can pass. Linux builds only exercise the non-macOS compile stubs.
