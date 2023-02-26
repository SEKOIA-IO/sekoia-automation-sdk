def match_events(*events):
    """
    Match a request according events
    """

    def wrapper(request):
        return set(events) & set(request.json().get("jsons", []))

    return wrapper
