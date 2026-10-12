<template>
  <div
    class="custom-select"
    :class="[
      `custom-select--${size}`,
      {
        'is-disabled': disabled,
        'is-open': isOpen,
        'is-multiple': multiple,
        'is-filterable': filterable,
      },
    ]"
    ref="selectRef"
  >
    <!-- 触发器 -->
    <div
      class="custom-select__trigger"
      :class="{ 'is-focus': isOpen }"
      :tabindex="disabled ? -1 : 0"
      @click="toggleOpen"
      @keydown.enter="toggleOpen"
      @keydown.space.prevent="toggleOpen"
      @keydown.esc="isOpen = false"
    >
      <!-- 多选标签 -->
      <template v-if="multiple && selectedLabels.length > 0">
        <div class="custom-select__tags">
          <span
            v-for="(item, idx) in selectedLabels"
            :key="idx"
            class="custom-select__tag"
          >
            {{ item.label }}
            <span class="custom-select__tag-close" @click.stop="removeTag(item.value)">&times;</span>
          </span>
        </div>
      </template>
      <!-- 单选显示值 -->
      <span v-else-if="!multiple && selectedLabel" class="custom-select__value">
        {{ selectedLabel }}
      </span>
      <!-- 占位符 -->
      <span v-else class="custom-select__placeholder">{{ placeholder }}</span>

      <span class="custom-select__suffix">
        <!-- 清除按钮 -->
        <span
          v-if="clearable && hasValue && !disabled"
          class="custom-select__clear"
          @click.stop="handleClear"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M3.5 3.5L10.5 10.5M10.5 3.5L3.5 10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
          </svg>
        </span>
        <!-- 箭头 -->
        <span class="custom-select__arrow" :class="{ 'is-reversed': isOpen }">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M3 5L6 8L9 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </span>
      </span>
    </div>

    <!-- 下拉菜单 (Teleport 到 body 避免被父容器遮挡) -->
    <Teleport to="body">
      <transition name="dropdown-slide">
        <div v-if="isOpen" class="custom-select__dropdown" :style="dropdownStyle" @click.stop>
          <!-- 搜索框 -->
          <div v-if="filterable" class="custom-select__search">
            <input
              ref="searchInputRef"
              v-model="searchQuery"
              class="custom-select__search-input"
              :placeholder="searchPlaceholder"
              @input="handleSearchInput"
            />
            <svg v-if="searchQuery" class="custom-select__search-clear" width="14" height="14" viewBox="0 0 14 14" fill="none" @click="searchQuery = ''">
              <path d="M3.5 3.5L10.5 10.5M10.5 3.5L3.5 10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
          </div>
          <!-- 选项列表 -->
          <div class="custom-select__options" ref="optionsRef">
            <div
              v-for="option in filteredOptions"
              :key="option.value"
              class="custom-select__option"
              :class="{
                selected: isSelected(option.value),
                highlighted: highlightedIndex === getOptionIndex(option),
              }"
              @click="selectOption(option)"
              @mouseenter="highlightedIndex = getOptionIndex(option)"
            >
              <span class="custom-select__option-label">{{ option.label }}</span>
              <span v-if="isSelected(option.value)" class="custom-select__option-check">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 7L6 10L11 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </span>
            </div>
            <!-- 空状态 -->
            <div v-if="filteredOptions.length === 0" class="custom-select__empty">
              {{ emptyText }}
            </div>
            <!-- 允许创建 -->
            <div
              v-if="allowCreate && searchQuery && !isExactMatch"
              class="custom-select__option custom-select__option--create"
              :class="{ highlighted: highlightedIndex === filteredOptions.length }"
              @click="createOption"
              @mouseenter="highlightedIndex = filteredOptions.length"
            >
              <span class="custom-select__option-label">创建 "{{ searchQuery }}"</span>
            </div>
          </div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number, Array], default: null },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '请选择' },
  disabled: { type: Boolean, default: false },
  clearable: { type: Boolean, default: false },
  multiple: { type: Boolean, default: false },
  filterable: { type: Boolean, default: false },
  allowCreate: { type: Boolean, default: false },
  size: { type: String, default: 'default' }, // small / default / large
  emptyText: { type: String, default: '暂无数据' },
  searchPlaceholder: { type: String, default: '搜索...' },
})

