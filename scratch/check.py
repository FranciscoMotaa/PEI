import json
import sqlite3
import os

def get_feed():
    # adjust path depending on where it runs
    db_path = "ai-server/db/iot_traffic.db"
    if not os.path.exists(db_path):
        db_path = "/app/data/iot_traffic.db"
        if not os.path.exists(db_path):
            # Try finding it
            db_path = "data/iot_traffic.db"

    print("Using DB:", db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        raw_rows = conn.execute("SELECT timestamp, src_ip, dst_ip, size, payload_hex, src_port, dst_port, ttl FROM raw_packets ORDER BY id DESC LIMIT 40").fetchall()
    except sqlite3.OperationalError as e:
        print("Fallback:", e)
        raw_rows = conn.execute("SELECT timestamp, src_ip, dst_ip, size FROM raw_packets ORDER BY id DESC LIMIT 40").fetchall()
        
    cls_rows = conn.execute("SELECT timestamp, device_id, predicted, confidence, avg_size, avg_iat, num_packets FROM classifications ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    
    feed = []
    for r in raw_rows:
        rd = dict(r)
        feed.append({
            "type": "packet",
            "timestamp": rd["timestamp"],
            "src_ip": rd["src_ip"],
            "dst_ip": rd["dst_ip"],
            "size": rd["size"],
            "payload_hex": rd.get("payload_hex", "17 03 03 ..."),
            "src_port": rd.get("src_port", "---"),
            "dst_port": rd.get("dst_port", "---"),
            "ttl": rd.get("ttl", "---")
        })
        
    for c in cls_rows:
        feed.append({
            "type": "classification",
            "timestamp": c["timestamp"],
            "device_id": c["device_id"],
            "predicted": c["predicted"],
            "confidence": c["confidence"],
            "avg_size": c["avg_size"],
            "avg_iat": c["avg_iat"],
            "num_packets": c["num_packets"]
        })
        
    feed.sort(key=lambda x: x["timestamp"])
    return feed

if __name__ == "__main__":
    feed = get_feed()
    print("Total items:", len(feed))
    if feed:
        print("First item:", json.dumps(feed[0], indent=2))
        print("Last item:", json.dumps(feed[-1], indent=2))
    else:
        print("FEED IS EMPTY")
