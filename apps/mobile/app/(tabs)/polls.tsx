import { useEffect, useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";

import { getPoll, getPollHistory, votePoll } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import { canonicalSymbol } from "@/lib/symbolRegistry";
import { Button, Card, EmptyState, Field, Pill, SectionHeader, theme } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function PollsTab() {
  const { token } = useSession();
  const { t } = useI18n();
  const [ticker, setTicker] = useState("PETR4");
  const [poll, setPoll] = useState<Record<string, any> | null>(null);
  const [history, setHistory] = useState<Record<string, any>[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  async function loadPoll() {
    if (!ticker.trim()) {
      return;
    }

    setLoading(true);
    try {
      const [nextPoll, nextHistory] = await Promise.all([
        getPoll(canonicalSymbol(ticker) || "PETR4").catch(() => null),
        getPollHistory(canonicalSymbol(ticker) || "PETR4").catch(() => ({ history: [] })),
      ]);
      setPoll(nextPoll);
      setHistory(Array.isArray(nextHistory?.history) ? nextHistory.history : []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPoll();
  }, [ticker]);

  async function handleVote(option: string) {
    if (!token) {
      setStatus(t("loginToVote"));
      return;
    }

    try {
      const nextPoll = await votePoll(token, canonicalSymbol(ticker) || "PETR4", option);
      setPoll(nextPoll);
      setStatus(t("voteOk"));
      await loadPoll();
    } catch (requestError) {
      setStatus(requestError instanceof Error ? requestError.message : "vote_failed");
    }
  }

  const options = Array.isArray(poll?.options) ? poll.options : [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: theme.colors.background }}
      contentContainerStyle={{ padding: 20, gap: 16 }}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={loadPoll} tintColor={theme.colors.accent} />}
    >
      <View style={{ gap: 8, paddingTop: 10 }}>
        <Pill label={t("pollsPill")} tone="warning" />
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          {t("pollsTitle")}
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          {t("pollsSubtitle")}
        </Text>
      </View>

      <Card>
        <SectionHeader title={t("tickerCardTitle")} subtitle={t("pollsTickerSubtitle")} />
        <Field value={ticker} onChangeText={(value) => setTicker(value.toUpperCase())} placeholder="PETR4" />
        <Button label={t("updatePoll")} onPress={loadPoll} variant="secondary" />
      </Card>

      <Card>
        <SectionHeader title={t("currentPollTitle")} subtitle={poll?.question || t("currentPollNone")} />
        {options.length ? (
          options.map((option: any) => (
            <View key={option.key} style={{ gap: 8, marginTop: 4 }}>
              <Button label={`${option.key} | ${option.label}`} onPress={() => handleVote(option.key)} loading={loading} />
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{Number(option.votes || 0)} {t("votesSuffix")}</Text>
            </View>
          ))
        ) : (
          <EmptyState title={t("noOptionsTitle")} description={t("noOptionsDesc")} />
        )}
        {status ? <Text style={{ color: theme.colors.muted, fontSize: 13 }}>{status}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title={t("historyTitle")} subtitle={t("historySubtitle")} />
        {history.length ? (
          history.map((item: any) => (
            <View key={item.id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line, gap: 4 }}>
              <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{item.question}</Text>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{formatTimestamp(item.created_at ? new Date(item.created_at).getTime() / 1000 : 0)}</Text>
            </View>
          ))
        ) : (
          <EmptyState title={t("historyEmptyTitle")} description={t("historyEmptyDesc")} />
        )}
      </Card>
    </ScrollView>
  );
}
