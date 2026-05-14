import { useEffect, useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";

import { getPoll, getPollHistory, votePoll } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import { Button, Card, EmptyState, Field, Pill, SectionHeader, theme } from "@/components/ui";
import { useSession } from "@/lib/session";

export default function PollsTab() {
  const { token } = useSession();
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
        getPoll(ticker.trim().toUpperCase()).catch(() => null),
        getPollHistory(ticker.trim().toUpperCase()).catch(() => ({ history: [] })),
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
      setStatus("Faça login para votar.");
      return;
    }

    try {
      const nextPoll = await votePoll(token, ticker.trim().toUpperCase(), option);
      setPoll(nextPoll);
      setStatus("Voto registrado.");
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
        <Pill label="Polls IA" tone="warning" />
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          Enquetes semanais por ticker.
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          Leitura simples, votacao rapida e historico para comparar a evolucao da tese.
        </Text>
      </View>

      <Card>
        <SectionHeader title="Ticker" subtitle="Troque o papel para ver a enquete ativa e o historico." />
        <Field value={ticker} onChangeText={(value) => setTicker(value.toUpperCase())} placeholder="PETR4" />
        <Button label="Atualizar poll" onPress={loadPoll} variant="secondary" />
      </Card>

      <Card>
        <SectionHeader title="Enquete atual" subtitle={poll?.question || "Nenhuma enquete carregada."} />
        {options.length ? (
          options.map((option: any) => (
            <View key={option.key} style={{ gap: 8, marginTop: 4 }}>
              <Button label={`${option.key} | ${option.label}`} onPress={() => handleVote(option.key)} loading={loading} />
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{Number(option.votes || 0)} votos</Text>
            </View>
          ))
        ) : (
          <EmptyState title="Sem opcoes" description="O backend ainda nao retornou opcoes para esta enquete." />
        )}
        {status ? <Text style={{ color: theme.colors.muted, fontSize: 13 }}>{status}</Text> : null}
      </Card>

      <Card>
        <SectionHeader title="Historico" subtitle="As ultimas enquetes do ativo." />
        {history.length ? (
          history.map((item: any) => (
            <View key={item.id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.colors.line, gap: 4 }}>
              <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{item.question}</Text>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{formatTimestamp(item.created_at ? new Date(item.created_at).getTime() / 1000 : 0)}</Text>
            </View>
          ))
        ) : (
          <EmptyState title="Sem historico" description="Nenhuma enquete antiga encontrada para esse ticker." />
        )}
      </Card>
    </ScrollView>
  );
}
