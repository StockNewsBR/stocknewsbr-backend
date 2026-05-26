import * as SecureStore from "expo-secure-store";
import type { ReactNode } from "react";
import { createContext, useContext, useEffect, useState } from "react";

import {
  getAccess,
  getPublicBootstrap,
  loginJson,
  logoutAuth,
  requestTelegramLink as requestTelegramLinkApi,
  verifyLoginOtp,
  updateProfile,
} from "@/lib/api";

const TOKEN_KEY = "stocknewsbr.token";
const DEVICE_ID_KEY = "stocknewsbr.device_id";

type LoginChallenge = {
  login_token: string;
  debug_otp_code?: string | null;
  otp_expires_at?: string | null;
  session_policy?: string | null;
  detail?: string | null;
};

type SessionContextValue = {
  ready: boolean;
  busy: boolean;
  token: string | null;
  access: Record<string, any> | null;
  bootstrap: Record<string, any> | null;
  challenge: LoginChallenge | null;
  error: string | null;
  deviceId: string;
  signIn: (email: string, password: string) => Promise<{ otpRequired: boolean; debugOtpCode?: string | null }>;
  verifyOtp: (code: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshAccess: () => Promise<Record<string, any> | null>;
  requestTelegramLink: (originChannel?: string) => Promise<Record<string, any>>;
  updateUserProfile: (payload: { email?: string | null; display_name?: string | null; avatar_url?: string | null }) => Promise<Record<string, any> | null>;
  clearError: () => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);

async function ensureDeviceId() {
  const stored = await SecureStore.getItemAsync(DEVICE_ID_KEY);
  if (stored) {
    return stored;
  }
  const generated = `mobile-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  await SecureStore.setItemAsync(DEVICE_ID_KEY, generated);
  return generated;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [access, setAccess] = useState<Record<string, any> | null>(null);
  const [bootstrap, setBootstrap] = useState<Record<string, any> | null>(null);
  const [challenge, setChallenge] = useState<LoginChallenge | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deviceId, setDeviceId] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function bootstrapSession() {
      try {
        const [storedToken, currentDeviceId, publicBootstrap] = await Promise.all([
          SecureStore.getItemAsync(TOKEN_KEY),
          ensureDeviceId(),
          getPublicBootstrap().catch(() => null),
        ]);

        if (cancelled) {
          return;
        }

        setDeviceId(currentDeviceId);
        setBootstrap(publicBootstrap);

        if (storedToken) {
          setToken(storedToken);
          try {
            const nextAccess = await getAccess(storedToken);
            if (!cancelled) {
              setAccess(nextAccess);
            }
          } catch (accessError) {
            if (!cancelled) {
              setError(accessError instanceof Error ? accessError.message : "access_load_failed");
              await SecureStore.deleteItemAsync(TOKEN_KEY);
              setToken(null);
              setAccess(null);
            }
          }
        }
      } catch (bootstrapError) {
        if (!cancelled) {
          setError(bootstrapError instanceof Error ? bootstrapError.message : "bootstrap_failed");
          setDeviceId((await ensureDeviceId()) || "");
        }
      } finally {
        if (!cancelled) {
          setReady(true);
        }
      }
    }

    bootstrapSession();

    return () => {
      cancelled = true;
    };
  }, []);

  async function persistToken(nextToken: string | null) {
    if (nextToken) {
      await SecureStore.setItemAsync(TOKEN_KEY, nextToken);
    } else {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
  }

  async function refreshAccess() {
    if (!token) {
      return null;
    }

    try {
      const nextAccess = await getAccess(token);
      setAccess(nextAccess);
      return nextAccess;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "access_refresh_failed");
      return null;
    }
  }

  async function signIn(email: string, password: string) {
    setBusy(true);
    setError(null);

    try {
      const payload = await loginJson(email, password, {
        channel: "app",
        device_id: deviceId || (await ensureDeviceId()),
        device_label: "mobile_app",
      });

      if (payload?.otp_required && payload?.login_token) {
        const nextChallenge: LoginChallenge = {
          login_token: payload.login_token,
          debug_otp_code: payload.debug_otp_code || null,
          otp_expires_at: payload.otp_expires_at || null,
          session_policy: payload.session_policy || null,
          detail: payload.detail || null,
        };
        setChallenge(nextChallenge);
        return { otpRequired: true, debugOtpCode: nextChallenge.debug_otp_code };
      }

      const nextToken = payload?.access_token || null;
      if (!nextToken) {
        throw new Error("login_without_token");
      }

      await persistToken(nextToken);
      setToken(nextToken);
      setChallenge(null);
      const nextAccess = await getAccess(nextToken);
      setAccess(nextAccess);
      return { otpRequired: false };
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "login_failed");
      throw requestError;
    } finally {
      setBusy(false);
    }
  }

  async function verifyOtp(code: string) {
    if (!challenge?.login_token) {
      throw new Error("missing_login_challenge");
    }

    setBusy(true);
    setError(null);

    try {
      const payload = await verifyLoginOtp(challenge.login_token, code);
      const nextToken = payload?.access_token || null;
      if (!nextToken) {
        throw new Error("otp_without_token");
      }

      await persistToken(nextToken);
      setToken(nextToken);
      setChallenge(null);
      const nextAccess = await getAccess(nextToken);
      setAccess(nextAccess);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "otp_failed");
      throw requestError;
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    const nextToken = token;
    setBusy(true);
    setError(null);

    try {
      if (nextToken) {
        await logoutAuth(nextToken).catch(() => null);
      }
    } finally {
      await persistToken(null);
      setToken(null);
      setAccess(null);
      setChallenge(null);
      setBusy(false);
    }
  }

  async function requestTelegramLink(originChannel = "app") {
    if (!token) {
      throw new Error("not_authenticated");
    }

    setBusy(true);
    setError(null);
    try {
      return await requestTelegramLinkApi(token, originChannel);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "telegram_link_failed");
      throw requestError;
    } finally {
      setBusy(false);
    }
  }

  async function updateUserProfile(payload: { email?: string | null; display_name?: string | null; avatar_url?: string | null }) {
    if (!token) {
      throw new Error("not_authenticated");
    }

    setBusy(true);
    setError(null);
    try {
      const nextAccess = await updateProfile(token, payload);
      setAccess(nextAccess);
      return nextAccess;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "profile_update_failed");
      throw requestError;
    } finally {
      setBusy(false);
    }
  }

  function clearError() {
    setError(null);
  }

  const value: SessionContextValue = {
    ready,
    busy,
    token,
    access,
    bootstrap,
    challenge,
    error,
    deviceId,
    signIn,
    verifyOtp,
    signOut,
    refreshAccess,
    requestTelegramLink,
    updateUserProfile,
    clearError,
  };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return value;
}
