// eslint 9 flat config. eslint-config-next 16 ships a native flat config;
// we spread its "core-web-vitals" preset (same ruleset as the old
// .eslintrc.json `extends: "next/core-web-vitals"`).
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

export default [
  ...nextCoreWebVitals,
  {
    // eslint-config-next 16 pulls in react-hooks v5, which adds new
    // "rules of react" (set-state-in-effect / refs / immutability) that flag
    // many pre-existing, intentional patterns. Keep this bump
    // behavior-preserving — same enforcement as the old eslint 8 setup —
    // and leave adopting these new rules (with the code fixes they want) to a
    // dedicated follow-up. exhaustive-deps stays a warning, as it was before.
    rules: {
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/refs": "off",
      "react-hooks/immutability": "off",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
];
