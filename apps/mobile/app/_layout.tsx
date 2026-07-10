import { Stack } from "expo-router";
import { StatusBar } from "react-native";
import { LanguageProvider } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import { theme } from "@/components/ui";

export default function RootLayout() {
  return (
    <LanguageProvider>
      <SessionProvider>
        <StatusBar barStyle="light-content" backgroundColor={theme.colors.background} />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: theme.colors.background },
          }}
        />
      </SessionProvider>
    </LanguageProvider>
  );
}
