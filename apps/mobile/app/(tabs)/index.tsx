import { useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { router } from "expo-router";

import {
  getMarketOpportunity,
  getMarketSnapshotInfo,
  getWorkspace,
} from "@/lib/api";
import { formatNumber, formatPercent, formatRelativeSeconds } from "@/lib/format";
import { canonicalSymbol } from "@/lib/symbolRegistry";
import { Button, Card, Divider, EmptyState, Field, Pill, SectionHeader, StatTile, theme } from "@/components/ui";
import { LanguageToggle, useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function HomeTab() {
  const { token, access, bootstrap } = useSession();
  const { t } = useI18n();
  const [workspace, setWorkspace] = useState<Record<string, any> | null>(null);
  const [snapshotInfo, setSnapshotInfo] = useState<Record<string, any> | null>(null);
  const [opportunity, setOpportunity] = useState<Record<string, any> | null>(null);
  const [ticker, setTicker] = useState("PETR4");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadHome() {
    if (!token) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const [nextWorkspace, nextSnapshotInfo, nextOpportunity] = await Promise.all([
        getWorkspace(token),
        getMarketSnapshotInfo(token).catch(() => null),
        getMarketOpportunity(token).catch(() => null),
      ]);
      setWorkspace(nextWorkspace);
      setSnapshotInfo(nextSnapshotInfo);
      setOpportunity(nextOpportunity);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "home_load_failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHome();
    // Token changes are rare and should trigger a full refresh.
  }, [token]);

  const topSignals = Array.isArray(workspace?.top_signals) ? workspace.top_signals : [];
  const ranking = Array.isArray(workspace?.ranking) ? workspace.ranking : [];
  const featuredPosts = Array.isArray(workspace?.featured_posts) ? workspace.featured_posts : [];
  const strategicPanel = workspace?.strategic_panel && typeof workspace.strategic_panel === "object" ? workspace.strategic_panel : null;
  const strategicAction = strategicPanel?.recommended_action || strategicPanel?.recommended_action_block?.action || "AGUARDAR";
  const strategicRisk = strategicPanel?.risk_block?.visual_level || strategicPanel?.risk_block?.level || t("stratRiskFallback");
  const strategicDirection = strategicPanel?.probable_direction_block?.visual_label || strategicPanel?.probable_direction_block?.label || t("stratDirectionFallback");
  const strategicScore = strategicPanel?.master_score_block?.score;
  const strategicWhy = Array.isArray(strategicPanel?.why) ? strategicPanel.why.slice(0, 4) : [];
  const strategicChangeConditions = Array.isArray(strategicPanel?.opinion_change_conditions)
    ? strategicPanel.opinion_change_conditions.slice(0, 4)
    : [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: theme.colors.background }}
      contentContainerStyle={{ padding: 20, gap: 16 }}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={loadHome} tintColor={theme.colors.accent} />}
    >
      <View style={{ paddingTop: 10, gap: 10 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
          <Pill label={workspace?.brand || "StockNewsBR"} tone="accent" />
          <LanguageToggle />
        </View>
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          {t("homeTitle")}
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          {access?.display_name || access?.email || t("userFallback")} | {access?.plan || "n/a"} | {workspace?.workspace_mode || "single_screen"}
        </Text>
      </View>

      <Card>
        <SectionHeader title={t("overviewTitle")} subtitle={t("overviewSubtitle")} />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label="Signals" value={formatNumber(workspace?.status?.signals_generated)} tone="accent" />
          <StatTile label="Assets" value={formatNumber(workspace?.status?.assets_scanned)} />
          <StatTile label="Snapshot" value={formatNumber(snapshotInfo?.signals ?? workspace?.status?.snapshot_signals)} tone="info" />
          <StatTile label="Cache" value={formatRelativeSeconds(workspace?.status?.cache_age)} tone="warning" />
        </View>
        <Divider />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          <Pill label={workspace?.platform_notes?.tabs_detachable ? "Web detach only" : "Mobile single screen"} tone="info" />
          <Pill label={workspace?.chart_capabilities?.signal_zones ? "Chart overlays" : "Chart basic"} />
          <Pill label={access?.otp_required_on_login ? "OTP on premium" : "Direct access"} tone="warning" />
        </View>
      </Card>

      <Card>
        <SectionHeader title={t("stratTitle")} subtitle={t("stratSubtitle")} />
        {strategicPanel ? (
          <View style={{ gap: 10 }}>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              <Pill label={`Score ${strategicScore ?? "n/a"}`} tone="accent" />
              <Pill label={String(strategicDirection)} tone="info" />
              <Pill label={String(strategicRisk)} tone={String(strategicRisk).toLowerCase().includes("alto") ? "danger" : "warning"} />
            </View>
            <Text style={{ color: theme.colors.text, fontSize: 20, fontWeight: "800" }}>{String(strategicAction)}</Text>
            <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
              {strategicPanel.strategic_panel_summary || t("stratSummaryFallback")}
            </Text>
            {strategicWhy.length ? (
              <View style={{ gap: 4 }}>
                {strategicWhy.map((item: any) => (
                  <Text key={`${item.tool || item.label}`} style={{ color: theme.colors.text, lineHeight: 19 }}>
                    {item.label || item.reason}
                  </Text>
                ))}
              </View>
            ) : null}
            {strategicChangeConditions.length ? (
              <View style={{ gap: 4 }}>
                <Text style={{ color: theme.colors.muted, fontWeight: "700" }}>{t("stratChangeQ")}</Text>
                {strategicChangeConditions.map((item: string) => (
                  <Text key={item} style={{ color: theme.colors.muted, lineHeight: 18 }}>
                    - {item}
                  </Text>
                ))}
              </View>
            ) : null}
          </View>
        ) : (
          <EmptyState title={t("stratEmptyTitle")} description={t("stratEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader
          title={t("quickTickerTitle")}
          subtitle={t("quickTickerSubtitle")}
          action={<Button label={t("openBtn")} onPress={() => router.push(`/ticker/${canonicalSymbol(ticker) || "PETR4"}`)} />}
        />
        <Field value={ticker} onChangeText={(value) => setTicker(value.toUpperCase())} placeholder="PETR4" />
      </Card>

      <Card>
        <SectionHeader title={t("spotlightTitle")} subtitle={t("spotlightSubtitle")} />
        {opportunity?.data ? (
          <View style={{ gap: 8 }}>
            <Text style={{ color: theme.colors.text, fontSize: 18, fontWeight: "700" }}>
              {opportunity.data.ticker || opportunity.data.symbol || opportunity.data.title || "Opportunity"}
            </Text>
            <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
              {opportunity.data.trader_takeaway || opportunity.data.reason || opportunity.data.summary || t("spotlightNoSummary")}
            </Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              <Pill label={`Score ${formatPercent(opportunity.data.score || opportunity.data.benchmark_score || 0)}`} tone="accent" />
              <Pill label={opportunity.data.impact || opportunity.data.signal || "watch"} tone="warning" />
            </View>
          </View>
        ) : (
          <EmptyState title={t("spotlightEmptyTitle")} description={t("spotlightEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader title={t("topSignalsTitle")} subtitle={t("topSignalsSubtitle")} />
        {topSignals.length ? (
          topSignals.slice(0, 5).map((row: any) => (
            <Pressable
              key={`${row.ticker || row.symbol || row.id || "signal"}`}
              onPress={() => router.push(`/ticker/${canonicalSymbol(row.ticker || row.symbol || "PETR4") || "PETR4"}`)}
              style={{
                paddingVertical: 10,
                borderBottomWidth: 1,
                borderBottomColor: theme.colors.line,
                gap: 4,
              }}
            >
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{row.ticker || row.symbol}</Text>
                <Text style={{ color: theme.colors.accent, fontWeight: "800" }}>{formatPercent(row.score)}</Text>
              </View>
              <Text style={{ color: theme.colors.muted }}>{row.signal || row.state || "n/a"}</Text>
            </Pressable>
          ))
        ) : (
          <EmptyState title={t("topSignalsEmptyTitle")} description={t("topSignalsEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader title={t("rankingTitle")} subtitle={t("rankingSubtitle")} />
        {ranking.length ? (
          ranking.slice(0, 6).map((row: any) => (
            <View
              key={`${row.symbol || row.ticker || row.id || "rank"}`}
              style={{
                paddingVertical: 10,
                borderBottomWidth: 1,
                borderBottomColor: theme.colors.line,
                flexDirection: "row",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <View style={{ gap: 4 }}>
                <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{row.symbol || row.ticker}</Text>
                <Text style={{ color: theme.colors.muted }}>{row.trend || row.signal || "n/a"}</Text>
              </View>
              <Pill label={formatPercent(row.score)} tone="accent" />
            </View>
          ))
        ) : (
          <EmptyState title={t("rankingEmptyTitle")} description={t("rankingEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader title={t("feedRecentTitle")} subtitle={t("feedRecentSubtitle")} />
        {featuredPosts.length ? (
          featuredPosts.slice(0, 4).map((post: any) => (
            <View key={`${post.id || post.timestamp}`} style={{ gap: 6, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 10 }}>
                <Text style={{ color: theme.colors.text, fontWeight: "700", flex: 1 }}>{post.user || post.display_name || t("userFallback")}</Text>
                {post.ticker ? <Pill label={post.ticker} tone="info" /> : null}
              </View>
              <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>{post.text}</Text>
            </View>
          ))
        ) : (
          <EmptyState title={t("feedRecentEmptyTitle")} description={t("feedRecentEmptyDesc")} />
        )}
      </Card>

      {bootstrap?.help_center_modules ? (
        <Card>
          <SectionHeader title={t("productShortcutsTitle")} subtitle={t("productShortcutsSubtitle")} />
          <View style={{ gap: 10 }}>
            {(bootstrap.help_center_modules || []).slice(0, 3).map((item: any) => (
              <View key={item.slug || item.title} style={{ gap: 4 }}>
                <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{item.title}</Text>
                <Text style={{ color: theme.colors.muted, lineHeight: 18 }}>{item.description}</Text>
              </View>
            ))}
          </View>
        </Card>
      ) : null}

      {error ? (
        <Card>
          <Text style={{ color: theme.colors.danger, fontSize: 13 }}>{error}</Text>
        </Card>
      ) : null}
    </ScrollView>
  );
}
