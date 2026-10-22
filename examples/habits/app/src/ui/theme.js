import { StyleSheet } from "react-native";

export const colors = { bg: "#f6f5f2", card: "#ffffff", ink: "#1d1d1f", muted: "#8a8a8e",
  accent: "#2f7d5b", line: "#e3e1dc", error: "#b3261e" };

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg, paddingTop: 64, paddingHorizontal: 16 },
  title: { fontSize: 28, fontWeight: "700", color: colors.ink, marginBottom: 16 },
  form: { flexDirection: "row", gap: 8, marginBottom: 16 },
  input: { flex: 1, height: 44, borderRadius: 10, borderWidth: 1, borderColor: colors.line,
    backgroundColor: colors.card, paddingHorizontal: 12, fontSize: 16, color: colors.ink },
  button: { height: 44, paddingHorizontal: 18, borderRadius: 10, backgroundColor: colors.accent,
    justifyContent: "center" },
  buttonOff: { opacity: 0.4 },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  list: { flex: 1 },
  note: { color: colors.muted, fontSize: 15, textAlign: "center", marginTop: 32 },
  error: { color: colors.error, fontSize: 14, marginBottom: 12 },
  card: { backgroundColor: colors.card, borderRadius: 14, padding: 14, marginBottom: 12 },
  cardHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 },
  name: { fontSize: 17, fontWeight: "600", color: colors.ink, flexShrink: 1 },
  streak: { fontSize: 14, color: colors.accent, fontWeight: "600" },
  week: { flexDirection: "row", justifyContent: "space-between" },
  day: { alignItems: "center", gap: 4, minWidth: 36 },
  dayName: { fontSize: 12, color: colors.muted },
  dot: { width: 34, height: 34, borderRadius: 17, borderWidth: 1, borderColor: colors.line,
    alignItems: "center", justifyContent: "center" },
  dotOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  dayNum: { fontSize: 13, color: colors.ink },
  dayNumOn: { color: "#fff", fontWeight: "600" },
  previewLabel: { fontSize: 12, fontWeight: "700", color: colors.muted, marginTop: 24, marginBottom: 8 },
});
