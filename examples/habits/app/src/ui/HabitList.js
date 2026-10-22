import { ScrollView, Text, View } from "react-native";

import HabitCard from "./HabitCard";
import { styles } from "./theme";

// S-4 loading, S-5 error, S-6 empty, S-7 habits.
export default function HabitList({ habits, days, loading = false, error = "", onToggle }) {
  if (loading) return <Text style={styles.note}>Loading…</Text>;
  return (
    <View style={styles.list}>
      {error ? <Text style={styles.error} testID="error">{error}</Text> : null}
      {habits.length === 0 ? (
        <Text style={styles.note} testID="empty">No habits yet. Add one above.</Text>
      ) : (
        <ScrollView>
          {habits.map((h) => <HabitCard key={h.id} habit={h} days={days} onToggle={onToggle} />)}
        </ScrollView>
      )}
    </View>
  );
}
