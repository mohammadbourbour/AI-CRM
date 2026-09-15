def mask_email(email: str | None) -> str:
    """Return a masked email for logs. Never log the raw address."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"
