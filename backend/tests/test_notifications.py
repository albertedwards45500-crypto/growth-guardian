"""
@file: tests/test_notifications.py
@description: 通知模块集成测试：列表、未读数与标记已读。
"""


def _create_notification(client, headers, user_id: int, title: str = "测试通知") -> None:
    """直接向数据库写入一条通知（用于测试前置数据）。

    @param client: 测试客户端
    @param headers: 鉴权头（未使用，仅为保持签名一致）
    @param user_id: 目标用户 ID
    @param title: 通知标题
    """
    from app.core.database import SessionLocal
    from app.models.notification import Notification

    with SessionLocal() as db:
        db.add(Notification(user_id=user_id, notify_type="system", title=title, content="通知内容"))
        db.commit()


class TestNotification:
    """通知接口测试组。"""

    def test_empty_notifications(self, client, auth_headers):
        """新用户通知列表应为空，未读数为 0（D09 分页契约：响应含 items）。"""
        resp = client.get("/api/v1/notifications", headers=auth_headers)
        assert resp.json()["data"]["items"] == []
        assert resp.json()["data"]["total"] == 0

        count = client.get("/api/v1/notifications/unread-count", headers=auth_headers)
        assert count.json()["data"]["unread_count"] == 0

    def test_mark_read_flow(self, client, auth_headers):
        """标记已读流程：先创建通知再标记。"""
        # 获取当前用户 id
        me = client.get("/api/v1/users/me", headers=auth_headers).json()["data"]
        _create_notification(client, auth_headers, me["id"], "接种提醒")

        resp = client.get("/api/v1/notifications", headers=auth_headers)
        data = resp.json()["data"]
        assert data["total"] == 1
        notifications = data["items"]
        assert len(notifications) == 1
        assert notifications[0]["is_read"] is False

        count = client.get("/api/v1/notifications/unread-count", headers=auth_headers).json()
        assert count["data"]["unread_count"] == 1

        # 标记已读
        nid = notifications[0]["id"]
        resp = client.patch(f"/api/v1/notifications/{nid}/read", headers=auth_headers)
        assert resp.json()["data"]["is_read"] is True

        count = client.get("/api/v1/notifications/unread-count", headers=auth_headers).json()
        assert count["data"]["unread_count"] == 0

    def test_mark_all_read(self, client, auth_headers):
        """全部标记已读。"""
        me = client.get("/api/v1/users/me", headers=auth_headers).json()["data"]
        _create_notification(client, auth_headers, me["id"], "提醒一")
        _create_notification(client, auth_headers, me["id"], "提醒二")

        resp = client.patch("/api/v1/notifications/read-all", headers=auth_headers)
        assert resp.json()["data"]["updated"] == 2

        count = client.get("/api/v1/notifications/unread-count", headers=auth_headers).json()
        assert count["data"]["unread_count"] == 0
