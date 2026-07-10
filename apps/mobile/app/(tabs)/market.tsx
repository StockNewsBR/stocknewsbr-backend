import { useEffect, useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";

import {
  getMarketHeatmap,
  getMarketNarrative,
  getMarketRadar,
  getMarketSnapshotInfo,
  getTopMovers,
} from "@/lib/api";
import { formatPercent, formatRelativeSeconds } from "@/lib/format";
import { Card, EmptyState, Pill, SectionHeader, StatTile, theme } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function MarketTab() {
  const { token } = useSession();
  const { t } = useI18n();
  const [heatmap, setHeatmap] = useState<Record<string, any> | null>(null);
  const [radar, setRadar] = useState<Record<string, any>[]>([]);
  const [narrative, setNarrative] = useState<string>("");
  const [snapshotInfo, setSnapshotInfo] = useState<Record<string, any> | null>(null);
  const [movers, setMovers] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  async function loadMarket() {
    if (!token) {
      return;
    }

    setLoading(true);
    try {
      const [nextHeatmap, nextRadar, nextNarrative, nextSnapshotInfo, nextMovers] = await Promise.all([
        getMarketHeatmap(token).catch(() => null),
        getMarketRadar(token).catch(() => []),
        getMarketNarrative(token).catch(() => null),
        getMarketSnapshotInfo(token).catch(() => null),
        getTopMovers(token).catch(() => ({ tickers: [] })),
      ]);

      setHeatmap(nextHeatmap);
      setRadar(Array.isArray(nextRadar) ? nextRadar : []);
      setNarrative(typeof nextNarrative === "string" ? nextNarrative : "");
      setSnapshotInfo(nextSnapshotInfo);
      setMovers(
        Array.isArray(nextMovers?.tickers)
          ? nextMovers.tickers
              .map((item: unknown) => String(item || "").trim().toUpperCase())
              .filter(Boolean)
          : [],
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMarket();
  }, [token]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: theme.colors.background }}
      contentContainerStyle={{ padding: 20, gap: 16 }}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={loadMarket} tintColor={theme.colors.accent} />}
    >
      <View style={{ gap: 8, paddingTop: 10 }}>
        <Pill label={t("marketPill")} tone="info" />
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          {t("marketTitle")}
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          {t("marketSubtitle")}
        </Text>
      </View>

      <Card>
        <SectionHeader title={t("snapshotTitle")} subtitle={t("snapshotSubtitle")} />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label="Signals" value={String(snapshotInfo?.signals ?? snapshotInfo?.snapshot_signals ?? "n/a")} tone="accent" />
          <StatTile label="Cache" value={formatRelativeSeconds(snapshotInfo?.age_seconds ?? snapshotInfo?.cache_age)} tone="warning" />
          <StatTile label="Source" value={snapshotInfo?.source || "n/a"} tone="info" />
          <StatTile label="Updated" value={snapshotInfo?.updated_at || snapshotInfo?.last_update || "n/a"} />
        </View>
      </Card>

      <Card>
        <SectionHeader title={t("narrativeTitle")} subtitle={t("narrativeSubtitle")} />
        {narrative ? (
          <View style={{ gap: 8 }}>
            <Text style={{ color: theme.colors.text, fontSize: 18, fontWeight: "700" }}>
              {t("narrativeHeader")}
            </Text>
            <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
              {narrative}
            </Text>
          </View>
        ) : (
          <EmptyState title={t("narrativeEmptyTitle")} description={t("narrativeEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader title={t("heatmapTitle")} subtitle={t("heatmapSubtitle")} />
        {heatmap?.global || heatmap?.sectors ? (
          <View style={{ gap: 12 }}>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
              <StatTile
                label={t("strengthLabel")}
                value={formatPercent(heatmap?.global?.market_strength)}
                tone="accent"
              />
              <StatTile
                label="Bullish"
                value={String(heatmap?.global?.bullish_assets ?? "n/a")}
                tone="info"
              />
              <StatTile
                label="Neutral"
                value={String(heatmap?.global?.neutral_assets ?? "n/a")}
              />
              <StatTile
                label="Bearish"
                value={String(heatmap?.global?.bearish_assets ?? "n/a")}
                tone="warning"
              />
            </View>
            <View style={{ gap: 8 }}>
              <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{t("sectorsLabel")}</Text>
              {(Object.entries(heatmap?.sectors || {}) as Array<[string, Record<string, any>]>)
                .sort((left, right) => Number(right[1]?.strength || 0) - Number(left[1]?.strength || 0))
                .slice(0, 6)
                .map(([sector, payload]) => (
                  <View key={sector} style={{ flexDirection: "row", justifyContent: "space-between", gap: 10 }}>
                    <Text style={{ color: theme.colors.text, flex: 1 }}>{sector}</Text>
                    <Text style={{ color: theme.colors.accent, fontWeight: "700" }}>
                      {formatPercent(payload?.strength)}
                    </Text>
                  </View>
                ))}
            </View>
          </View>
        ) : (
          <EmptyState title={t("heatmapEmptyTitle")} description={t("heatmapEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader title={t("radarTitle")} subtitle={t("radarSubtitle")} />
        {radar.length ? (
          radar.slice(0, 8).map((row: any) => (
            <View key={`${row.symbol || row.ticker || row.id}`} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line, gap: 5 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{row.symbol || row.ticker}</Text>
                <Text style={{ color: theme.colors.info, fontWeight: "700" }}>{formatPercent(row.score)}</Text>
              </View>
              <Text style={{ color: theme.colors.muted, lineHeight: 18 }}>{row.signal || row.state || "n/a"}</Text>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>
                {Array.isArray(row.events) ? `${row.events.length} ${t("eventsSuffix")}` : t("noEvents")}
              </Text>
            </View>
          ))
        ) : (
          <EmptyState title={t("radarEmptyTitle")} description={t("radarEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader title={t("moversTitle")} subtitle={t("moversSubtitle")} />
        {movers.length ? (
          movers.slice(0, 8).map((symbol) => (
            <View key={symbol} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line }}>
              <View>
                <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{symbol}</Text>
                <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{t("moversNote")}</Text>
              </View>
              <Pill label="ranking" tone="warning" />
            </View>
          ))
        ) : (
          <EmptyState title={t("moversEmptyTitle")} description={t("moversEmptyDesc")} />
        )}
      </Card>
    </ScrollView>
  );
}
