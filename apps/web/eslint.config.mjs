import nextVitals from "eslint-config-next/core-web-vitals";
import { defineConfig, globalIgnores } from "eslint/config";

const eslintConfig = defineConfig([
    ...nextVitals,
    {
        rules: {
            "@typescript-eslint/ban-ts-comment": "off",
            "@next/next/no-img-element": "off",
            "react-hooks/exhaustive-deps": "off",
            "react/no-unescaped-entities": "off",
            "react-hooks/incompatible-library": "off",
        },
    },
    // Override default ignores of eslint-config-next.
    globalIgnores([
        // Default ignores of eslint-config-next:
        ".next/**",
        "out/**",
        "build/**",
        "next-env.d.ts",
    ]),
]);

export default eslintConfig;
