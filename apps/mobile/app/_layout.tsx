import { Stack } from "expo-router";
import { StatusBar } from "react-native";
import { SessionProvider } from "@/lib/session";
import { theme } from "@/components/ui";

export default function RootLayout() {
  return (
    <SessionProvider>
      <StatusBar barStyle="light-content" backgroundColor={theme.colors.background} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: theme.colors.background },
        }}
      />
    </SessionProvider>
  );
}
