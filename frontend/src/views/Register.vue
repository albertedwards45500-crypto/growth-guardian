<script setup lang="ts">
/**
 * @file: src/views/Register.vue
 * @description: 注册页：手机号/昵称/密码校验，注册成功后跳转登录页。
 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// 路由实例
const router = useRouter()
// 认证 store
const auth = useAuthStore()

// 表单数据
const form = reactive({ phone: '', nickname: '', password: '', confirm: '' })
// 提交中标记
const submitting = ref(false)
// 表单校验错误信息
const formError = ref('')

/**
 * 校验注册表单。
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
  if (form.password !== form.confirm) {
    formError.value = '两次输入的密码不一致'
    return false
  }
  formError.value = ''
  return true
}

/**
 * 提交注册：成功后跳转登录页。
 *
 * @throws Error 手机号已注册（40900）时展示错误提示
 */
async function onSubmit(): Promise<void> {
  if (!validate() || submitting.value) return
  submitting.value = true
  try {
    await auth.register(form.phone, form.password, form.nickname || undefined)
    router.push({ name: 'login' })
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '注册失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card card">
      <h1 class="brand">创建账号</h1>
      <p class="slogan">加入成长宝，开始记录宝宝的每一天</p>

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
          <label class="label" for="nickname">昵称（选填）</label>
          <input
            id="nickname"
            v-model="form.nickname"
            class="input"
            type="text"
            maxlength="50"
            placeholder="怎么称呼你？"
          />
        </div>
        <div class="field">
          <label class="label" for="password">密码</label>
          <input
            id="password"
            v-model="form.password"
            class="input"
            type="password"
            placeholder="至少 6 位"
            autocomplete="new-password"
          />
        </div>
        <div class="field">
          <label class="label" for="confirm">确认密码</label>
          <input
            id="confirm"
            v-model="form.confirm"
            class="input"
            type="password"
            placeholder="再次输入密码"
            autocomplete="new-password"
          />
        </div>

        <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>

        <button class="btn btn-primary submit" type="submit" :disabled="submitting">
          {{ submitting ? '注册中…' : '注 册' }}
        </button>
      </form>

      <p class="switch-tip">
        已有账号？
        <RouterLink class="link" to="/login">返回登录</RouterLink>
      </p>
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
  font-size: 22px;
  line-height: 30px;
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
</style>
