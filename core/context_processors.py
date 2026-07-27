def notification_context(request):
    if not request.user.is_authenticated:
        return {}

    unread_notifications = (
        request.user
        .in_app_notifications
        .filter(
            is_read=False
        )
    )

    return {
        "unread_notification_count": (
            unread_notifications.count()
        ),

        "latest_unread_notifications": (
            unread_notifications[:5]
        ),
    }