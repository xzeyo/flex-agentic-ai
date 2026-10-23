import { defineConfig, globalIgnores } from "eslint/config";
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default defineConfig([
  globalIgnores([".next/**", "next-env.d.ts"]),
  js.configs.recommended,
  tseslint.configs.recommended,
  { files: ["src/**/*.{ts,tsx}"], plugins: {"react-hooks": reactHooks}, rules: reactHooks.configs.recommended.rules },
  { languageOptions: {globals: {...globals.browser, ...globals.node}} },
]);
