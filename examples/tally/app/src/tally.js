// Counters and where they are kept. Plain JS, no React Native imports, so it unit-tests in Node.
// A counter is {id, name, count}; the list is saved as JSON under one storage key.

export function addCounter(list, name) {
  const id = list.reduce((max, c) => Math.max(max, c.id), 0) + 1;
  return [...list, { id, name, count: 0 }];
}

// Counts never go below zero.
export function bump(list, id, delta) {
  return list.map((c) => (c.id === id ? { ...c, count: Math.max(0, c.count + delta) } : c));
}

// `storage`: anything with AsyncStorage's getItem / setItem.
export function makeStore(storage, key) {
  return {
    async load() {
      const raw = await storage.getItem(key);
      return raw ? JSON.parse(raw) : [];
    },
    save: (list) => storage.setItem(key, JSON.stringify(list)),
  };
}
