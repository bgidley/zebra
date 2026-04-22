/**
 * WebAuthn (Passkey) client-side helpers for Zebra Agent.
 *
 * Handles registration and authentication ceremonies by calling
 * the browser's navigator.credentials API and communicating with
 * the Django backend.
 */

/**
 * Register a new passkey for the given username.
 *
 * @param {string} username
 * @returns {Promise<{success: boolean, error?: string}>}
 */
async function registerPasskey(username) {
    try {
        // 1. Get registration options from server
        const beginRes = await fetch('/auth/begin-register/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ username }),
        });

        if (!beginRes.ok) {
            const err = await beginRes.json();
            return { success: false, error: err.error || 'Failed to start registration' };
        }

        const options = await beginRes.json();

        // 2. Call navigator.credentials.create()
        const publicKey = parseOptions(options);
        const credential = await navigator.credentials.create({ publicKey });

        if (!credential) {
            return { success: false, error: 'Passkey creation was cancelled.' };
        }

        // 3. Send credential back to server
        const credentialData = buildCredentialJSON(credential);
        const completeRes = await fetch('/auth/complete-register/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ username, credential: credentialData }),
        });

        if (!completeRes.ok) {
            const err = await completeRes.json();
            return { success: false, error: err.error || 'Registration verification failed' };
        }

        return { success: true };
    } catch (e) {
        console.error('Passkey registration error:', e);
        return { success: false, error: e.message || 'An unexpected error occurred' };
    }
}

/**
 * Authenticate with an existing passkey.
 *
 * @returns {Promise<{success: boolean, error?: string}>}
 */
async function authenticateWithPasskey() {
    try {
        // 1. Get authentication options from server
        const beginRes = await fetch('/auth/begin-authenticate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({}),
        });

        if (!beginRes.ok) {
            const err = await beginRes.json();
            return { success: false, error: err.error || 'Failed to start authentication' };
        }

        const options = await beginRes.json();

        // 2. Call navigator.credentials.get()
        const publicKey = parseOptions(options);
        const credential = await navigator.credentials.get({ publicKey });

        if (!credential) {
            return { success: false, error: 'Passkey authentication was cancelled.' };
        }

        // 3. Send credential back to server
        const credentialData = buildCredentialJSON(credential);
        const completeRes = await fetch('/auth/complete-authenticate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ credential: credentialData }),
        });

        if (!completeRes.ok) {
            const err = await completeRes.json();
            return { success: false, error: err.error || 'Authentication verification failed' };
        }

        return { success: true };
    } catch (e) {
        console.error('Passkey authentication error:', e);
        return { success: false, error: e.message || 'An unexpected error occurred' };
    }
}

/**
 * Parse server options into a format suitable for navigator.credentials.
 *
 * Converts base64url strings to ArrayBuffers where needed.
 */
function parseOptions(options) {
    const publicKey = { ...options };

    if (publicKey.challenge) {
        publicKey.challenge = base64urlToBuffer(publicKey.challenge);
    }

    if (publicKey.user && publicKey.user.id) {
        publicKey.user.id = base64urlToBuffer(publicKey.user.id);
    }

    if (publicKey.excludeCredentials) {
        publicKey.excludeCredentials = publicKey.excludeCredentials.map(cred => ({
            ...cred,
            id: base64urlToBuffer(cred.id),
        }));
    }

    if (publicKey.allowCredentials) {
        publicKey.allowCredentials = publicKey.allowCredentials.map(cred => ({
            ...cred,
            id: base64urlToBuffer(cred.id),
        }));
    }

    return publicKey;
}

/**
 * Build a JSON-serializable credential object from a Credential instance.
 */
function buildCredentialJSON(credential) {
    const clientDataJSON = arrayBufferToBase64url(credential.response.clientDataJSON);
    const rawId = arrayBufferToBase64url(credential.rawId);

    const result = {
        id: credential.id,
        rawId: rawId,
        type: credential.type,
        clientExtensionResults: credential.getClientExtensionResults(),
        response: {
            clientDataJSON: clientDataJSON,
        },
    };

    if (credential.response.authenticatorData) {
        result.response.authenticatorData = arrayBufferToBase64url(credential.response.authenticatorData);
    }

    if (credential.response.publicKey) {
        result.response.publicKey = arrayBufferToBase64url(credential.response.publicKey);
    }

    if (credential.response.publicKeyAlgorithm !== undefined) {
        result.response.publicKeyAlgorithm = credential.response.publicKeyAlgorithm;
    }

    if (credential.response.attestationObject) {
        result.response.attestationObject = arrayBufferToBase64url(credential.response.attestationObject);
    }

    if (credential.response.signature) {
        result.response.signature = arrayBufferToBase64url(credential.response.signature);
    }

    if (credential.response.userHandle) {
        result.response.userHandle = arrayBufferToBase64url(credential.response.userHandle);
    }

    return result;
}

/**
 * Convert base64url string to ArrayBuffer.
 */
function base64urlToBuffer(base64url) {
    const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
    const padding = '='.repeat((4 - base64.length % 4) % 4);
    const binary = atob(base64 + padding);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
}

/**
 * Convert ArrayBuffer to base64url string.
 */
function arrayBufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary)
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');
}

/**
 * Get the CSRF token from the cookie or meta tag.
 */
function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    if (match) return match[1];
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.content;
    return '';
}
