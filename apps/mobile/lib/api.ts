const API_BASE = (process.env.EXPO_PUBLIC_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");

async function parseJson(response: Response) {
  if (!response.ok) {
    let detail = response.statusText;

    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {}

    throw new Error(detail || "request_failed");
  }

  return response.json();
}

export async function loginJson(
  email: string,
  password: string,
  options?: { channel?: string; device_id?: string; device_label?: string }
) {
  const response = await fetch(`${API_BASE}/auth/login-json`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, ...(options || {}) })
  });
  return parseJson(response);
}

export async function verifyLoginOtp(login_token: string, code: string) {
  const response = await fetch(`${API_BASE}/auth/login/verify-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login_token, code })
  });
  return parseJson(response);
}

export async function getAccess(token: string) {
  const response = await fetch(`${API_BASE}/auth/access`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  return parseJson(response);
}

export async function getWorkspace(token: string) {
  const response = await fetch(`${API_BASE}/app/workspace/data`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  return parseJson(response);
}

export async function getChart(token: string, ticker: string) {
  const response = await fetch(`${API_BASE}/chart/${encodeURIComponent(ticker)}?interval=1D`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  return parseJson(response);
}

export async function getPoll(ticker: string) {
  const response = await fetch(`${API_BASE}/poll/${encodeURIComponent(ticker)}`);
  return parseJson(response);
}

export async function logoutAuth(token: string) {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` }
  });
  return parseJson(response);
}

export async function requestTelegramLink(token: string, origin_channel = "app") {
  const response = await fetch(`${API_BASE}/auth/telegram/link/request`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ origin_channel })
  });
  return parseJson(response);
}
