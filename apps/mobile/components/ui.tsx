import type { ReactNode } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

export const theme = {
  colors: {
    background: "#061018",
    surface: "#0d1724",
    surfaceSoft: "#111f31",
    surfaceGlow: "#16283c",
    line: "rgba(255,255,255,0.08)",
    text: "#eef4fb",
    muted: "#8fa4b8",
    accent: "#1fd38a",
    accentSoft: "rgba(31, 211, 138, 0.16)",
    warning: "#ffb547",
    danger: "#ff6b6b",
    info: "#6aa8ff",
  },
};

type CardProps = {
  children: ReactNode;
  style?: object;
};

export function AppScreen({ children }: { children: ReactNode }) {
  return <SafeAreaView style={styles.safe}>{children}</SafeAreaView>;
}

export function Card({ children, style }: CardProps) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <View style={styles.sectionHeader}>
      <View style={{ flex: 1 }}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {subtitle ? <Text style={styles.sectionSubtitle}>{subtitle}</Text> : null}
      </View>
      {action}
    </View>
  );
}

export function Pill({
  label,
  tone = "muted",
}: {
  label: string;
  tone?: "muted" | "accent" | "info" | "warning" | "danger";
}) {
  return (
    <View
      style={[
        styles.pill,
        tone === "accent" && styles.pillAccent,
        tone === "info" && styles.pillInfo,
        tone === "warning" && styles.pillWarning,
        tone === "danger" && styles.pillDanger,
      ]}
    >
      <Text
        style={[
          styles.pillText,
          tone === "accent" && styles.pillTextAccent,
          tone === "info" && styles.pillTextInfo,
          tone === "warning" && styles.pillTextWarning,
          tone === "danger" && styles.pillTextDanger,
        ]}
      >
        {label}
      </Text>
    </View>
  );
}

export function Button({
  label,
  onPress,
  variant = "primary",
  disabled,
  loading,
}: {
  label: string;
  onPress?: () => void | Promise<void>;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.buttonBase,
        variant === "primary" && styles.buttonPrimary,
        variant === "secondary" && styles.buttonSecondary,
        variant === "ghost" && styles.buttonGhost,
        (disabled || loading) && styles.buttonDisabled,
        pressed && !disabled && !loading && styles.buttonPressed,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === "primary" ? theme.colors.background : theme.colors.text} />
      ) : (
        <Text
          style={[
            styles.buttonText,
            variant === "primary" && styles.buttonTextPrimary,
            variant === "secondary" && styles.buttonTextSecondary,
            variant === "ghost" && styles.buttonTextGhost,
          ]}
        >
          {label}
        </Text>
      )}
    </Pressable>
  );
}

export function Field({
  value,
  onChangeText,
  placeholder,
  keyboardType,
  secureTextEntry,
  autoCapitalize = "none",
}: {
  value: string;
  onChangeText: (text: string) => void;
  placeholder?: string;
  keyboardType?: "default" | "email-address" | "numeric" | "phone-pad";
  secureTextEntry?: boolean;
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
}) {
  return (
    <TextInput
      value={value}
      onChangeText={onChangeText}
      placeholder={placeholder}
      placeholderTextColor={theme.colors.muted}
      style={styles.input}
      keyboardType={keyboardType}
      secureTextEntry={secureTextEntry}
      autoCapitalize={autoCapitalize}
    />
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <View style={styles.emptyState}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <Text style={styles.sectionSubtitle}>{description}</Text>
    </View>
  );
}

export function StatTile({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: string;
  tone?: "muted" | "accent" | "info" | "warning" | "danger";
}) {
  return (
    <View style={styles.statTile}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text
        style={[
          styles.statValue,
          tone === "accent" && styles.statValueAccent,
          tone === "info" && styles.statValueInfo,
          tone === "warning" && styles.statValueWarning,
          tone === "danger" && styles.statValueDanger,
        ]}
      >
        {value}
      </Text>
    </View>
  );
}

export function Divider() {
  return <View style={styles.divider} />;
}

export function TickerChip({ symbol }: { symbol: string }) {
  return (
    <View style={styles.tickerChip}>
      <Text style={styles.tickerChipText}>{symbol}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  card: {
    borderRadius: 22,
    padding: 16,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.line,
    gap: 12,
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 12,
  },
  sectionTitle: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: "700",
  },
  sectionSubtitle: {
    color: theme.colors.muted,
    fontSize: 13,
    marginTop: 4,
    lineHeight: 18,
  },
  pill: {
    alignSelf: "flex-start",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.06)",
    borderWidth: 1,
    borderColor: theme.colors.line,
  },
  pillAccent: {
    backgroundColor: theme.colors.accentSoft,
    borderColor: "rgba(31, 211, 138, 0.24)",
  },
  pillInfo: {
    backgroundColor: "rgba(106, 168, 255, 0.16)",
    borderColor: "rgba(106, 168, 255, 0.24)",
  },
  pillWarning: {
    backgroundColor: "rgba(255, 181, 71, 0.16)",
    borderColor: "rgba(255, 181, 71, 0.28)",
  },
  pillDanger: {
    backgroundColor: "rgba(255, 107, 107, 0.16)",
    borderColor: "rgba(255, 107, 107, 0.28)",
  },
  pillText: {
    color: theme.colors.muted,
    fontSize: 12,
    fontWeight: "600",
  },
  pillTextAccent: {
    color: theme.colors.accent,
  },
  pillTextInfo: {
    color: theme.colors.info,
  },
  pillTextWarning: {
    color: theme.colors.warning,
  },
  pillTextDanger: {
    color: theme.colors.danger,
  },
  buttonBase: {
    minHeight: 48,
    paddingHorizontal: 16,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonPrimary: {
    backgroundColor: theme.colors.accent,
  },
  buttonSecondary: {
    backgroundColor: theme.colors.surfaceSoft,
    borderWidth: 1,
    borderColor: theme.colors.line,
  },
  buttonGhost: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: theme.colors.line,
  },
  buttonDisabled: {
    opacity: 0.55,
  },
  buttonPressed: {
    transform: [{ scale: 0.985 }],
  },
  buttonText: {
    fontSize: 14,
    fontWeight: "700",
  },
  buttonTextPrimary: {
    color: theme.colors.background,
  },
  buttonTextSecondary: {
    color: theme.colors.text,
  },
  buttonTextGhost: {
    color: theme.colors.text,
  },
  input: {
    minHeight: 48,
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: theme.colors.text,
    backgroundColor: theme.colors.surfaceSoft,
    borderWidth: 1,
    borderColor: theme.colors.line,
  },
  emptyState: {
    paddingVertical: 12,
    gap: 8,
  },
  statTile: {
    flex: 1,
    minWidth: 110,
    borderRadius: 18,
    backgroundColor: theme.colors.surfaceSoft,
    borderWidth: 1,
    borderColor: theme.colors.line,
    padding: 12,
    gap: 4,
  },
  statLabel: {
    color: theme.colors.muted,
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  statValue: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
  statValueAccent: {
    color: theme.colors.accent,
  },
  statValueInfo: {
    color: theme.colors.info,
  },
  statValueWarning: {
    color: theme.colors.warning,
  },
  statValueDanger: {
    color: theme.colors.danger,
  },
  divider: {
    height: 1,
    backgroundColor: theme.colors.line,
    opacity: 0.9,
  },
  tickerChip: {
    alignSelf: "flex-start",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: "rgba(255,255,255,0.06)",
    borderWidth: 1,
    borderColor: theme.colors.line,
  },
  tickerChipText: {
    color: theme.colors.text,
    fontSize: 12,
    fontWeight: "700",
  },
});