const emit = defineEmits(['update:modelValue', 'change'])

const selectRef = ref(null)
const searchInputRef = ref(null)
const optionsRef = ref(null)
const isOpen = ref(false)
const searchQuery = ref('')
const highlightedIndex = ref(-1)
const createdOptions = ref([])
const dropdownStyle = ref({})

// 合并内置选项和动态创建的选项
const allOptions = computed(() => {
  if (props.allowCreate) {
    const existingValues = new Set(props.options.map((o) => o.value))
    const uniqueCreated = createdOptions.value.filter((o) => !existingValues.has(o.value))
    return [...props.options, ...uniqueCreated]
  }
  return props.options
})

// 过滤选项
const filteredOptions = computed(() => {
  if (!searchQuery.value) return allOptions.value
  const q = searchQuery.value.toLowerCase()
  return allOptions.value.filter((o) => o.label.toLowerCase().includes(q) || String(o.value).toLowerCase().includes(q))
})

// 是否为精确匹配
const isExactMatch = computed(() => {
  if (!searchQuery.value) return false
  const q = searchQuery.value.toLowerCase()
  return allOptions.value.some(
    (o) => o.label.toLowerCase() === q || String(o.value).toLowerCase() === q
  )
})

// 选中值
const selectedValues = computed(() => {
  if (props.multiple) {
    return Array.isArray(props.modelValue) ? props.modelValue : []
  }
  return props.modelValue !== null && props.modelValue !== undefined ? [props.modelValue] : []
})

// 选中的标签文本
const selectedLabels = computed(() => {
  return selectedValues.value
    .map((v) => {
      const opt = allOptions.value.find((o) => o.value === v)
      return opt ? { label: opt.label, value: opt.value } : null
    })
    .filter(Boolean)
})

const selectedLabel = computed(() => {
  if (selectedLabels.value.length > 0) return selectedLabels.value[0].label
  return ''
})

const hasValue = computed(() => {
  if (props.multiple) return Array.isArray(props.modelValue) && props.modelValue.length > 0
  return props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== ''
})

// 判断是否选中
function isSelected(value) {
  if (props.multiple) {
    return Array.isArray(props.modelValue) && props.modelValue.includes(value)
  }
  return props.modelValue === value
}

function getOptionIndex(option) {
  return filteredOptions.value.indexOf(option)
}

// 选择选项
function selectOption(option) {
  if (props.disabled) return

  if (props.multiple) {
    const current = Array.isArray(props.modelValue) ? [...props.modelValue] : []
    const idx = current.indexOf(option.value)
    if (idx > -1) {
      current.splice(idx, 1)
    } else {
      current.push(option.value)
    }
    emit('update:modelValue', current)
    emit('change', current)
  } else {
    emit('update:modelValue', option.value)
    emit('change', option.value)
    isOpen.value = false
    searchQuery.value = ''
  }
}

// 移除标签（多选）
function removeTag(value) {
  if (props.disabled) return
  const current = Array.isArray(props.modelValue) ? [...props.modelValue] : []
  const idx = current.indexOf(value)
  if (idx > -1) {
    current.splice(idx, 1)
    emit('update:modelValue', current)
    emit('change', current)
  }
}

// 清除
function handleClear() {
  if (props.disabled) return
  if (props.multiple) {
    emit('update:modelValue', [])
    emit('change', [])
  } else {
    emit('update:modelValue', null)
    emit('change', null)
  }
  searchQuery.value = ''
}

