/**
 * @file: tests/states.spec.ts
 * @description: 通用状态组件测试：LoadingState / EmptyState / ErrorState 渲染与交互。
 */

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'

describe('LoadingState', () => {
  it('渲染默认加载文案', () => {
    const wrapper = mount(LoadingState)
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('加载中…')
  })

  it('渲染自定义加载文案', () => {
    const wrapper = mount(LoadingState, { props: { text: '正在加载宝宝档案…' } })
    expect(wrapper.text()).toContain('正在加载宝宝档案…')
  })
})

describe('EmptyState', () => {
  it('渲染默认空态文案', () => {
    const wrapper = mount(EmptyState)
    expect(wrapper.text()).toContain('这里还没有内容')
  })

  it('渲染自定义文案与插槽操作按钮', async () => {
    const wrapper = mount(EmptyState, {
      props: { text: '还没有宝宝档案' },
      slots: { default: '<button class="cta">创建宝宝档案</button>' }
    })
    expect(wrapper.text()).toContain('还没有宝宝档案')
    expect(wrapper.find('button.cta').exists()).toBe(true)
  })
})

describe('ErrorState', () => {
  it('渲染错误信息', () => {
    const wrapper = mount(ErrorState, { props: { message: '网络请求失败' } })
    expect(wrapper.text()).toContain('网络请求失败')
  })

  it('点击重试触发 retry 事件', async () => {
    const wrapper = mount(ErrorState)
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})
