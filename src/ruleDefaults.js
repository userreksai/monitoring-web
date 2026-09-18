export function createRuleDefaults(parent, business, existingRules = []) {
  const existingCodes = new Set(existingRules.map((rule) => rule.code));
  let code;
  do {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    code = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  } while (existingCodes.has(code));
  return { code, parent, business, provider: "", account: "", threshold: 1000, fluctuation: 0, debounce: "10m", purpose: "", tag: "", enabled: true };
}
