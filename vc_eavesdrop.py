from google.cloud import firestore
import time
import os

db = firestore.Client()
join_vc_dict = {}  # {user_id: JoinVC}

class JoinVC:
    def __init__(self, user_id, guild_id, channel_id, join_time):
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.join_time = join_time

def vc_check(user_id, guild_id, bef_channel, aft_channel):
    now = time.time()
    eavesdrop_limit = 10

    if user_id in join_vc_dict:
        record = join_vc_dict[user_id]
        elapsed_time = now - record.join_time

        if bef_channel and aft_channel:  # 切換語音頻道
            join_vc_dict[user_id] = JoinVC(user_id, guild_id, aft_channel, now)
            return True
        elif not aft_channel:  # 離開語音頻道
            if elapsed_time < eavesdrop_limit:
                join_vc_dict.pop(user_id, None)
                return True  # 偷聽判定

            save_vc_log(user_id, guild_id, record.channel_id, record.join_time, now)
            join_vc_dict.pop(user_id, None)

    else:
        join_vc_dict[user_id] = JoinVC(user_id, guild_id, aft_channel, now)

    return False

def save_vc_log(user_id, guild_id, channel_id, join_time, leave_time):
    duration = leave_time - join_time
    db.collection("vc_logs").add({
        "user_id": user_id,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "join_time": join_time,
        "leave_time": leave_time,
        "duration": duration
    })
