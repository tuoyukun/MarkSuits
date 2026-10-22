import { useCallback, useEffect, useState } from "react";
import { Text } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { makeApi, week } from "./src/api";
import HabitForm from "./src/ui/HabitForm";
import HabitList from "./src/ui/HabitList";
import { styles } from "./src/ui/theme";

const api = makeApi(process.env.EXPO_PUBLIC_API_BASE || "http://127.0.0.1:8300");

export default function App() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(async (job) => {
    setBusy(true);
    try {
      await job();
      setData(await api.list());
      setError("");
    } catch (e) {
      setError(e.message || "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { run(async () => {}); }, [run]);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.screen}>
        <Text style={styles.title}>Habits</Text>
        <HabitForm busy={busy} onAdd={(name) => run(() => api.add(name))} />
        <HabitList
          loading={!data && !error}
          error={error}
          habits={data ? data.habits : []}
          days={data ? week(data.today) : []}
          onToggle={(id, day) => run(() => api.toggle(id, day))}
        />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
