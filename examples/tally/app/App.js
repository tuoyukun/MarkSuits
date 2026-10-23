import AsyncStorage from "@react-native-async-storage/async-storage";
import { useEffect, useState } from "react";
import { Text } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { addCounter, bump, makeStore } from "./src/tally";
import CounterForm from "./src/ui/CounterForm";
import CounterList from "./src/ui/CounterList";
import { styles } from "./src/ui/theme";

// The storage key comes from .env at bundle time, so each end-to-end run starts empty.
const store = makeStore(AsyncStorage, process.env.EXPO_PUBLIC_STORAGE_KEY || "tally");

export default function App() {
  const [counters, setCounters] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    store.load().then(setCounters, () => { setCounters([]); setError("Could not load your counters."); });
  }, []);

  const change = (next) => {
    setCounters(next);
    store.save(counters).catch(() => setError("Could not save your counters."));
  };

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.screen}>
        <Text style={styles.title}>Tally</Text>
        <CounterForm onAdd={(name) => change(addCounter(counters, name))} busy={!counters} />
        <CounterList
          loading={!counters}
          error={error}
          counters={counters || []}
          onBump={(id, delta) => change(bump(counters, id, delta))}
        />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
