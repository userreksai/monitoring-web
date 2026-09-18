import test from "node:test";
import assert from "node:assert/strict";
import { computed, effectScope, ref } from "vue";
import { usePagination } from "./usePagination.js";
import { createRuleDefaults } from "./ruleDefaults.js";

test("pagination slices rows, clamps jumps, and resets page size", () => {
  const scope = effectScope();
  scope.run(() => {
    const rows = ref(Array.from({ length: 53 }, (_, id) => ({ id })));
    const pagination = usePagination(rows);
    assert.equal(pagination.items.length, 10);
    pagination.goTo(2);
    assert.deepEqual(pagination.items.map((row) => row.id), [10,11,12,13,14,15,16,17,18,19]);
    pagination.goTo(999);
    assert.equal(pagination.page, 6);
    assert.equal(pagination.start, 51);
    assert.equal(pagination.end, 53);
    assert.equal(pagination.items.length, 3);
    assert.deepEqual(pagination.pages, [2,3,4,5,6]);
    pagination.goTo("invalid");
    assert.equal(pagination.page, 6);
    pagination.goTo(-3);
    assert.equal(pagination.page, 1);
    pagination.goTo(3);
    pagination.pageSize = 20;
    assert.equal(pagination.page, 1);
    assert.equal(pagination.items.length, 20);
    pagination.pageSize = 50;
    assert.equal(pagination.pageCount, 2);
  });
  scope.stop();
});

test("filters reset pages even when count is unchanged; deletion and empty data stay valid", () => {
  const scope = effectScope();
  scope.run(() => {
    const filter = ref(0);
    const rows = ref(Array.from({ length: 42 }, (_, id) => ({ id })));
    const filtered = computed(() => rows.value.filter((row) => row.id % 2 === filter.value));
    const pagination = usePagination(filtered, [filter]);
    pagination.goTo(3);
    filter.value = 1;
    assert.equal(pagination.page, 1);
    assert.equal(pagination.items[0].id, 1);
    pagination.goTo(3);
    rows.value = rows.value.slice(0, 40);
    assert.equal(pagination.page, 2);
    rows.value = [];
    assert.equal(pagination.page, 1);
    assert.equal(pagination.start, 0);
    assert.equal(pagination.end, 0);
    assert.deepEqual(pagination.items, []);
  });
  scope.stop();
});

test("new rule defaults contain fresh random codes and a 1000 currency threshold", () => {
  const rules = Array.from({ length: 1000 }, () => createRuleDefaults("123456", "短信商"));
  assert.equal(new Set(rules.map((rule) => rule.code)).size, rules.length);
  for (const rule of rules) {
    assert.match(rule.code, /^[0-9a-f]{32}$/);
    assert.equal(rule.threshold, 1000);
    assert.equal(rule.parent, "123456");
    assert.equal(rule.business, "短信商");
  }
});
