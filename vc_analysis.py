import sqlite3
# from tabulate import tabulate  # format output

DB_PATH = "data/vc_data.db"

def get_vc_stats(user_id, guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT COUNT(*), AVG(duration), MAX(duration), MIN(duration) 
                 FROM vc_log WHERE user_id = ? AND guild_id = ?''', 
              (user_id, guild_id))
    result = c.fetchone()
    conn.close()

    if result and result[0] > 0:
        count, avg_duration, max_duration, min_duration = result
        return {
            "sessions": count,
            "average_time": round(avg_duration, 2),
            "max_time": round(max_duration, 2),
            "min_time": round(min_duration, 2)
        }
    else:
        return None  # no any vc log

def get_top_active_users(guild_id, limit=5):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT user_id, SUM(duration) as total_time
                 FROM vc_log WHERE guild_id = ?
                 GROUP BY user_id ORDER BY total_time DESC LIMIT ?''', 
              (guild_id, limit))
    result = c.fetchall()
    conn.close()
    
    return result if result else None

def get_most_active_channels(guild_id, limit=3):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT channel_id, SUM(duration) as total_time
                 FROM vc_log WHERE guild_id = ?
                 GROUP BY channel_id ORDER BY total_time DESC LIMIT ?''', 
              (guild_id, limit))
    result = c.fetchall()
    conn.close()
    
    return result if result else None
