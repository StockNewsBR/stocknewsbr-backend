import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { Linking, ScrollView, Text, View } from "react-native";

import { Button, Card, Divider, Field, Pill, SectionHeader, StatTile, theme } from "@/components/ui";
import { getBillingPricing } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function AuthGateScreen() {
  const { ready, token, bootstrap, challenge, busy, error, signIn, verifyOtp, clearError } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [localMessage, setLocalMessage] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [brPricing, setBrPricing] = useState<Record<string, any> | null>(null);
  const [usaPricing, setUsaPricing] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    if (error) {
      setLocalError(error);
    }
  }, [error]);

  useEffect(() => {
    let mounted = true;

    Promise.all([
      getBillingPricing("BR").catch(() => null),
      getBillingPricing("USA").catch(() => null),
    ]).then(([nextBrPricing, nextUsaPricing]) => {
      if (!mounted) {
        return;
      }
      setBrPricing(nextBrPricing);
      setUsaPricing(nextUsaPricing);
    });

    return () => {
      mounted = false;
    };
  }, []);

  if (ready && token) {
    return <Redirect href="/(tabs)" />;
  }

  async function handleSignIn() {
    setLocalError(null);
    setLocalMessage(null);
    clearError();

    try {
      const result = await signIn(email.trim(), password);
      if (result.otpRequired) {
        setLocalMessage("Conta Premium exige confirmacao por email.");
      } else {
        setLocalMessage("Sessao liberada com sucesso.");
      }
    } catch (requestError) {
      setLocalError(requestError instanceof Error ? requestError.message : "login_failed");
    }
  }

  async function handleVerifyOtp() {
    setLocalError(null);
    setLocalMessage(null);
    clearError();

    try {
      await verifyOtp(otp.trim());
    } catch (requestError) {
      setLocalError(requestError instanceof Error ? requestError.message : "otp_failed");
    }
  }

  async function openPublicSite() {
    const url = bootstrap?.launch_roadmap?.domain || "https://www.stocknewsbr.com";
    try {
      await Linking.openURL(url);
    } catch (requestError) {
      setLocalError(requestError instanceof Error ? requestError.message : "open_site_failed");
    }
  }

  const legacyPricing = bootstrap?.pricing || {};
  const brPlan = brPricing?.selected || brPricing?.plans?.BR || {};
  const usaPlan = usaPricing?.selected || usaPricing?.plans?.USA || {};
  const brTrialDays = brPlan.trial_days || legacyPricing?.trial_days || 30;
  const usaTrialDays = usaPlan.trial_days || brTrialDays;
  const refundDays = brPricing?.refund_window_days || usaPricing?.refund_window_days || 7;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: theme.colors.background }}
      contentContainerStyle={{ padding: 20, gap: 16 }}
      keyboardShouldPersistTaps="handled"
    >
      <View style={{ gap: 8, paddingTop: 16 }}>
        <Pill label="StockNewsBR Mobile" tone="accent" />
        <Text style={{ color: theme.colors.text, fontSize: 32, fontWeight: "800", lineHeight: 36 }}>
          A central completa do projeto no celular.
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 15, lineHeight: 22 }}>
          Login, mercado, social, polls e telegram em um fluxo unico, rapido e sem crash.
        </Text>
      </View>

      <Card>
        <SectionHeader title="Acesso" subtitle="Use a conta do produto. Trial entra direto; Premium pode pedir OTP por email." />
        <Field value={email} onChangeText={setEmail} placeholder="Email" keyboardType="email-address" autoCapitalize="none" />
        <Field value={password} onChangeText={setPassword} placeholder="Senha" secureTextEntry />
        <Button label="Entrar no app" onPress={handleSignIn} loading={busy} />
        {challenge ? (
          <>
            <Divider />
            <Pill label={challenge.session_policy || "email otp"} tone="warning" />
            <Text style={{ color: theme.colors.muted, fontSize: 13, lineHeight: 18 }}>
              Confirme o codigo recebido por email para concluir o login Premium.
            </Text>
            <Field value={otp} onChangeText={setOtp} placeholder="Codigo de 6 digitos" keyboardType="numeric" />
            <Button label="Validar codigo" onPress={handleVerifyOtp} loading={busy} />
            {challenge.debug_otp_code ? <Text style={{ color: theme.colors.muted, fontSize: 12 }}>Codigo local: {challenge.debug_otp_code}</Text> : null}
          </>
        ) : null}
        {localMessage ? <Text style={{ color: theme.colors.accent, fontSize: 13 }}>{localMessage}</Text> : null}
        {localError ? <Text style={{ color: theme.colors.danger, fontSize: 13 }}>{localError}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title="Plano e lancamento" subtitle="Trial, Premium e regra de refund sincronizados com o backend." />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label="Trial BR" value={`${brTrialDays} dias`} />
          <StatTile label="Trial USA" value={`${usaTrialDays} dias`} />
          <StatTile label="BR mensal" value={`R$ ${brPlan.monthly_amount ?? 49}`} tone="accent" />
          <StatTile label="BR anual" value={`R$ ${brPlan.annual_amount ?? 500}`} tone="info" />
          <StatTile label="USA mensal" value={`$${usaPlan.monthly_amount ?? 49}`} tone="accent" />
          <StatTile label="USA anual" value={`$${usaPlan.annual_amount ?? 500}`} tone="info" />
          <StatTile label="Principal" value={bootstrap?.primary_launch_platform || "google_app"} tone="warning" />
          <StatTile label="Refund" value={`${refundDays} dias`} />
        </View>
        <Divider />
        <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
          Conta internacional usa assinatura USA: Premium $49/month ou $500 upfront. Depois da janela de refund de 7 dias, nao ha devolucao do valor pago.
        </Text>
      </Card>

      <Card>
        <SectionHeader title="Atalhos" subtitle="Se quiser validar a plataforma publica, o dominio oficial abre daqui." />
        <View style={{ gap: 10 }}>
          <Button label="Abrir site oficial" onPress={openPublicSite} variant="secondary" />
        </View>
      </Card>
    </ScrollView>
  );
}
