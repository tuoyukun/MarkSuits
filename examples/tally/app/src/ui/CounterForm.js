import { useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";

import { colors, styles } from "./theme";

// S-1 empty field (Add disabled), S-2 typing, S-3 busy (both disabled).
export default function CounterForm({ onAdd, busy = false, initialName = "" }) {
  const [name, setName] = useState(initialName);
  const ready = name.trim().length > 0 && !busy;
  const submit = () => {
    if (!ready) return;
    onAdd(name.trim());
    setName("");
  };
  return (
    <View style={styles.form}>
      <TextInput
        testID="new-counter"
        accessibilityLabel="New counter"
        style={styles.input}
        placeholder="New counter"
        placeholderTextColor={colors.muted}
        value={name}
        onChangeText={setName}
        onSubmitEditing={submit}
        editable={!busy}
        maxLength={60}
      />
      <Pressable
        testID="add-counter"
        accessibilityRole="button"
        accessibilityState={{ disabled: !ready }}
        onPress={submit}
        style={[styles.button, !ready && styles.buttonOff]}
      >
        <Text style={styles.buttonText}>Add</Text>
      </Pressable>
    </View>
  );
}
