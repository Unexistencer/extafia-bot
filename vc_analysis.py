from google.cloud import firestore

db = firestore.Client()


def _fetch_vc_logs(guild_id, *, user_id=None):
    query = db.collection("vc_logs").where("guild_id", "==", guild_id)
    if user_id is not None:
        query = query.where("user_id", "==", user_id)

    return [doc.to_dict() or {} for doc in query.stream()]

def get_vc_stats(user_id, guild_id):
    rows = _fetch_vc_logs(guild_id, user_id=user_id)
    durations = [
        float(row.get("duration", 0))
        for row in rows
        if row.get("duration") is not None
    ]

    if durations:
        count = len(durations)
        avg_duration = sum(durations) / count
        max_duration = max(durations)
        min_duration = min(durations)
        return {
            "sessions": count,
            "average_time": round(avg_duration, 2),
            "max_time": round(max_duration, 2),
            "min_time": round(min_duration, 2)
        }
    else:
        return None  # no any vc log

def get_top_active_users(guild_id, limit=5):
    rows = _fetch_vc_logs(guild_id)
    totals = {}
    for row in rows:
        user_id = row.get("user_id")
        duration = row.get("duration")
        if user_id is None or duration is None:
            continue
        totals[user_id] = totals.get(user_id, 0.0) + float(duration)

    result = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    return result if result else None

def get_most_active_channels(guild_id, limit=3):
    rows = _fetch_vc_logs(guild_id)
    totals = {}
    for row in rows:
        channel_id = row.get("channel_id")
        duration = row.get("duration")
        if channel_id is None or duration is None:
            continue
        totals[channel_id] = totals.get(channel_id, 0.0) + float(duration)

    result = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    return result if result else None
