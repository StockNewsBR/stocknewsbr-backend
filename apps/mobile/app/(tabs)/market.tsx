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
import { useSession } from "@/lib/session";

export default function MarketTab() {
  const { token } = useSession();
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
        <Pill label="Mercado" tone="info" />
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          Leitura de fluxo, calor, radar e narrativa institucional.
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          A tela concentra o que o app sabe do mercado em um toque rapido.
        </Text>
      </View>

      <Card>
        <SectionHeader title="Snapshot" subtitle="Sinaliza a saude da memoria de mercado." />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label="Signals" value={String(snapshotInfo?.signals ?? snapshotInfo?.snapshot_signals ?? "n/a")} tone="accent" />
          <StatTile label="Cache" value={formatRelativeSeconds(snapshotInfo?.age_seconds ?? snapshotInfo?.cache_age)} tone="warning" />
          <StatTile label="Source" value={snapshotInfo?.source || "n/a"} tone="info" />
          <StatTile label="Updated" value={snapshotInfo?.updated_at || snapshotInfo?.last_update || "n/a"} />
        </View>
      </Card>

      <Card>
        <SectionHeader title="Narrativa" subtitle="O texto de contexto que ajuda a ler o dia sem caçar sinal solto." />
        {narrative ? (
          <View style={{ gap: 8 }}>
            <Text style={{ color: theme.colors.text, fontSize: 18, fontWeight: "700" }}>
              Narrativa de mercado
            </Text>
            <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
              {narrative}
            </Text>
          </View>
        ) : (
          <EmptyState title="Sem narrativa" description="O backend nao retornou narrativa agora." />
        )}
      </Card>

      <Card>
        <SectionHeader title="Heatmap" subtitle="O que esta quente, o que esta fraco e os nomes com pressao real." />
        {heatmap?.global || heatmap?.sectors ? (
          <View style={{ gap: 12 }}>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
              <StatTile
                label="Forca"
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
              <Text style={{ color: theme.colors.text, fontWeight: "700" }}>Setores</Text>
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
          <EmptyState title="Heatmap vazio" description="A leitura quente/fria ainda nao veio do servidor." />
        )}
      </Card>

      <Card>
        <SectionHeader title="Radar" subtitle="Movimentos com evento, gatilho ou aceleracao relevante." />
        {radar.length ? (
          radar.slice(0, 8).map((row: any) => (
            <View key={`${row.symbol || row.ticker || row.id}`} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line, gap: 5 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{row.symbol || row.ticker}</Text>
                <Text style={{ color: theme.colors.info, fontWeight: "700" }}>{formatPercent(row.score)}</Text>
              </View>
              <Text style={{ color: theme.colors.muted, lineHeight: 18 }}>{row.signal || row.state || "n/a"}</Text>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>
                {Array.isArray(row.events) ? `${row.events.length} eventos` : "sem eventos"}
              </Text>
            </View>
          ))
        ) : (
          <EmptyState title="Radar vazio" description="Sem alvos de radar no momento." />
        )}
      </Card>

      <Card>
        <SectionHeader title="Top movers" subtitle="Ativos com maior tracao no recorte atual." />
        {movers.length ? (
          movers.slice(0, 8).map((symbol) => (
            <View key={symbol} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line }}>
              <View>
                <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{symbol}</Text>
                <Text style={{ color: theme.colors.muted, fontSize: 12 }}>Top mover atual no ranking</Text>
              </View>
              <Pill label="ranking" tone="warning" />
            </View>
          ))
        ) : (
          <EmptyState title="Sem movers" description="A fila de top movers ainda nao voltou do backend." />
        )}
      </Card>
    </ScrollView>
  );
}
