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
import { canonicalSymbol } from "@/lib/symbolRegistry";
import { Button, Card, Divider, EmptyState, Field, Pill, SectionHeader, StatTile, theme } from "@/components/ui";
import { MobilePriceChart } from "@/components/mobile-price-chart";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

const RANGES = ["1D", "1W", "1M", "3M", "1Y"];

export default function TickerDetailScreen() {
  const { symbol } = useLocalSearchParams<{ symbol?: string }>();
  const ticker = canonicalSymbol(symbol || "PETR4") || "PETR4";
  const { token } = useSession();
  const { t, tf } = useI18n();
  const [snapshot, setSnapshot] = useState<Record<string, any> | null>(null);
  const [chart, setChart] = useState<Record<string, any> | null>(null);
  const [news, setNews] = useState<Record<string, any> | null>(null);
  const [feed, setFeed] = useState<Record<string, any> | null>(null);
  const [poll, setPoll] = useState<Record<string, any> | null>(null);
  const [history, setHistory] = useState<Record<string, any>[]>([]);
  const [activeRange, setActiveRange] = useState("1D");
  const [draft, setDraft] = useState("");
  const [sentiment, setSentiment] = useState("neutral");
  const [imageUrl, setImageUrl] = useState("");
  const [showImageField, setShowImageField] = useState(false);
  const [showEmojiRow, setShowEmojiRow] = useState(false);
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
        image_url: imageUrl.trim() || null,
      });
      setDraft("");
      setImageUrl("");
      setStatus(result?.error ? result.reason || result.error : t("postOk"));
      await loadDetail();
    } catch (requestError) {
      setStatus(requestError instanceof Error ? requestError.message : "post_failed");
    } finally {
      setPublishing(false);
    }
  }

  function toggleImageField() {
    // Drop the retained URL when hiding the field so hidden attachments are never submitted.
    if (showImageField) {
      setImageUrl("");
    }
    setShowImageField((current) => !current);
  }

  async function handleVote(option: string) {
    if (!token) {
      setStatus(t("loginToVote"));
      return;
    }

    try {
      const nextPoll = await votePoll(token, ticker, option);
      setPoll(nextPoll);
      setStatus(t("voteOk"));
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
  const dataStatus = ohlcRows.length ? `${ohlcRows.length} ${t("candlesSuffix")}` : t("noCandles");

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: theme.colors.background }}
      contentContainerStyle={{ padding: 20, gap: 16 }}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={loadDetail} tintColor={theme.colors.accent} />}
    >
      <View style={{ paddingTop: 10, gap: 8 }}>
        <Pressable onPress={() => router.back()} style={{ alignSelf: "flex-start" }}>
          <Pill label={t("backBtn")} tone="muted" />
        </Pressable>
        <Pill label={ticker} tone="accent" />
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          {t("tickerScreenTitle")}
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          {t("tickerScreenSubtitle")}
        </Text>
      </View>

      <Card>
        <SectionHeader title={t("panelTitle")} subtitle={t("panelSubtitle")} />
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <StatTile label={t("priceLabel")} value={formatTickerCurrency(ticker, snapshot?.price || snapshot?.last_price)} tone="accent" />
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
        <SectionHeader title={t("chartCardTitle")} subtitle={t("chartCardSubtitle")} />
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
          {chartSummary?.trend || chartSummary?.signal || t("noSyntheticSignal")}
        </Text>
        <Text style={{ color: theme.colors.muted, lineHeight: 20 }}>
          {chartSummary?.text || chartSummary?.summary || t("chartSummaryFallback")}
        </Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          <Pill label={`Close ${formatTickerCurrency(ticker, latestClose)}`} tone="accent" />
          <Pill label={`Markers ${markers.length}`} tone="accent" />
          <Pill label={`Zones ${zones.length}`} tone="warning" />
          <Pill label={`Signals ${Array.isArray(chart?.signals) ? chart.signals.length : 0}`} tone="info" />
        </View>
      </Card>

      <Card>
        <SectionHeader title={tf("publishTitle", { ticker })} subtitle={t("publishSubtitle")} />
        <TextInput
          multiline
          value={draft}
          onChangeText={setDraft}
          placeholder={tf("draftTickerPh", { ticker })}
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
          <Pressable
            onPress={() => setSentiment(sentiment === "bullish" ? "neutral" : "bullish")}
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 6,
              paddingHorizontal: 14,
              paddingVertical: 9,
              borderRadius: 999,
              borderWidth: 1,
              borderColor: sentiment === "bullish" ? theme.colors.accent : theme.colors.line,
              backgroundColor: sentiment === "bullish" ? theme.colors.accentSoft : theme.colors.surfaceSoft,
            }}
          >
            <Text style={{ fontSize: 14 }}>{"\u{1F402}"}</Text>
            <Text style={{ color: sentiment === "bullish" ? theme.colors.accent : theme.colors.muted, fontWeight: "800" }}>{t("bullLabel")}</Text>
          </Pressable>
          <Pressable
            onPress={() => setSentiment(sentiment === "bearish" ? "neutral" : "bearish")}
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 6,
              paddingHorizontal: 14,
              paddingVertical: 9,
              borderRadius: 999,
              borderWidth: 1,
              borderColor: sentiment === "bearish" ? theme.colors.danger : theme.colors.line,
              backgroundColor: sentiment === "bearish" ? "rgba(255, 107, 107, 0.16)" : theme.colors.surfaceSoft,
            }}
          >
            <Text style={{ fontSize: 14 }}>{"\u{1F43B}"}</Text>
            <Text style={{ color: sentiment === "bearish" ? theme.colors.danger : theme.colors.muted, fontWeight: "800" }}>{t("bearLabel")}</Text>
          </Pressable>
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("predictionTemplate")}
            onPress={() => setDraft((current) => (current ? `${current}\n${t("predictionTemplate")}` : t("predictionTemplate")))}
            style={{ width: 42, height: 42, borderRadius: 999, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: theme.colors.line, backgroundColor: theme.colors.surfaceSoft }}
          >
            <Text style={{ fontSize: 16 }}>{"\u{1F3AF}"}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("addImagePh")}
            onPress={toggleImageField}
            style={{ width: 42, height: 42, borderRadius: 999, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: showImageField ? theme.colors.accent : theme.colors.line, backgroundColor: theme.colors.surfaceSoft }}
          >
            <Text style={{ fontSize: 16 }}>{"\u{1F5BC}\u{FE0F}"}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="GIF"
            onPress={toggleImageField}
            style={{ minWidth: 42, height: 42, paddingHorizontal: 8, borderRadius: 999, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: showImageField ? theme.colors.accent : theme.colors.line, backgroundColor: theme.colors.surfaceSoft }}
          >
            <Text style={{ color: theme.colors.text, fontWeight: "800", fontSize: 12 }}>GIF</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Emoji"
            onPress={() => setShowEmojiRow((current) => !current)}
            style={{ width: 42, height: 42, borderRadius: 999, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: showEmojiRow ? theme.colors.accent : theme.colors.line, backgroundColor: theme.colors.surfaceSoft }}
          >
            <Text style={{ fontSize: 16 }}>{"\u{1F60A}"}</Text>
          </Pressable>
          <View style={{ flex: 1 }} />
          <View style={{ minWidth: 120 }}>
            <Button label={t("publishBtn")} onPress={handlePublish} loading={publishing} />
          </View>
        </View>
        {showEmojiRow ? (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {["\u{1F680}", "\u{1F4C8}", "\u{1F4C9}", "\u{1F525}", "\u{1F440}", "\u{1F48E}", "\u{26A0}\u{FE0F}", "\u{1F91D}"].map((emoji) => (
              <Pressable
                key={emoji}
                accessibilityRole="button"
                accessibilityLabel={emoji}
                onPress={() => setDraft((current) => `${current}${emoji}`)}
                style={{ width: 40, height: 40, borderRadius: 12, alignItems: "center", justifyContent: "center", backgroundColor: theme.colors.surfaceSoft, borderWidth: 1, borderColor: theme.colors.line }}
              >
                <Text style={{ fontSize: 18 }}>{emoji}</Text>
              </Pressable>
            ))}
          </View>
        ) : null}
        {showImageField ? (
          <Field value={imageUrl} onChangeText={setImageUrl} placeholder={t("addImagePh")} />
        ) : null}
        {status ? <Text style={{ color: theme.colors.muted, fontSize: 13 }}>{status}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title={t("pollCardTitle")} subtitle={poll?.question || t("pollNone")} />
        {pollOptions.length ? (
          pollOptions.map((option: any) => (
            <View key={option.key} style={{ gap: 8, marginTop: 4 }}>
              <Button label={`${option.key} | ${option.label}`} onPress={() => handleVote(option.key)} variant="secondary" />
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{Number(option.votes || 0)} {t("votesSuffix")}</Text>
            </View>
          ))
        ) : (
          <EmptyState title={t("pollEmptyTitle")} description={t("pollEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader title={t("newsTitle")} subtitle={t("newsSubtitle")} />
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
          <EmptyState title={t("newsEmptyTitle")} description={t("newsEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader title={t("tickerFeedTitle")} subtitle={t("tickerFeedSubtitle")} />
        {feedPosts.length ? (
          feedPosts.slice(0, 8).map((post: any) => (
            <View key={post.id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line, gap: 6 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 10 }}>
                <Text style={{ color: theme.colors.text, fontWeight: "700", flex: 1 }}>{post.user || post.display_name || t("userFallback")}</Text>
                <Pill label={post.sentiment || "neutral"} tone="info" />
              </View>
              <Text style={{ color: theme.colors.text, lineHeight: 20 }}>{post.text}</Text>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>
                {Array.isArray(post.comments) ? `${post.comments.length} comments` : "0 comments"} | {Number(post.likes || 0)} likes | {Number(post.reposts || 0)} reposts
              </Text>
            </View>
          ))
        ) : (
          <EmptyState title={t("tickerFeedEmptyTitle")} description={t("tickerFeedEmptyDesc")} />
        )}
      </Card>

      <Card>
        <SectionHeader title={t("pollHistoryTitle")} subtitle={t("pollHistorySubtitle")} />
        {history.length ? (
          history.slice(0, 6).map((item: any) => (
            <View key={item.id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line, gap: 4 }}>
              <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{item.question}</Text>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{item.created_at || "n/a"}</Text>
            </View>
          ))
        ) : (
          <EmptyState title={t("pollHistoryEmptyTitle")} description={t("pollHistoryEmptyDesc")} />
        )}
      </Card>
    </ScrollView>
  );
}
