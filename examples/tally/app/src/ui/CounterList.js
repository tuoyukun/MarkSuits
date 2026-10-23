import { ScrollView, Text, View } from "react-native";

import CounterCard from "./CounterCard";
import { styles } from "./theme";

// S-4 loading, S-5 error, S-6 empty, S-7 counters.
export default function CounterList({ counters, loading = false, error = "", onBump }) {
  if (loading) return <Text style={styles.note}>Loading…</Text>;
  return (
    <View style={styles.list}>
      {error ? <Text style={styles.error} testID="error">{error}</Text> : null}
      {counters.length === 0 ? (
        <Text style={styles.note} testID="empty">No counters yet. Add one above.</Text>
      ) : (
        <ScrollView keyboardShouldPersistTaps="handled">
          {counters.map((c) => <CounterCard key={c.id} counter={c} onBump={onBump} />)}
        </ScrollView>
      )}
    </View>
  );
}
