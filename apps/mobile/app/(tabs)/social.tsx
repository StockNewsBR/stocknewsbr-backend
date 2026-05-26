import { useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { router } from "expo-router";

import { createTickerPost, getTickerFeed } from "@/lib/api";
import { formatRelativeSeconds } from "@/lib/format";
import { Button, Card, EmptyState, Field, Pill, SectionHeader, theme } from "@/components/ui";
import { useSession } from "@/lib/session";

const SENTIMENTS = ["bullish", "bearish", "neutral"];

export default function SocialTab() {
  const { token, access } = useSession();
  const [ticker, setTicker] = useState("PETR4");
  const [feed, setFeed] = useState<Record<string, any> | null>(null);
  const [draft, setDraft] = useState("");
  const [sentiment, setSentiment] = useState("neutral");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  async function loadFeed() {
    if (!token || !ticker.trim()) {
      return;
    }

    setLoading(true);
    try {
      const nextFeed = await getTickerFeed(token, ticker.trim().toUpperCase()).catch(() => null);
      setFeed(nextFeed);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadFeed();
  }, [token, ticker]);

  async function handlePublish() {
    if (!token || !draft.trim()) {
      return;
    }

    setBusy(true);
    setStatus(null);

    try {
      const published = await createTickerPost(token, ticker.trim().toUpperCase(), {
        text: draft.trim(),
        sentiment,
      });
      setDraft("");
      setStatus(published?.error ? published.reason || published.error : "Post publicado com sucesso.");
      await loadFeed();
    } catch (requestError) {
      setStatus(requestError instanceof Error ? requestError.message : "post_failed");
    } finally {
      setBusy(false);
    }
  }

  const posts = Array.isArray(feed?.posts) ? feed.posts : [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: theme.colors.background }}
      contentContainerStyle={{ padding: 20, gap: 16 }}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={loadFeed} tintColor={theme.colors.accent} />}
    >
      <View style={{ gap: 8, paddingTop: 10 }}>
        <Pill label="Social por ticker" tone="accent" />
        <Text style={{ color: theme.colors.text, fontSize: 30, fontWeight: "800", lineHeight: 34 }}>
          Feed, post e contexto em uma tela so.
        </Text>
        <Text style={{ color: theme.colors.muted, fontSize: 14, lineHeight: 21 }}>
          Publique, leia comentarios e navegue direto para o detalhe do ativo.
        </Text>
      </View>

      <Card>
        <SectionHeader title="Ticker" subtitle="Troque o ativo e a tela recarrega o feed associado." />
        <Field value={ticker} onChangeText={(value) => setTicker(value.toUpperCase())} placeholder="PETR4" />
        <View style={{ flexDirection: "row", gap: 10 }}>
          <Button label="Abrir ticker" onPress={() => router.push(`/ticker/${ticker.trim().toUpperCase() || "PETR4"}`)} variant="secondary" />
          <Button label="Atualizar" onPress={loadFeed} loading={loading} />
        </View>
      </Card>

      <Card>
        <SectionHeader title="Novo post" subtitle="Conte algo do ativo ou do fluxo que voce esta vendo agora." />
        <TextInput
          multiline
          value={draft}
          onChangeText={setDraft}
          placeholder="Escreva sua leitura..."
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
        <Button label="Publicar no feed" onPress={handlePublish} loading={busy} />
        {status ? <Text style={{ color: theme.colors.muted, fontSize: 13 }}>{status}</Text> : null}
      </Card>

      <Card>
        <SectionHeader
          title="Feed"
          subtitle={feed?.count ? `${feed.count} posts carregados` : "Sem posts carregados ainda"}
        />
        {posts.length ? (
          posts.map((post: any) => (
            <View
              key={post.id}
              style={{
                gap: 8,
                paddingVertical: 12,
                borderBottomWidth: 1,
                borderBottomColor: theme.colors.line,
              }}
            >
              <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: theme.colors.text, fontWeight: "700" }}>{post.user || post.display_name || "Usuario"}</Text>
                  <Text style={{ color: theme.colors.muted, fontSize: 12 }}>{formatRelativeSeconds(Date.now() / 1000 - Number(post.timestamp || 0))} ago</Text>
                </View>
                {post.ticker ? <Pill label={post.ticker} tone="info" /> : null}
              </View>
              <Text style={{ color: theme.colors.text, lineHeight: 20 }}>{post.text}</Text>
              <Text style={{ color: theme.colors.muted, fontSize: 12 }}>
                {Array.isArray(post.comments) ? `${post.comments.length} comments` : "0 comments"} | {Number(post.likes || 0)} likes | {Number(post.reposts || 0)} reposts
              </Text>
            </View>
          ))
        ) : (
          <EmptyState title="Sem feed" description="Ainda nao ha posts para este ticker." />
        )}
      </Card>

      {access?.telegram_linked ? (
        <Card>
          <SectionHeader title="Telegram" subtitle="O acesso do Telegram ja esta conectado na conta." />
        </Card>
      ) : null}
    </ScrollView>
  );
}
