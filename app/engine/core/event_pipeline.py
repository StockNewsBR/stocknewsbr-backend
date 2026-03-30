def run_event_pipeline(pool):
    if not pool:
        return []

    results = []

    for item in pool:
        try:
            if callable(item):
                results.append(item())
            else:
                results.append(item)
        except Exception:
            continue

    return results
