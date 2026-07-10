import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Image, Linking, ScrollView, Text, View } from "react-native";

import { Button, Card, Divider, Field, Pill, SectionHeader, StatTile, theme } from "@/components/ui";
import { getBillingPricing } from "@/lib/api";
import { LanguageToggle, useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function AuthGateScreen() {
  const { ready, token, bootstrap, challenge, busy, error, signIn, requestAccessCode, verifyOtp, clearError } = useSession();
  const { t } = useI18n();
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

  const authenticated = ready && Boolean(token);

  useEffect(() => {
    if (authenticated) {
      router.replace("/(tabs)");
    }
  }, [authenticated]);

  if (authenticated) {
    return null;
  }

  async function handleSignIn() {
    setLocalError(null);
    setLocalMessage(null);
    clearError();

    try {
      const result = await signIn(email.trim(), password);
      if (result.otpRequired) {
        setLocalMessage(t("msgOtpRequired"));
      } else {
        setLocalMessage(t("msgSessionOk"));
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

  async function handleForgotPassword() {
    setLocalError(null);
    setLocalMessage(null);
    clearError();

    if (!email.trim()) {
      setLocalError(t("needEmailFirst"));
      return;
    }

    try {
      await requestAccessCode(email.trim());
      setLocalMessage(t("codeSentMsg"));
    } catch (requestError) {
      setLocalError(requestError instanceof Error ? requestError.message : "request_code_failed");
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

  function annualDiscountPct(monthly: unknown, annual: unknown) {
    const monthlyAmount = Number(monthly);
    const annualAmount = Number(annual);
    if (!Number.isFinite(monthlyAmount) || !Number.isFinite(annualAmount) || monthlyAmount <= 0 || annualAmount <= 0) {
      return null;
    }
    const pct = Math.round((1 - annualAmount / (monthlyAmount * 12)) * 100);
    return pct > 0 ? pct : null;
  }

  const legacyPricing = bootstrap?.pricing || {};
  const brPlan = brPricing?.selected || brPricing?.plans?.BR || {};
  const usaPlan = usaPricing?.selected || usaPricing?.plans?.USA || {};
  const brDiscount = annualDiscountPct(brPlan.monthly_amount ?? 49, brPlan.annual_amount ?? 500);
  const usaDiscount = annualDiscountPct(usaPlan.monthly_amount ?? 49, usaPlan.annual_amount ?? 500);
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
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flexShrink: 1 }}>
            <Image
              source={require("../assets/brand-logo.png")}
              style={{ width: 40, height: 40, borderRadius: 10 }}
              resizeMode="contain"
              accessibilityLabel="StockNewsBR logo"
            />
            <Pill label={t("appTag")} tone="accent" />
          </View>
          <LanguageToggle />
        </View>
        <Text style={{ color: theme.colors.text, fontSize: 32, fontWeight: "800", lineHeight: 36 }}>
          {t("loginTitle")}
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 15, lineHeight: 22 }}>
          {t("loginSubtitle")}
        </Text>
      </View>

      <Card>
        <SectionHeader title={t("accessTitle")} subtitle={t("accessSubtitle")} />
        <Field value={email} onChangeText={setEmail} placeholder={t("emailPh")} keyboardType="email-address" autoCapitalize="none" />
        <Field value={password} onChangeText={setPassword} placeholder={t("passwordPh")} secureTextEntry />
        <Button label={t("signIn")} onPress={handleSignIn} loading={busy} />
        <Button label={t("forgotPassword")} onPress={handleForgotPassword} variant="ghost" disabled={busy} />
        {challenge ? (
          <>
            <Divider />
            <Pill label={challenge.session_policy || t("otpFallbackPill")} tone="warning" />
            <Text style={{ color: theme.colors.muted, fontSize: 13, lineHeight: 18 }}>
              {t("otpHelp")}
            </Text>
            <Field value={otp} onChangeText={setOtp} placeholder={t("otpPh")} keyboardType="numeric" />
            <Button label={t("otpValidate")} onPress={handleVerifyOtp} loading={busy} />
            {challenge.debug_otp_code ? <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{t("otpLocalCode")} {challenge.debug_otp_code}</Text> : null}
          </>
        ) : null}
        {localMessage ? <Text style={{ color: theme.colors.accent, fontSize: 13 }}>{localMessage}</Text> : null}
        {localError ? <Text style={{ color: theme.colors.danger, fontSize: 13 }}>{localError}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title={t("planTitle")} subtitle={t("planSubtitle")} />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label={t("trialBR")} value={`${brTrialDays} ${t("daysSuffix")}`} />
          <StatTile label={t("trialUSA")} value={`${usaTrialDays} ${t("daysSuffix")}`} />
          <StatTile label={t("brMonthly")} value={`R$ ${brPlan.monthly_amount ?? 49}`} tone="accent" />
          <StatTile label={t("brAnnual")} value={`R$ ${brPlan.annual_amount ?? 500}`} tone="info" />
          {brDiscount ? <StatTile label={t("brAnnualDiscount")} value={`-${brDiscount}%`} tone="accent" /> : null}
          <StatTile label={t("usaMonthly")} value={`$${usaPlan.monthly_amount ?? 49}`} tone="accent" />
          <StatTile label={t("usaAnnual")} value={`$${usaPlan.annual_amount ?? 500}`} tone="info" />
          {usaDiscount ? <StatTile label={t("usaAnnualDiscount")} value={`-${usaDiscount}%`} tone="accent" /> : null}
          <StatTile label={t("primaryLabel")} value={bootstrap?.primary_launch_platform || "google_app"} tone="warning" />
          <StatTile label={t("refundLabel")} value={`${refundDays} ${t("daysSuffix")}`} />
        </View>
        <Divider />
        <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
          {t("planNote")}
        </Text>
      </Card>

      <Card>
        <SectionHeader title={t("shortcutsTitle")} subtitle={t("shortcutsSubtitle")} />
        <View style={{ gap: 10 }}>
          <Button label={t("openSite")} onPress={openPublicSite} variant="secondary" />
        </View>
      </Card>
    </ScrollView>
  );
}
