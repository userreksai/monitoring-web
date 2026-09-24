import { computed, ref, watch } from "vue";

export function useRuleBusiness(businesses, rules) {
  const selectedId = ref(null);
  watch(businesses, (rows) => {
    if (!rows.some((row) => row.id === selectedId.value)) {
      selectedId.value = (rows.find((row) => row.name === "短信资源余额") || rows[0])?.id ?? null;
    }
  }, { immediate: true, flush: "sync" });
  const selectedBusiness = computed(() => businesses.value.find((row) => row.id === selectedId.value));
  const businessRules = computed(() => selectedBusiness.value
    ? rules.value.filter((row) => row.parent === selectedBusiness.value.code)
    : []);
  return { selectedId, selectedBusiness, businessRules };
}
