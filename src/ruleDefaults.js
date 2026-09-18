export function createRuleDefaults(parent, business, existingRules = []) {
  const existingCodes = new Set(existingRules.map((rule) => String(rule.code)));
  const random = crypto.getRandomValues(new Uint32Array(1))[0];
  const first = random % 900000;
  let code;
  for (let offset = 0; offset < 900000; offset += 1) {
    const candidate = String(100000 + (first + offset) % 900000);
    if (!existingCodes.has(candidate)) {
      code = candidate;
      break;
    }
  }
  if (!code) throw new Error("6 位规则编码已用完，请清理不再使用的规则");
  return { code, parent, business, provider: "", account: "", threshold: 1000, fluctuation: 0, debounce: "10m", purpose: "", tag: "", enabled: true };
}
