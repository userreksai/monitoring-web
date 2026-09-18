<script setup>
import { ref, watch } from "vue";

const props = defineProps({ pagination: { type: Object, required: true } });
const jumpPage = ref(props.pagination.page);
watch(() => props.pagination.page, (page) => { jumpPage.value = page; });
function jump() {
  props.pagination.goTo(jumpPage.value);
  jumpPage.value = props.pagination.page;
}
</script>

<template>
  <footer class="pagination" aria-label="列表分页">
    <div aria-live="polite">
      <span>共 <b>{{ pagination.total }}</b> 条，显示 {{ pagination.start }}–{{ pagination.end }} 条</span>
      <label>每页 <select v-model.number="pagination.pageSize" aria-label="每页条数"><option :value="10">10 条</option><option :value="20">20 条</option><option :value="50">50 条</option></select></label>
    </div>
    <div>
      <button :disabled="pagination.page === 1" @click="pagination.goTo(1)">首页</button>
      <button :disabled="pagination.page === 1" @click="pagination.goTo(pagination.page - 1)">上一页</button>
      <button v-for="page in pagination.pages" :key="page" :class="{ active: page === pagination.page }" :aria-current="page === pagination.page ? 'page' : undefined" :aria-label="`第 ${page} 页`" @click="pagination.goTo(page)">{{ page }}</button>
      <button :disabled="pagination.page === pagination.pageCount" @click="pagination.goTo(pagination.page + 1)">下一页</button>
      <button :disabled="pagination.page === pagination.pageCount" @click="pagination.goTo(pagination.pageCount)">末页</button>
      <span>共 {{ pagination.pageCount }} 页</span>
      <form @submit.prevent="jump"><label>前往 <input v-model="jumpPage" type="number" min="1" step="1" aria-label="跳转页码" /> 页</label><button type="submit">跳转</button></form>
    </div>
  </footer>
</template>
