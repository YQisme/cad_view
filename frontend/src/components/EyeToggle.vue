<template>
  <button
    type="button"
    class="eye-btn"
    :class="{ visible: visible, hidden: !visible }"
    :title="visible ? '点击隐藏' : '点击显示'"
    :aria-label="visible ? '显示中' : '已隐藏'"
    @click.stop="$emit('toggle')"
  >
    <!-- 睁眼：显示中 -->
    <svg v-if="visible" class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
    </svg>
    <!-- 闭眼：已隐藏 -->
    <svg v-else class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <path d="M1 1l22 22" />
      <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
    </svg>
  </button>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: true },
})
defineEmits(['toggle'])
</script>

<style scoped>
.eye-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  flex-shrink: 0;
}
.eye-btn:hover {
  background: rgba(255, 255, 255, 0.08);
}
.eye-btn.visible {
  color: #58a6ff;
}
.eye-btn.hidden {
  color: #6e7681;
}
.icon {
  width: 18px;
  height: 18px;
}
</style>
