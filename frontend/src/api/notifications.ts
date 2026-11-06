/**
 * @file: src/api/notifications.ts
 * @description: 通知接口：分页列表、未读数与已读标记。
 */

import { get, patch } from './client'
import type { Notification, PageResult } from '@/types/api'

/**
 * 分页查询当前用户通知（按创建时间倒序）。
 *
 * @param params: unread_only 仅未读、page、page_size
 * @returns 分页通知结果
 * @throws Error 未认证时抛出
 */
export function listNotifications(
  params: { unread_only?: boolean; page?: number; page_size?: number } = {}
): Promise<PageResult<Notification>> {
  return get<PageResult<Notification>>('/notifications', params)
}

/**
 * 获取未读通知数。
 *
 * @returns 未读数
 * @throws Error 未认证时抛出
 */
export function getUnreadCount(): Promise<{ unread_count: number }> {
  return get<{ unread_count: number }>('/notifications/unread-count')
}

/**
 * 将单条通知标记为已读。
 *
 * @param notificationId: 通知 ID
 * @returns 更新后的通知
 * @throws Error 通知不存在（40400）时抛出
 */
export function markRead(notificationId: number): Promise<Notification> {
  return patch<Notification>(`/notifications/${notificationId}/read`)
}

/**
 * 全部通知标记为已读。
 *
 * @returns 更新数量
 */
export function markAllRead(): Promise<{ updated: number }> {
  return patch<{ updated: number }>('/notifications/read-all')
}
