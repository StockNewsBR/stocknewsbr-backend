import { useEffect, useState } from "react";
import {
  Linking,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View
} from "react-native";
import * as SecureStore from "expo-secure-store";

import { getAccess, getChart, getPoll, getWorkspace, loginJson, logoutAuth, requestTelegramLink, verifyLoginOtp } from "@/lib/api";

const styles = {
  screen: { flex: 1, backgroundColor: "#061018" } as const,
  container: { padding: 20, gap: 16 } as const,
  title: { color: "#eef4fb", fontSize: 28, fontWeight: "700" as const },
  subtitle: { color: "#8fa4b8", fontSize: 14 },
  card: {
    backgroundColor: "#101c2b",
    borderRadius: 20,
    padding: 16,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    gap: 10
  } as const,
  input: {
    backgroundColor: "#0c1622",
    color: "#eef4fb",
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)"
  } as const,
  button: {
    backgroundColor: "#1fd38a",
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: "center" as const
  },
  buttonSecondary: {
    backgroundColor: "#182434",
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: "center" as const
  },
  buttonText: { color: "#061018", fontWeight: "700" as const },
  buttonTextSecondary: { color: "#eef4fb", fontWeight: "700" as const },
  row: {
    flexDirection: "row" as const,
    justifyContent: "space-between" as const,
    alignItems: "center" as const
  },
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.06)"
  } as const,
  chipText: { color: "#8fa4b8", fontSize: 12 },
  rankingRow: {
    flexDirection: "row" as const,
    justifyContent: "space-between" as const,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.06)"
  } as const
};