// 创建选项
function createOption() {
  const value = searchQuery.value.trim()
  if (!value) return
  // 检查是否已存在
  const exists = allOptions.value.some((o) => o.value === value || o.label === value)
  if (exists) return

  const newOption = { label: value, value }
  createdOptions.value.push(newOption)
  selectOption(newOption)
  searchQuery.value = ''
}

// 搜索输入处理
function handleSearchInput() {
  highlightedIndex.value = -1
}

// 切换展开/收起
function toggleOpen() {
  if (props.disabled) return
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    updateDropdownPosition()
    highlightedIndex.value = -1
    nextTick(() => {
      if (props.filterable && searchInputRef.value) {
        searchInputRef.value.focus()
      }
    })
  } else {
    searchQuery.value = ''
  }
}

// 计算下拉菜单位置 (固定定位)
function updateDropdownPosition() {
  if (!selectRef.value) return
  const rect = selectRef.value.getBoundingClientRect()
  const spaceBelow = window.innerHeight - rect.bottom
  const dropdownHeight = Math.min(280, spaceBelow - 8)
  const top = spaceBelow > 100 ? rect.bottom + 4 : rect.top - dropdownHeight - 4
  dropdownStyle.value = {
    position: 'fixed',
    top: top + 'px',
    left: rect.left + 'px',
    width: rect.width + 'px',
    minWidth: rect.width + 'px',
  }
}

// 点击外部关闭
function handleClickOutside(e) {
  if (selectRef.value && !selectRef.value.contains(e.target) && isOpen.value) {
    const dropdown = document.querySelector('.custom-select__dropdown')
    if (dropdown && !dropdown.contains(e.target)) {
      isOpen.value = false
      searchQuery.value = ''
    }
  }
}

// 滚动时重新定位下拉菜单
function handleScroll() {
  if (isOpen.value) {
    updateDropdownPosition()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('scroll', handleScroll, true)
  window.addEventListener('resize', handleScroll)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('scroll', handleScroll, true)
  window.removeEventListener('resize', handleScroll)
})
</script>

<style scoped>
/* ========== 容器 ========== */
.custom-select {
  position: relative;
  width: 100%;
  font-family: var(--font-family, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif);
  user-select: none;
}

/* ========== 尺寸 ========== */
.custom-select--default .custom-select__trigger {
  min-height: 36px;
  padding: 4px 12px;
  font-size: var(--font-size-md, 14px);
}
.custom-select--small .custom-select__trigger {
  min-height: 28px;
  padding: 2px 10px;
  font-size: var(--font-size-sm, 12px);
}
.custom-select--large .custom-select__trigger {
  min-height: 42px;
  padding: 6px 14px;
  font-size: var(--font-size-lg, 16px);
}

.custom-select--small .custom-select__tag {
  font-size: 11px;
  padding: 1px 6px;
}
.custom-select--small .custom-select__value,
.custom-select--small .custom-select__placeholder {
  font-size: 12px;
}
.custom-select--default .custom-select__tag {
  font-size: 12px;
  padding: 2px 8px;
}

