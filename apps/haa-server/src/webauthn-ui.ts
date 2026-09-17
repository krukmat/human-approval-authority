export function webAuthnApprovalPage(): string {
  return String.raw`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>HAA WebAuthn approval spike</title>
  <style>
    :root { font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif; color-scheme: light dark; }
    body { max-width: 760px; margin: 48px auto; padding: 0 20px; line-height: 1.45; }
    .warning { border: 1px solid currentColor; border-radius: 8px; padding: 12px 14px; margin: 18px 0; }
    .claims { display: grid; grid-template-columns: 180px 1fr; gap: 8px 14px; margin: 18px 0; }
    .claim-label { font-weight: 700; }
    button { padding: 10px 16px; margin: 6px 8px 6px 0; }
    code { overflow-wrap: anywhere; }
    #status { min-height: 1.5em; font-weight: 600; }
  </style>
</head>
<body>
  <h1>HAA WebAuthn approval spike</h1>
  <div class="warning">
    <strong>Assurance boundary:</strong> this browser page is not a trusted native display.
    WebAuthn user verification is cryptographically bound to the HAA challenge digest, but the human-visible
    action rendering is protected only by the authenticated web origin.
  </div>
  <p>Request: <code id="request"></code></p>
  <div>
    <button id="register">1. Register Touch ID credential</button>
    <button id="prepare" disabled>2. Prepare exact approval</button>
    <button id="approve" disabled>3. Approve with WebAuthn</button>
  </div>
  <div id="claims" class="claims"></div>
  <p id="status"></p>

<script type="module">
const qs = new URLSearchParams(location.search);
const requestId = qs.get('requestId');
const fragment = new URLSearchParams(location.hash.slice(1));
let apiKey = fragment.get('apiKey') ?? '';
if (location.hash) history.replaceState(null, '', location.pathname + location.search);
if (!requestId) throw new Error('Missing requestId');
document.querySelector('#request').textContent = requestId;

let authenticatorId = '';
let challengeDigest = '';
const status = document.querySelector('#status');
const registerButton = document.querySelector('#register');
const prepareButton = document.querySelector('#prepare');
const approveButton = document.querySelector('#approve');

function fail(error) {
  const message = error instanceof Error ? error.message : String(error);
  status.textContent = 'ERROR: ' + message;
  console.error(error);
}

function fromB64url(value) {
  const padding = '='.repeat((4 - value.length % 4) % 4);
  const binary = atob(value.replace(/-/g, '+').replace(/_/g, '/') + padding);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function toB64url(value) {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

async function call(path, { method = 'GET', body } = {}) {
  if (!apiKey) {
    apiKey = prompt('Approver API key for this local spike') ?? '';
  }
  if (!apiKey) throw new Error('Approver API key required');
  const response = await fetch(path, {
    method,
    headers: {
      'x-api-key': apiKey,
      ...(body === undefined ? {} : { 'content-type': 'application/json' }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await response.text();
  const value = text ? JSON.parse(text) : undefined;
  if (!response.ok) throw new Error(value?.error ?? ('HTTP_' + response.status));
  return value;
}

function serializeRegistration(credential) {
  return {
    id: credential.id,
    rawId: toB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toB64url(credential.response.clientDataJSON),
      attestationObject: toB64url(credential.response.attestationObject),
      transports: credential.response.getTransports?.() ?? [],
    },
  };
}

function serializeAssertion(credential) {
  return {
    id: credential.id,
    rawId: toB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toB64url(credential.response.clientDataJSON),
      authenticatorData: toB64url(credential.response.authenticatorData),
      signature: toB64url(credential.response.signature),
      userHandle: credential.response.userHandle ? toB64url(credential.response.userHandle) : null,
    },
  };
}

registerButton.addEventListener('click', async () => {
  try {
    status.textContent = 'Creating user-verified platform credential…';
    const registration = await call('/v1/webauthn/registration/options', { method: 'POST', body: {} });
    const options = registration.publicKey;
    const publicKey = {
      ...options,
      challenge: fromB64url(options.challenge),
      user: { ...options.user, id: fromB64url(options.user.id) },
      excludeCredentials: (options.excludeCredentials ?? []).map((item) => ({ ...item, id: fromB64url(item.id) })),
    };
    const credential = await navigator.credentials.create({ publicKey });
    if (!credential) throw new Error('WebAuthn registration returned no credential');
    const verified = await call('/v1/webauthn/registration/verify', {
      method: 'POST',
      body: { registrationId: registration.registrationId, credential: serializeRegistration(credential) },
    });
    authenticatorId = verified.authenticator.id;
    registerButton.disabled = true;
    prepareButton.disabled = false;
    status.textContent = 'Credential registered. Prepare the approval to inspect exact action claims.';
  } catch (error) { fail(error); }
});

prepareButton.addEventListener('click', async () => {
  try {
    const challenge = await call('/v1/approval-requests/' + encodeURIComponent(requestId) + '/challenges', {
      method: 'POST',
      body: { authenticatorId },
    });
    const payloadBytes = fromB64url(challenge.payload);
    const digestBytes = await crypto.subtle.digest('SHA-256', payloadBytes);
    challengeDigest = 'sha256:' + toB64url(digestBytes);
    const payload = JSON.parse(new TextDecoder().decode(payloadBytes));
    const claims = document.querySelector('#claims');
    claims.replaceChildren();
    for (const claim of payload.displayClaims ?? []) {
      const label = document.createElement('div');
      label.className = 'claim-label';
      label.textContent = claim.label;
      const value = document.createElement('code');
      value.textContent = claim.value;
      claims.append(label, value);
    }
    prepareButton.disabled = true;
    approveButton.disabled = false;
    status.textContent = 'Review the action above, then explicitly approve with WebAuthn.';
  } catch (error) { fail(error); }
});

approveButton.addEventListener('click', async () => {
  try {
    const auth = await call('/v1/webauthn/authentication/options', {
      method: 'POST',
      body: { requestId, authenticatorId, challengeDigest },
    });
    const options = auth.publicKey;
    const publicKey = {
      ...options,
      challenge: fromB64url(options.challenge),
      allowCredentials: options.allowCredentials.map((item) => ({ ...item, id: fromB64url(item.id) })),
    };
    const assertion = await navigator.credentials.get({ publicKey });
    if (!assertion) throw new Error('WebAuthn authentication returned no assertion');
    const encoded = serializeAssertion(assertion);
    const authData = fromB64url(encoded.response.authenticatorData);
    if (authData.length < 37) throw new Error('Invalid authenticatorData');
    const counter = new DataView(authData.buffer, authData.byteOffset, authData.byteLength).getUint32(33, false);
    const proof = {
      schema: 'haa.webauthn-proof.v1',
      credentialId: encoded.id,
      clientDataJSON: encoded.response.clientDataJSON,
      authenticatorData: encoded.response.authenticatorData,
      assertionSignature: encoded.response.signature,
    };
    const proofBytes = new TextEncoder().encode(JSON.stringify(proof));
    await call('/v1/approval-evidence', {
      method: 'POST',
      body: {
        schema: 'haa.evidence.v1',
        type: 'webauthn-v1',
        authenticatorId,
        requestId,
        challengeDigest,
        signatureAlgorithm: 'ES256',
        signature: toB64url(proofBytes),
        counter,
      },
    });
    approveButton.disabled = true;
    status.textContent = 'APPROVED: WebAuthn assertion accepted by HAA.';
  } catch (error) { fail(error); }
});
</script>
</body>
</html>`;
}
