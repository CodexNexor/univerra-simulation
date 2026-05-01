def normalize_openai_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return base_url

    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    return normalized