export default function HomeScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [loginToken, setLoginToken] = useState("");
  const [debugOtpCode, setDebugOtpCode] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [ticker, setTicker] = useState("PETR4");
  const [workspace, setWorkspace] = useState<any>(null);
  const [chart, setChart] = useState<any>(null);
  const [poll, setPoll] = useState<any>(null);
  const [access, setAccess] = useState<any>(null);
  const [telegramLink, setTelegramLink] = useState<any>(null);

  useEffect(() => {
    SecureStore.getItemAsync("stocknewsbr.token").then((stored) => {
      if (stored) {
        setToken(stored);
      }
    });
  }, []);

  useEffect(() => {
    if (!token) return;

    Promise.all([
      getAccess(token),
      getWorkspace(token),
      getChart(token, ticker),
      getPoll(ticker)
    ])
      .then(([nextAccess, nextWorkspace, nextChart, nextPoll]) => {
        setAccess(nextAccess);
        setWorkspace(nextWorkspace);
        setChart(nextChart);
        setPoll(nextPoll);
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : "Erro ao carregar");
      });
  }, [token, ticker]);

  async function handleLogin() {
    try {
      setError("");
      const currentDeviceId = (await SecureStore.getItemAsync("stocknewsbr.device_id")) || `mobile-${Date.now()}`;
      await SecureStore.setItemAsync("stocknewsbr.device_id", currentDeviceId);
      const payload: any = await loginJson(email, password, {
        channel: "app",
        device_id: currentDeviceId,
        device_label: "expo_mobile_app"
      });

      if (payload?.otp_required && payload?.login_token) {
        setLoginToken(payload.login_token);
        setOtpCode("");
        setDebugOtpCode(payload.debug_otp_code || "");
        return;
      }

      await SecureStore.setItemAsync("stocknewsbr.token", payload.access_token);
      setToken(payload.access_token);
      setLoginToken("");
      setDebugOtpCode("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha no login");
    }
  }

  async function handleVerifyOtp() {
    try {
      setError("");
      const payload: any = await verifyLoginOtp(loginToken, otpCode);
      await SecureStore.setItemAsync("stocknewsbr.token", payload.access_token);
      setToken(payload.access_token);
      setLoginToken("");
      setOtpCode("");
      setDebugOtpCode("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha no codigo");
    }
  }

  async function handleLogout() {
    if (token) {
      try {
        await logoutAuth(token);
      } catch {}
    }
    await SecureStore.deleteItemAsync("stocknewsbr.token");
    setToken("");
    setAccess(null);
    setWorkspace(null);
    setChart(null);
    setPoll(null);
    setLoginToken("");
    setOtpCode("");
    setDebugOtpCode("");
    setTelegramLink(null);
  }

  async function handleTelegramLink() {
    if (!token) return;

    try {
      setError("");
      const payload = await requestTelegramLink(token, "app");
      setTelegramLink(payload);
      if (payload?.deep_link) {
        await Linking.openURL(payload.deep_link);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao gerar link do Telegram");
    }
  }

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>StockNewsBR</Text>
        <Text style={styles.subtitle}>Android-first app conectado ao backend real.</Text>

        {!token && !loginToken ? (
          <View style={styles.card}>
            <Text style={{ color: "#eef4fb", fontSize: 18, fontWeight: "700" }}>Entrar</Text>
            <TextInput style={styles.input} value={email} onChangeText={setEmail} placeholder="Email" placeholderTextColor="#8fa4b8" />
            <TextInput style={styles.input} value={password} secureTextEntry onChangeText={setPassword} placeholder="Senha" placeholderTextColor="#8fa4b8" />
            <Pressable style={styles.button} onPress={handleLogin}>
              <Text style={styles.buttonText}>Entrar</Text>
            </Pressable>
            <Text style={styles.subtitle}>Premium confirma o login com codigo por email. Trial e Free entram direto.</Text>
            {error ? <Text style={{ color: "#ff6b6b" }}>{error}</Text> : null}
          </View>
        ) : !token ? (
          <View style={styles.card}>
            <Text style={{ color: "#eef4fb", fontSize: 18, fontWeight: "700" }}>Codigo por email</Text>
            <Text style={styles.subtitle}>Conta Premium protegida com OTP no email.</Text>
            <TextInput style={styles.input} value={otpCode} onChangeText={setOtpCode} placeholder="Codigo de 6 digitos" placeholderTextColor="#8fa4b8" />
            <Pressable style={styles.button} onPress={handleVerifyOtp}>
              <Text style={styles.buttonText}>Validar codigo</Text>
            </Pressable>
            <Pressable style={styles.buttonSecondary} onPress={() => { setLoginToken(""); setOtpCode(""); setDebugOtpCode(""); }}>
              <Text style={styles.buttonTextSecondary}>Voltar</Text>
            </Pressable>
            {debugOtpCode ? <Text style={styles.subtitle}>Codigo local: {debugOtpCode}</Text> : null}
            {error ? <Text style={{ color: "#ff6b6b" }}>{error}</Text> : null}
          </View>
        ) : (
          <>
            <View style={styles.card}>
              <View style={styles.row}>
                <View>
                  <Text style={{ color: "#eef4fb", fontSize: 18, fontWeight: "700" }}>
                    {access?.display_name || access?.email || "Usuario"}
                  </Text>
                  <Text style={styles.subtitle}>Plano: {access?.plan || "n/a"}</Text>
                </View>
                <Pressable style={styles.buttonSecondary} onPress={handleLogout}>
                  <Text style={styles.buttonTextSecondary}>Sair</Text>
                </Pressable>
              </View>
              <Text style={styles.subtitle}>
                Politica de sessao: {access?.session_policy || "shared"} | OTP Premium: {access?.otp_required_on_login ? "ativo" : "nao"}
              </Text>
              {access?.access?.telegram ? (
                <Pressable style={styles.buttonSecondary} onPress={handleTelegramLink}>
                  <Text style={styles.buttonTextSecondary}>Gerar link seguro do Telegram</Text>
                </Pressable>
              ) : null}
              {telegramLink ? (
                <Text style={styles.subtitle}>
                  Codigo: {telegramLink.link_code} {telegramLink.deep_link ? "| bot aberto automaticamente" : ""}
                </Text>
              ) : null}
            </View>

            <View style={styles.card}>
              <Text style={{ color: "#eef4fb", fontSize: 18, fontWeight: "700" }}>Ticker monitorado</Text>
              <TextInput style={styles.input} value={ticker} onChangeText={(value) => setTicker(value.toUpperCase())} placeholder="PETR4" placeholderTextColor="#8fa4b8" />
              <View style={styles.row}>
                <View style={styles.chip}>
                  <Text style={styles.chipText}>Workspace tabs: {workspace?.tabs?.length || 0}</Text>
                </View>
                <View style={styles.chip}>
                  <Text style={styles.chipText}>Markers: {chart?.markers?.length || 0}</Text>
                </View>
              </View>
              <Text style={styles.subtitle}>
                No app as tabs ficam internas em tela unica. Popout e multi-monitor existem so na web.
              </Text>
            </View>

            <View style={styles.card}>
              <Text style={{ color: "#eef4fb", fontSize: 18, fontWeight: "700" }}>Ranking</Text>
              {(workspace?.ranking || []).slice(0, 6).map((row: any) => (
                <View key={row.symbol} style={styles.rankingRow}>
                  <View>
                    <Text style={{ color: "#eef4fb" }}>{row.symbol}</Text>
                    <Text style={styles.subtitle}>Trend: {row.trend || "n/a"}</Text>
                  </View>
                  <Text style={{ color: "#1fd38a", fontWeight: "700" }}>
                    {Number(row.score || 0).toFixed(2)}
                  </Text>
                </View>
              ))}
            </View>

            <View style={styles.card}>
              <Text style={{ color: "#eef4fb", fontSize: 18, fontWeight: "700" }}>Poll</Text>
              <Text style={styles.subtitle}>{poll?.question || `Poll ativa para ${ticker}`}</Text>
              {(poll?.options || []).map((option: any) => (
                <View key={option.key} style={styles.rankingRow}>
                  <Text style={{ color: "#eef4fb", flex: 1 }}>{option.label}</Text>
                  <Text style={styles.subtitle}>{option.votes} votos</Text>
                </View>
              ))}
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}
