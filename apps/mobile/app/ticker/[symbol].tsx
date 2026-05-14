import { useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useLocalSearchParams, router } from "expo-router";

import {
  createTickerPost,
  getChart,
  getNews,
  getPoll,
  getPollHistory,
  getTickerFeed,
  getTickerSnapshot,
  votePoll,
} from "@/lib/api";
import { formatPercent, formatPlainNumber, formatTickerCurrency, formatTimestamp } from "@/lib/format";
import { Button, Card, Divider, EmptyState, Field, Pill, SectionHeader, StatTile, theme } from "@/components/ui";
import { MobilePriceChart } from "@/components/mobile-price-chart";
import { useSession } from "@/lib/session";

const SENTIMENTS = ["bullish", "bearish", "neutral"];
const RANGES = ["1D", "1W", "1M", "3M", "1Y"];

export default function TickerDetailScreen() {
  const { symbol } = useLocalSearchParams<{ symbol?: string }>();
  const ticker = String(symbol || "PETR4").toUpperCase().trim();
  const { token } = useSession();
  const [snapshot, setSnapshot] = useState<Record<string, any> | null>(null);
  const [chart, setChart] = useState<Record<string, any> | null>(null);
  const [news, setNews] = useState<Record<string, any> | null>(null);
  const [feed, setFeed] = useState<Record<string, any> | null>(null);
  const [poll, setPoll] = useState<Record<string, any> | null>(null);
  const [history, setHistory] = useState<Record<string, any>[]>([]);
  const [activeRange, setActiveRange] = useState("1D");
  const [draft, setDraft] = useState("");
  const [sentiment, setSentiment] = useState("neutral");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);

  async function loadDetail() {
    if (!token) {
      return;
    }

    setLoading(true);
    try {
      const [nextSnapshot, nextChart, nextNews, nextFeed, nextPoll, nextHistory] = await Promise.all([
        getTickerSnapshot(token, ticker).catch(() => null),
        getChart(token, ticker, activeRange).catch(() => null),
        getNews(token, ticker).catch(() => null),
        getTickerFeed(token, ticker).catch(() => null),
        getPoll(ticker).catch(() => null),
        getPollHistory(ticker).catch(() => ({ history: [] })),
      ]);
      setSnapshot(nextSnapshot);
      setChart(nextChart);
      setNews(nextNews);
      setFeed(nextFeed);
      setPoll(nextPoll);
      setHistory(Array.isArray(nextHistory?.history) ? nextHistory.history : []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDetail();
  }, [token, ticker, activeRange]);

  async function handlePublish() {
    if (!token || !draft.trim()) {
      return;
    }

    setPublishing(true);
    setStatus(null);
    try {
      const result = await createTickerPost(token, ticker, {
        text: draft.trim(),
        sentiment,
      });
      setDraft("");
      setStatus(result?.error ? result.reason || result.error : "Post publicado.");
      await loadDetail();
    } catch (requestError) {
      setStatus(requestError instanceof Error ? requestError.message : "post_failed");
    } finally {
      setPublishing(false);
    }
  }

  async function handleVote(option: string) {
    if (!token) {
      setStatus("Faça login para votar.");
      return;
    }

    try {
      const nextPoll = await votePoll(token, ticker, option);
      setPoll(nextPoll);
      setStatus("Voto registrado.");
    } catch (requestError) {
      setStatus(requestError instanceof Error ? requestError.message : "vote_failed");
    }
  }

  const newsItems = Array.isArray(news?.items) ? news.items : [];
  const feedPosts = Array.isArray(feed?.posts) ? feed.posts : [];
  const pollOptions = Array.isArray(poll?.options) ? poll.options : [];
  const chartSummary = chart?.summary || {};
  const markers = Array.isArray(chart?.markers) ? chart.markers : [];
  const zones = Array.isArray(chart?.zones) ? chart.zones : [];
  const ohlcRows = Array.isArray(chart?.ohlc) ? chart.ohlc : Array.isArray(chart?.data) ? chart.data : [];
  const chartSeries = Array.isArray(chart?.series) ? chart.series : [];
  const latestClose = chartSummary?.latest_close || snapshot?.price || snapshot?.last_price;
  const dataStatus = ohlcRows.length ? `${ohlcRows.length} candles` : "sem candles validos";

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: theme.colors.background }}
      contentContainerStyle={{ padding: 20, gap: 16 }}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={loadDetail} tintColor={theme.colors.accent} />}
    >
      <View style={{ paddingTop: 10, gap: 8 }}>
        <Pressable onPress={() => router.back()} style={{ alignSelf: "flex-start" }}>
          <Pill label="Voltar" tone="muted" />
        </Pressable>
        <Pill label={ticker} tone="accent" />
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          Painel mobile do ativo.
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          Preco, grafico, news, feed e poll no mesmo fluxo para abrir o ativo sem depender do desktop.
        </Text>
      </View>

      <Card>
        <SectionHeader title="Painel do ticker" subtitle="Leitura mais recente do ativo e estado real dos dados." />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label="Preco" value={formatTickerCurrency(ticker, snapshot?.price || snapshot?.last_price)} tone="accent" />
          <StatTile label="Change" value={formatPercent(snapshot?.change_pct || snapshot?.change)} tone="info" />
          <StatTile label="Volume" value={formatPlainNumber(snapshot?.volume)} />
          <StatTile label="High/Low" value={`${formatTickerCurrency(ticker, snapshot?.high)} / ${formatTickerCurrency(ticker, snapshot?.low)}`} tone="warning" />
        </View>
        <Divider />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          <Pill label={snapshot?.trend || snapshot?.signal || "n/a"} tone="info" />
          <Pill label={snapshot?.after_hours ? "after-hours" : "regular"} />
          <Pill label={snapshot?.pre_market ? "pre-market" : "session"} />
          <Pill label={dataStatus} tone={ohlcRows.length ? "accent" : "warning"} />
        </View>
      </Card>

      <Card>
        <SectionHeader title="Grafico mobile" subtitle="Candles, zonas, marcadores e ranges principais." />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {RANGES.map((range) => (
            <Pressable
              key={range}
              testID={`range-${range}`}
              onPress={() => setActiveRange(range)}
              style={{
                minHeight: 38,
                minWidth: 50,
                alignItems: "center",
                justifyContent: "center",
                borderRadius: 999,
                borderWidth: 1,
                borderColor: activeRange === range ? theme.colors.accent : theme.colors.line,
                backgroundColor: activeRange === range ? theme.colors.accentSoft : theme.colors.surfaceSoft,
              }}
            >
              <Text style={{ color: activeRange === range ? theme.colors.accent : theme.colors.muted, fontWeight: "800" }}>
                {range}
              </Text>
            </Pressable>
          ))}
        </View>
        <MobilePriceChart ticker={ticker} range={activeRange} rows={ohlcRows} series={chartSeries} markers={markers} zones={zones} />
        <Divider />
        <Text style={{ color: theme.colors.text, fontSize: 18, fontWeight: "700" }}>
          {chartSummary?.trend || chartSummary?.signal || "Sem sinal sintetico ainda"}
        </Text>
        <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
          {chartSummary?.text || chartSummary?.summary || "O backend pode estar sem candles suficientes neste momento."}
        </Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          <Pill label={`Close ${formatTickerCurrency(ticker, latestClose)}`} tone="accent" />
          <Pill label={`Markers ${markers.length}`} tone="accent" />
          <Pill label={`Zones ${zones.length}`} tone="warning" />
          <Pill label={`Signals ${Array.isArray(chart?.signals) ? chart.signals.length : 0}`} tone="info" />
        </View>
      </Card>

      <Card>
        <SectionHeader title="Publicar leitura" subtitle="Envie uma tese ou contexto para o feed do ticker." />
        <TextInput
          multiline
          value={draft}
          onChangeText={setDraft}
          placeholder="Escreva sua leitura do ativo..."
          placeholderTextColor={theme.colors.muted}
          style={{
            minHeight: 120,
            borderRadius: 16,
            paddingHorizontal: 14,
            paddingVertical: 12,
            backgroundColor: theme.colors.surfaceSoft,
            borderWidth: 1,
            borderColor: theme.colors.line,
            color: theme.colors.text,
            textAlignVertical: "top",
          }}
        />
        <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
          {SENTIMENTS.map((item) => (
            <Pressable
              key={item}
              onPress={() => setSentiment(item)}
              style={{
                paddingHorizontal: 12,
                paddingVertical: 8,
                borderRadius: 999,
                borderWidth: 1,
                borderColor: sentiment === item ? theme.colors.accent : theme.colors.line,
                backgroundColor: sentiment === item ? theme.colors.accentSoft : theme.colors.surfaceSoft,
              }}
            >
              <Text style={{ color: sentiment === item ? theme.colors.accent : theme.colors.muted, fontWeight: "700" }}>{item}</Text>
            </Pressable>
          ))}
        </View>
        <Button label="Publicar" onPress={handlePublish} loading={publishing} />
        {status ? <Text style={{ color: theme.colors.muted, fontSize: 13 }}>{status}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title="Poll" subtitle={poll?.question || "Sem enquete ativa"} />
        {pollOptions.length ? (
          pollOptions.map((option: any) => (
            <View key={option.key} style={{ gap: 8, marginTop: 4 }}>
              <Button label={`${option.key} | ${option.label}`} onPress={() => handleVote(option.key)} variant="secondary" />
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{Number(option.votes || 0)} votos</Text>
            </View>
          ))
        ) : (
          <EmptyState title="Sem poll" description="O ticker ainda nao tem enquete ativa." />
        )}
      </Card>

      <Card>
        <SectionHeader title="News" subtitle="Manchetes filtradas e classificadas para o ticker." />
        {newsItems.length ? (
          newsItems.slice(0, 6).map((item: any) => (
            <View key={item.id || item.story_key} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line, gap: 6 }}>
              <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{item.title}</Text>
              <Text style={{ color: theme.colors.muted, lineHeight: 19 }}>{item.card_summary || item.summary}</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                <Pill label={item.impact_label || item.impact || "n/a"} tone={item.impact === "bullish" ? "accent" : item.impact === "bearish" ? "danger" : "warning"} />
                {item.source ? <Pill label={item.source} /> : null}
              </View>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{formatTimestamp(item.published_at ? new Date(item.published_at).getTime() / 1000 : 0)}</Text>
            </View>
          ))
        ) : (
          <EmptyState title="Sem noticias" description="Nao ha manchetes carregadas para este ticker." />
        )}
      </Card>

      <Card>
        <SectionHeader title="Feed do ticker" subtitle="Posts, likes, comentarios e reposts associados ao ativo." />
        {feedPosts.length ? (
          feedPosts.slice(0, 8).map((post: any) => (
            <View key={post.id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line, gap: 6 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 10 }}>
                <Text style={{ color: theme.colors.text, fontWeight: "700", flex: 1 }}>{post.user || post.display_name || "Usuario"}</Text>
                <Pill label={post.sentiment || "neutral"} tone="info" />
              </View>
              <Text style={{ color: theme.colors.text, lineHeight: 20 }}>{post.text}</Text>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>
                {Array.isArray(post.comments) ? `${post.comments.length} comments` : "0 comments"} | {Number(post.likes || 0)} likes | {Number(post.reposts || 0)} reposts
              </Text>
            </View>
          ))
        ) : (
          <EmptyState title="Feed vazio" description="Ainda nao ha posts para esse ticker." />
        )}
      </Card>

      <Card>
        <SectionHeader title="Historico da poll" subtitle="Comparar as enquetes anteriores ajuda a entender drift de tese." />
        {history.length ? (
          history.slice(0, 6).map((item: any) => (
            <View key={item.id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line, gap: 4 }}>
              <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{item.question}</Text>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{item.created_at || "n/a"}</Text>
            </View>
          ))
        ) : (
          <EmptyState title="Sem historico" description="Nao ha historico para comparar ainda." />
        )}
      </Card>
    </ScrollView>
  );
}
