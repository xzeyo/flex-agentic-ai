PROFILES = {
    "lint": ["python", "-I", "/runner/execute.py", "lint"],
    "test": ["python", "-I", "/runner/execute.py", "test"],
}


def command(profile: str) -> list[str]:
    if profile not in PROFILES:
        raise ValueError("Unknown command profile")
    return list(PROFILES[profile])
