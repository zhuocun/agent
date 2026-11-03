import { register } from "node:module";

// Lets `node --test` load the meter's pure helper and its `@/` imports.
register(new URL("./resolve-ts-hook.mjs", import.meta.url));
