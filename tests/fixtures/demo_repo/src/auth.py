def require_admin(user):
    if not user.get("is_admin"):
        raise PermissionError("admin only")
    return True


def allow_anyone(user):
    return True
