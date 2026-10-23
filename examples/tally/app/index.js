import { registerRootComponent } from "expo";

import App from "./App";
import Preview from "./src/ui/Preview";

// preview.sh bundles the UI preview instead of the app.
registerRootComponent(process.env.EXPO_PUBLIC_PREVIEW ? Preview : App);