/* ========== 触发器 ========== */
.custom-select__trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(0, 136, 153, 0.12);
  border: 1px solid rgba(0, 136, 153, 0.25);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  box-sizing: border-box;
  width: 100%;
}
.custom-select__trigger:hover {
  border-color: rgba(0, 229, 204, 0.4);
}
.custom-select__trigger.is-focus {
  border-color: var(--border-focus, #00e5cc);
  box-shadow: 0 0 0 1px rgba(0, 229, 204, 0.15);
}
.custom-select.is-disabled .custom-select__trigger {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ========== 值/占位符 ========== */
.custom-select__value {
  flex: 1;
  color: var(--text-primary, #e6f7ff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.custom-select__placeholder {
  flex: 1;
  color: var(--text-muted, #66a0ad);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ========== 后缀图标 ========== */
.custom-select__suffix {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  color: var(--text-muted, #66a0ad);
}
.custom-select__clear {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  cursor: pointer;
  color: var(--text-muted, #66a0ad);
  transition: color 0.15s;
}
.custom-select__clear:hover {
  color: var(--text-primary, #e6f7ff);
}
.custom-select__arrow {
  display: flex;
  align-items: center;
  transition: transform 0.25s ease;
  color: var(--text-muted, #66a0ad);
}
.custom-select__arrow.is-reversed {
  transform: rotate(180deg);
}

/* ========== 多选标签 ========== */
.custom-select__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex: 1;
}
.custom-select__tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(0, 136, 153, 0.25);
  color: var(--text-primary, #e6f7ff);
  border-radius: 4px;
  line-height: 1.4;
}
.custom-select__tag-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  opacity: 0.7;
  transition: opacity 0.15s;
}
.custom-select__tag-close:hover {
  opacity: 1;
}

/* ========== 下拉菜单 ========== */
.custom-select__dropdown {
  z-index: 9999;
  background: rgba(10, 22, 40, 0.98);
  border: 1px solid rgba(0, 136, 153, 0.3);
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  max-height: 280px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ========== 搜索框 ========== */
.custom-select__search {
  position: relative;
  padding: 8px 10px 6px;
  flex-shrink: 0;
}
.custom-select__search-input {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 28px 6px 10px;
  background: rgba(0, 136, 153, 0.1);
  border: 1px solid rgba(0, 136, 153, 0.25);
  border-radius: 6px;
  color: var(--text-primary, #e6f7ff);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}
.custom-select__search-input:focus {
  border-color: rgba(0, 229, 204, 0.5);
}
.custom-select__search-input::placeholder {
  color: var(--text-muted, #66a0ad);
}
.custom-select__search-clear {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  cursor: pointer;
  color: var(--text-muted, #66a0ad);
}
.custom-select__search-clear:hover {
  color: var(--text-primary, #e6f7ff);
}

/* ========== 选项列表 ========== */
.custom-select__options {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
  overscroll-behavior: contain;
}
.custom-select__options::-webkit-scrollbar {
  width: 4px;
}
.custom-select__options::-webkit-scrollbar-thumb {
  background: rgba(0, 136, 153, 0.3);
  border-radius: 2px;
}

/* ========== 选项项 ========== */
.custom-select__option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  color: var(--text-body, #99c7d1);
  font-size: 13px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  min-height: 32px;
}
.custom-select__option:hover,
.custom-select__option.highlighted {
  background: rgba(0, 229, 204, 0.1);
  color: var(--text-primary, #e6f7ff);
}
.custom-select__option.selected {
  background: transparent;
  color: var(--text-primary, #e6f7ff);
  font-weight: 600;
  border: 1px solid rgba(0, 229, 204, 0.5);
  margin: -1px 0;
}
.custom-select__option.selected:hover {
  background: rgba(0, 229, 204, 0.1);
  border-color: rgba(0, 229, 204, 0.7);
}
.custom-select__option-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.custom-select__option-check {
  flex-shrink: 0;
  margin-left: 8px;
  color: var(--primary, #00e5cc);
}
.custom-select__option--create {
  border-top: 1px solid rgba(0, 136, 153, 0.2);
  margin-top: 4px;
  padding-top: 10px;
  color: var(--primary, #00e5cc);
  font-style: italic;
}

/* ========== 空状态 ========== */
.custom-select__empty {
  padding: 24px 12px;
  text-align: center;
  color: var(--text-muted, #66a0ad);
  font-size: 13px;
}

/* ========== 动画 ========== */
.dropdown-slide-enter-active {
  animation: dropdownIn 0.2s ease-out;
}
.dropdown-slide-leave-active {
  animation: dropdownOut 0.15s ease-in;
}
@keyframes dropdownIn {
  from {
    opacity: 0;
    transform: translateY(-6px) scaleY(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scaleY(1);
  }
}
@keyframes dropdownOut {
  from {
    opacity: 1;
    transform: translateY(0) scaleY(1);
  }
  to {
    opacity: 0;
    transform: translateY(-6px) scaleY(0.96);
  }
}
</style>