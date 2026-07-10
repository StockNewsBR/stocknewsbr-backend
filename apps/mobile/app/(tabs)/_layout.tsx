import { Tabs, router } from "expo-router";
import { useEffect } from "react";

import { theme } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function TabsLayout() {
  const { ready, token } = useSession();
  const { t } = useI18n();
  const loggedOut = ready && !token;

  // Navigate imperatively once instead of rendering <Redirect> every render:
  // paired declarative redirects ("/" <-> "/(tabs)") ping-pong into a render loop.
  useEffect(() => {
    if (loggedOut) {
      router.replace("/");
    }
  }, [loggedOut]);

  if (loggedOut) {
    return null;
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: theme.colors.accent,
        tabBarInactiveTintColor: theme.colors.muted,
        tabBarStyle: {
          backgroundColor: theme.colors.surface,
          borderTopColor: theme.colors.line,
          height: 64,
          paddingBottom: 10,
          paddingTop: 8,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: "700",
        },
      }}
    >
      <Tabs.Screen name="index" options={{ title: t("tabHome") }} />
      <Tabs.Screen name="market" options={{ title: t("tabMarket") }} />
      <Tabs.Screen name="social" options={{ title: t("tabSocial") }} />
      <Tabs.Screen name="polls" options={{ title: t("tabPolls") }} />
      <Tabs.Screen name="profile" options={{ title: t("tabProfile") }} />
    </Tabs>
  );
}
