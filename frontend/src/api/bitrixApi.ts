// Bitrix24 iframe session bootstrap.
//
// The app is embedded in a Bitrix24 iframe. On load it asks the BX24 JS SDK
// for the current user + auth, hands both to the backend, and the backend
// returns a SessionUser whose `role` it resolved server-side (department head
// / supervisor allowlist). Nothing sensitive is decided on the client.
//
// Returns null only when the page is not inside a Bitrix iframe. Handshake and
// backend errors are surfaced so production never impersonates a mock user.

import type { SessionUser } from "../types/domain";

type BitrixAuth = {
  access_token: string;
  refresh_token: string;
  domain: string;
  member_id: string;
  expires_in: number | string | Date;
};

type BitrixResult = {
  error: () => unknown;
  data: () => unknown;
};

type BitrixSDK = {
  init: (callback: () => void) => void;
  getAuth: () => BitrixAuth | false;
  callMethod: (
    method: string,
    params: Record<string, unknown>,
    callback: (result: BitrixResult) => void,
  ) => void;
};

declare global {
  interface Window {
    BX24?: BitrixSDK;
  }
}

export function isInsideFrame(): boolean {
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
}

function loadBitrixSDK(): Promise<boolean> {
  if (window.BX24) {
    return Promise.resolve(true);
  }

  if (!isInsideFrame()) {
    return Promise.resolve(false);
  }

  return new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "https://api.bitrix24.com/api/v1/";
    script.async = true;
    script.onload = () => resolve(Boolean(window.BX24));
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
  });
}

async function syncBitrixSession(auth: BitrixAuth, user: unknown): Promise<SessionUser> {
  const expiresIn =
    auth.expires_in instanceof Date ? auth.expires_in.getTime() : Number(auth.expires_in) || 0;

  const response = await fetch("/api/bitrix/session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ auth: { ...auth, expires_in: expiresIn }, user }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.error || `HTTP ${response.status}`);
  }

  const data = (await response.json()) as { user: SessionUser };
  return data.user;
}

/**
 * Resolve the signed-in Bitrix user (with server-decided role), or null when
 * not embedded / the handshake did not complete in time.
 */
export async function initBitrixSession(): Promise<SessionUser | null> {
  const loaded = await loadBitrixSDK();
  if (!loaded || !window.BX24) {
    return null;
  }

  return new Promise((resolve, reject) => {
    let settled = false;
    let timeout = 0;
    const succeed = (profile: SessionUser) => {
      if (!settled) {
        settled = true;
        window.clearTimeout(timeout);
        resolve(profile);
      }
    };
    const fail = (error: unknown) => {
      if (!settled) {
        settled = true;
        window.clearTimeout(timeout);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    };
    timeout = window.setTimeout(
      () => fail(new Error("Bitrix24 не ответил при авторизации")),
      8000,
    );

    try {
      window.BX24?.init(() => {
        const auth = window.BX24?.getAuth();
        if (!auth) {
          fail(new Error("Bitrix24 не передал данные авторизации"));
          return;
        }

        window.BX24?.callMethod("user.current", {}, (result) => {
          const bitrixError = result.error();
          if (bitrixError) {
            fail(new Error(`Bitrix24 отклонил user.current: ${String(bitrixError)}`));
            return;
          }
          const user = result.data();
          syncBitrixSession(auth, user)
            .then(succeed)
            .catch(fail);
        });
      });
    } catch (error) {
      fail(error);
    }
  });
}
