import js from "@eslint/js";
import jsdoc from "eslint-plugin-jsdoc";
import globals from "globals";

export default [
  {
    ignores: [".vendor/**", "data/**", "node_modules/**"],
  },
  {
    files: ["apps/api/app/static/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: globals.browser,
    },
    plugins: { jsdoc },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": ["error", { "argsIgnorePattern": "^_", "varsIgnorePattern": "^_" }],
      "jsdoc/check-alignment": "error",
      "jsdoc/check-param-names": "error",
      "jsdoc/check-tag-names": "error",
      "jsdoc/check-types": "error",
      "jsdoc/require-jsdoc": [
        "error",
        {
          "publicOnly": { "esm": true, "cjs": false, "window": false },
          "require": {
            "ArrowFunctionExpression": false,
            "ClassDeclaration": true,
            "ClassExpression": false,
            "FunctionDeclaration": true,
            "FunctionExpression": false,
            "MethodDefinition": false
          }
        }
      ]
    }
  }
];
