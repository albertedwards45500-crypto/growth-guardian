<script setup lang="ts">
/**
 * @file: src/views/Login.vue
 * @description: 登录页：手机号+密码表单校验（11 位手机号、密码 ≥6 位）、提交登录与跳转注册。
 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// 路由实例
const router = useRouter()
// 当前路由（用于登录后回跳）
const route = useRoute()
// 认证 store
const auth = useAuthStore()

// 表单数据
const form = reactive({ phone: '', password: '' })
// 提交中标记
const submitting = ref(false)
// 表单校验错误信息
const formError = ref('')

/**
 * 校验登录表单。
 *
 * @returns 校验通过返回 true
 */
function validate(): boolean {
  if (!/^1[3-9]\d{9}$/.test(form.phone)) {
    formError.value = '请输入 11 位大陆手机号'
    return false
  }
  if (form.password.length < 6) {
    formError.value = '密码至少 6 位'
    return false
  }
  formError.value = ''
  return true
}

/**
 * 提交登录：校验通过后调用认证接口并跳转。
 *
 * @throws Error 登录失败时展示错误提示
 */
async function onSubmit(): Promise<void> {
  if (!validate() || submitting.value) return
  submitting.value = true
  try {
    await auth.login(form.phone, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/overview'
    router.push(redirect)
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '登录失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card card">
      <h1 class="brand">成长宝</h1>
      <p class="slogan">记录宝宝成长 · 轻松安排每一餐</p>

      <form class="form" novalidate @submit.prevent="onSubmit">
        <div class="field">
          <label class="label" for="phone">手机号</label>
          <input
            id="phone"
            v-model="form.phone"
            class="input"
            type="tel"
            maxlength="11"
            placeholder="请输入 11 位手机号"
            autocomplete="tel"
          />
        </div>
        <div class="field">
          <label class="label" for="password">密码</label>
          <input
            id="password"
            v-model="form.password"
            class="input"
            type="password"
            placeholder="请输入密码（至少 6 位）"
            autocomplete="current-password"
          />
        </div>

        <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>

        <button class="btn btn-primary submit" type="submit" :disabled="submitting">
          {{ submitting ? '登录中…' : '登 录' }}
        </button>
      </form>

      <p class="switch-tip">
        还没有账号？
        <RouterLink class="link" to="/register">立即注册</RouterLink>
      </p>
      <p class="demo-tip">演示账号：13800000000 / 123456</p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-lg);
}

.auth-card {
  width: 100%;
  max-width: 400px;
  padding: var(--space-xxl);
}

.brand {
  font-size: 28px;
  line-height: 36px;
  font-weight: 700;
  text-align: center;
  color: var(--color-primary);
}

.slogan {
  margin: var(--space-xs) 0 var(--space-xl);
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.field {
  display: flex;
  flex-direction: column;
}

.form-error {
  margin: 0;
  color: var(--color-danger);
  font-size: 13px;
}

.submit {
  width: 100%;
}

.switch-tip {
  margin: var(--space-lg) 0 0;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.link {
  color: var(--color-primary);
  text-decoration: none;
  font-weight: 600;
}

.demo-tip {
  margin: var(--space-sm) 0 0;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 12px;
}
</style>
