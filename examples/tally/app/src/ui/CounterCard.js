import { Pressable, Text, View } from "react-native";

import { styles } from "./theme";

function Step({ label, hint, testID, disabled = false, onPress }) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={hint}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.step, disabled && styles.buttonOff]}
    >
      <Text style={styles.stepText}>{label}</Text>
    </Pressable>
  );
}

// One counter: its name, − (disabled at zero), the count, +.
export default function CounterCard({ counter, onBump }) {
  const { id, name, count } = counter;
  return (
    <View style={styles.card} testID={`counter-${name}`}>
      <Text style={styles.name}>{name}</Text>
      <View style={styles.row}>
        <Step label="−" hint={`${name} minus one`} testID={`minus-${name}`} disabled={count === 0}
          onPress={() => onBump(id, -1)} />
        <Text style={styles.count} testID={`count-${name}`}>{count}</Text>
        <Step label="+" hint={`${name} plus one`} testID={`plus-${name}`} onPress={() => onBump(id, 1)} />
      </View>
    </View>
  );
}
