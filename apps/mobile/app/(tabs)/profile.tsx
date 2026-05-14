import { useEffect, useState } from "react";
import { Linking, ScrollView, Text, View } from "react-native";

import { Button, Card, Divider, Field, Pill, SectionHeader, StatTile, theme } from "@/components/ui";
import { getBillingPricing } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function ProfileTab() {
  const { access, bootstrap, busy, signOut, requestTelegramLink, updateUserProfile, refreshAccess } = useSession();
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
      setStatus("Perfil atualizado.");
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
      setTelegramStatus(result?.link_code ? `Codigo ${result.link_code}` : "Link gerado.");
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

  const brPlan = brPricing?.selected || brPricing?.plans?.BR || {};
  const usaPlan = usaPricing?.selected || usaPricing?.plans?.USA || {};
  const trialDays = brPlan.trial_days || bootstrap?.pricing?.trial_days || 30;
  const refundDays = brPricing?.refund_window_days || 7;

  return (
    <ScrollView style={{ flex: 1, backgroundColor: theme.colors.background }} contentContainerStyle={{ padding: 20, gap: 16 }}>
      <View style={{ gap: 8, paddingTop: 10 }}>
        <Pill label="Perfil e acesso" tone="accent" />
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          Conta, acesso, Telegram e legal em um so lugar.
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          Aqui a pessoa confirma o plano, ajusta os dados e sai sem risco.
        </Text>
      </View>

      <Card>
        <SectionHeader title="Conta" subtitle="Resumo do usuario autenticado." />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label="Nome" value={access?.display_name || "n/a"} />
          <StatTile label="Email" value={access?.email || "n/a"} tone="info" />
          <StatTile label="Plano" value={access?.plan || "n/a"} tone="accent" />
          <StatTile label="OTP" value={access?.otp_required_on_login ? "ativo" : "off"} tone="warning" />
        </View>
        <Divider />
        <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
          {access?.session_policy ? `Session policy: ${access.session_policy}` : "Sem politica de sessao carregada."}
        </Text>
      </Card>

      <Card>
        <SectionHeader title="Editar perfil" subtitle="Atualizacao rapida do nome, email e avatar." />
        <Field value={displayName} onChangeText={setDisplayName} placeholder="Display name" />
        <Field value={email} onChangeText={setEmail} placeholder="Email" keyboardType="email-address" />
        <Field value={avatarUrl} onChangeText={setAvatarUrl} placeholder="Avatar URL" />
        <Button label="Salvar alteracoes" onPress={handleSaveProfile} loading={busy} />
        {status ? <Text style={{ color: theme.colors.muted, fontSize: 13 }}>{status}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title="Telegram" subtitle="Gera o link seguro para o canal oficial e abre o bot, se existir." />
        <Button label="Gerar link do Telegram" onPress={handleTelegramLink} variant="secondary" loading={busy} />
        {telegramStatus ? <Text style={{ color: theme.colors.muted, fontSize: 13 }}>{telegramStatus}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title="Resumo comercial" subtitle="Plano carregado do backend e pronto para Google Play." />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label="Trial atual" value={`${trialDays} dias`} />
          <StatTile label="BR mensal" value={`R$ ${brPlan.monthly_amount ?? 49}`} tone="accent" />
          <StatTile label="BR anual" value={`R$ ${brPlan.annual_amount ?? 500}`} tone="info" />
          <StatTile label="USA mensal" value={`$${usaPlan.monthly_amount ?? 49}`} tone="accent" />
          <StatTile label="USA anual" value={`$${usaPlan.annual_amount ?? 500}`} tone="info" />
          <StatTile label="Refund" value={`${refundDays} dias`} />
          <StatTile label="Dominio" value={bootstrap?.launch_roadmap?.domain || "n/a"} tone="warning" />
        </View>
        <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
          Produto Android usa IDs de plano do backend: BR mensal/anual e USA mensal/anual. Cancelamento dentro de 7 dias respeita a janela de refund; depois disso o acesso segue ate o fim do periodo pago.
        </Text>
        <Button label="Abrir site oficial" onPress={handleOpenOfficialSite} variant="secondary" />
      </Card>

      <Card>
        <SectionHeader title="Encerrar sessao" subtitle="Sai do app localmente e revoga a sessao quando possível." />
        <Button label="Logout" onPress={signOut} variant="ghost" loading={busy} />
      </Card>
    </ScrollView>
  );
}
