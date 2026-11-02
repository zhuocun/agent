import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const srcDir = join(dirname(fileURLToPath(import.meta.url)), "../src");

function withExtension(specifier) {
  if (/\.(?:ts|tsx|js|mjs|cjs|json)$/.test(specifier)) return [specifier];
  return [specifier, `${specifier}.ts`, `${specifier}.tsx`];
}

export async function resolve(specifier, context, nextResolve) {
  const target = specifier.startsWith("@/")
    ? pathToFileURL(join(srcDir, specifier.slice(2))).href
    : specifier;
  let lastError;
  for (const candidate of withExtension(target)) {
    try {
      return await nextResolve(candidate, context);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}
