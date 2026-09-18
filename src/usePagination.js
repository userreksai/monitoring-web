import { computed, reactive, ref, watch } from "vue";

export function usePagination(rows, filters = []) {
  const page = ref(1);
  const pageSize = ref(10);
  const total = computed(() => rows.value.length);
  const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
  function goTo(value) {
    const requested = Number(value);
    if (!Number.isFinite(requested)) return;
    page.value = Math.min(pageCount.value, Math.max(1, Math.trunc(requested)));
  }
  watch([pageSize, ...filters], () => { page.value = 1; }, { flush: "sync" });
  watch(pageCount, () => goTo(page.value), { flush: "sync" });
  const start = computed(() => total.value ? (page.value - 1) * pageSize.value + 1 : 0);
  const end = computed(() => Math.min(page.value * pageSize.value, total.value));
  const items = computed(() => rows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value));
  const pages = computed(() => {
    const first = Math.max(1, Math.min(page.value - 2, pageCount.value - 4));
    return Array.from({ length: Math.min(5, pageCount.value) }, (_, index) => first + index);
  });
  return reactive({ page, pageSize, total, pageCount, start, end, items, pages, goTo });
}
