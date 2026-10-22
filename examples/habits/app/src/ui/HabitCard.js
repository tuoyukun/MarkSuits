import { Pressable, Text, View } from "react-native";

import { styles } from "./theme";

const WEEKDAY = ["S", "M", "T", "W", "T", "F", "S"];

function streakLabel(n) {
  return n === 0 ? "No streak yet" : `${n}-day streak`;
}

// One habit: its name, its streak and the last 7 days as toggles (`days`: YYYY-MM-DD, oldest first).
export default function HabitCard({ habit, days, onToggle }) {
  const done = new Set(habit.days);
  return (
    <View style={styles.card} testID={`habit-${habit.name}`}>
      <View style={styles.cardHead}>
        <Text style={styles.name}>{habit.name}</Text>
        <Text style={styles.streak} testID={`streak-${habit.name}`}>{streakLabel(habit.streak)}</Text>
      </View>
      <View style={styles.week}>
        {days.map((day) => {
          const on = done.has(day);
          const d = new Date(day + "T00:00:00Z");
          return (
            <Pressable
              key={day}
              testID={`day-${habit.name}-${day}`}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: on }}
              accessibilityLabel={`${habit.name} ${day}`}
              onPress={() => onToggle(habit.id, day)}
              style={styles.day}
            >
              <Text style={styles.dayName}>{WEEKDAY[d.getUTCDay()]}</Text>
              <View style={[styles.dot, on && styles.dotOn]}>
                <Text style={[styles.dayNum, on && styles.dayNumOn]}>{d.getUTCDate()}</Text>
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
