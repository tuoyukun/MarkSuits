import { ScrollView, Text, View } from "react-native";

import CounterForm from "./CounterForm";
import CounterList from "./CounterList";
import { styles } from "./theme";

// Every state in design.md, with mock props. preview.sh bundles this into preview.html.
const COUNTERS = [
  { id: 1, name: "Water", count: 3 },
  { id: 2, name: "Pages of the book I am reading this month", count: 0 },
];
const log = (...args) => console.log(...args);

const STATES = [
  ["S-1 form: empty", <CounterForm onAdd={log} />],
  ["S-2 form: typing", <CounterForm onAdd={log} initialName="Water" />],
  ["S-3 form: busy", <CounterForm onAdd={log} busy initialName="Water" />],
  ["S-4 list: loading", <CounterList counters={[]} loading onBump={log} />],
  ["S-5 list: error", <CounterList counters={COUNTERS} error="Could not save your counters." onBump={log} />],
  ["S-6 list: empty", <CounterList counters={[]} onBump={log} />],
  ["S-7 list: counters", <CounterList counters={COUNTERS} onBump={log} />],
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
