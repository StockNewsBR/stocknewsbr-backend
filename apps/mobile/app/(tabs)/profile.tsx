import { useEffect, useState } from "react";
import { Linking, ScrollView, Text, View } from "react-native";

import { Button, Card, Divider, Field, Pill, SectionHeader, StatTile, theme } from "@/components/ui";
import { getBillingPricing } from "@/lib/api";
import { LanguageToggle, useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function ProfileTab() {
  const { access, bootstrap, busy, signOut, requestTelegramLink, updateUserProfile, refreshAccess } = useSession();
  const { t } = useI18n();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [telegramStatus, setTelegramStatus] = useState<string | null>(null);
  const [brPricing, setBrPricing] = useState<Record<string, any> | null>(null);
  const [usaPricing, setUsaPricing] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    setDisplayName(access?.display_name || "");
    setEmail(access?.email || "");
    setAvatarUrl(access?.avatar_url || "");
  }, [access]);

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

  async function handleSaveProfile() {
    setStatus(null);
    try {
      await updateUserProfile({
        display_name: displayName.trim(),
        email: email.trim(),
        avatar_url: avatarUrl.trim(),
      });
      setStatus(t("profileSaved"));
      await refreshAccess();
    } catch (requestError) {
      setStatus(requestError instanceof Error ? requestError.message : "profile_update_failed");
    }
  }

  async function handleTelegramLink() {
    setTelegramStatus(null);
    try {
      const result = await requestTelegramLink("app");
      if (result?.deep_link) {
        try {
          await Linking.openURL(result.deep_link);
        } catch {}
      }
      setTelegramStatus(result?.link_code ? `${t("telegramCodePrefix")} ${result.link_code}` : t("telegramLinkOk"));
    } catch (requestError) {
      setTelegramStatus(requestError instanceof Error ? requestError.message : "telegram_link_failed");
    }
  }

  async function handleOpenOfficialSite() {
    try {
      await Linking.openURL(bootstrap?.launch_roadmap?.domain || "https://www.stocknewsbr.com");
    } catch (requestError) {
      setStatus(requestError instanceof Error ? requestError.message : "open_site_failed");
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

  const brPlan = brPricing?.selected || brPricing?.plans?.BR || {};
  const usaPlan = usaPricing?.selected || usaPricing?.plans?.USA || {};
  const trialDays = brPlan.trial_days || bootstrap?.pricing?.trial_days || 30;
  const refundDays = brPricing?.refund_window_days || 7;
  const brDiscount = annualDiscountPct(brPlan.monthly_amount ?? 49, brPlan.annual_amount ?? 500);
  const usaDiscount = annualDiscountPct(usaPlan.monthly_amount ?? 49, usaPlan.annual_amount ?? 500);

  return (
    <ScrollView style={{ flex: 1, backgroundColor: theme.colors.background }} contentContainerStyle={{ padding: 20, gap: 16 }}>
      <View style={{ gap: 8, paddingTop: 10 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
          <Pill label={t("profilePill")} tone="accent" />
          <LanguageToggle />
        </View>
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          {t("profileTitle")}
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          {t("profileSubtitle")}
        </Text>
      </View>

      <Card>
        <SectionHeader title={t("accountTitle")} subtitle={t("accountSubtitle")} />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label={t("nameLabel")} value={access?.display_name || "n/a"} />
          <StatTile label={t("emailLabel")} value={access?.email || "n/a"} tone="info" />
          <StatTile label={t("planLabel")} value={access?.plan || "n/a"} tone="accent" />
          <StatTile label={t("otpLabel")} value={access?.otp_required_on_login ? t("otpActive") : t("otpOff")} tone="warning" />
        </View>
        <Divider />
        <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
          {access?.session_policy ? `${t("sessionPolicyPrefix")} ${access.session_policy}` : t("noSessionPolicy")}
        </Text>
      </Card>

      <Card>
        <SectionHeader title={t("editProfileTitle")} subtitle={t("editProfileSubtitle")} />
        <Field value={displayName} onChangeText={setDisplayName} placeholder={t("displayNamePh")} />
        <Field value={email} onChangeText={setEmail} placeholder={t("emailLabel")} keyboardType="email-address" />
        <Field value={avatarUrl} onChangeText={setAvatarUrl} placeholder={t("avatarPh")} />
        <Button label={t("saveChanges")} onPress={handleSaveProfile} loading={busy} />
        {status ? <Text style={{ color: theme.colors.muted, fontSize: 13 }}>{status}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title={t("telegramTitle")} subtitle={t("telegramSubtitle")} />
        <Button label={t("telegramBtn")} onPress={handleTelegramLink} variant="secondary" loading={busy} />
        {telegramStatus ? <Text style={{ color: theme.colors.muted, fontSize: 13 }}>{telegramStatus}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title={t("commercialTitle")} subtitle={t("commercialSubtitle")} />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label={t("currentTrialLabel")} value={`${trialDays} ${t("daysSuffix")}`} />
          <StatTile label={t("brMonthly")} value={`R$ ${brPlan.monthly_amount ?? 49}`} tone="accent" />
          <StatTile label={t("brAnnual")} value={`R$ ${brPlan.annual_amount ?? 500}`} tone="info" />
          {brDiscount ? <StatTile label={t("brAnnualDiscount")} value={`-${brDiscount}%`} tone="accent" /> : null}
          <StatTile label={t("usaMonthly")} value={`$${usaPlan.monthly_amount ?? 49}`} tone="accent" />
          <StatTile label={t("usaAnnual")} value={`$${usaPlan.annual_amount ?? 500}`} tone="info" />
          {usaDiscount ? <StatTile label={t("usaAnnualDiscount")} value={`-${usaDiscount}%`} tone="accent" /> : null}
          <StatTile label={t("refundLabel")} value={`${refundDays} ${t("daysSuffix")}`} />
          <StatTile label={t("domainLabel")} value={bootstrap?.launch_roadmap?.domain || "n/a"} tone="warning" />
        </View>
        <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
          {t("commercialNote")}
        </Text>
        <Button label={t("openSite")} onPress={handleOpenOfficialSite} variant="secondary" />
      </Card>

      <Card>
        <SectionHeader title={t("logoutTitle")} subtitle={t("logoutSubtitle")} />
        <Button label={t("logoutBtn")} onPress={signOut} variant="ghost" loading={busy} />
      </Card>
    </ScrollView>
  );
}
