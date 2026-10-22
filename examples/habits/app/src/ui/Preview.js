import { ScrollView, Text, View } from "react-native";

import { week } from "../api";
import HabitForm from "./HabitForm";
import HabitList from "./HabitList";
import { styles } from "./theme";

// Every state in design.md, with mock props. preview.sh bundles this into preview.html.
const DAYS = week("2026-03-02");
const HABITS = [
  { id: 1, name: "Read", days: ["2026-02-28", "2026-03-01", "2026-03-02"], streak: 3 },
  { id: 2, name: "Stretch for ten minutes after waking up", days: ["2026-02-25"], streak: 0 },
];
const log = (...args) => console.log(...args);

const STATES = [
  ["S-1 form: empty", <HabitForm onAdd={log} />],
  ["S-2 form: typing", <HabitForm onAdd={log} initialName="Drink water" />],
  ["S-3 form: busy", <HabitForm onAdd={log} busy initialName="Drink water" />],
  ["S-4 list: loading", <HabitList habits={[]} days={DAYS} loading onToggle={log} />],
  ["S-5 list: error", <HabitList habits={HABITS} days={DAYS} error="Could not reach the server." onToggle={log} />],
  ["S-6 list: empty", <HabitList habits={[]} days={DAYS} onToggle={log} />],
  ["S-7 list: habits", <HabitList habits={HABITS} days={DAYS} onToggle={log} />],
];

export default function Preview() {
  return (
    <ScrollView style={styles.screen}>
      <Text style={styles.title}>UI preview</Text>
      {STATES.map(([label, node]) => (
        <View key={label}>
          <Text style={styles.previewLabel}>{label}</Text>
          {node}
        </View>
      ))}
    </ScrollView>
  );
}
