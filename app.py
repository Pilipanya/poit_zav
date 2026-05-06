from flask import Flask, render_template, request, jsonify
import serial
import threading
import configparser
import MySQLdb
import time

MAX_BATCH = 20
batch = []
last_insert_time = time.time()
data = {
    "temp": 0.0,
    "hum": 0.0,
    "motion": 0
}
lock = threading.Lock()
flush_lock = threading.Lock()

RECEIVE_ENABLED = True
DATA_SOURCE = "db"  # "db" / "file"

last_data_time = time.time()
DATA_TIMEOUT = 5  # seconds

FILE_PATH = "data.log"

config = configparser.ConfigParser()
config.read("config.cfg")

app = Flask(__name__)


def round1(value):
    return round(float(value), 1)


def get_db():
    return MySQLdb.connect(
        host=config.get("mysqlDB", "host"),
        user=config.get("mysqlDB", "user"),
        passwd=config.get("mysqlDB", "passwd"),
        db=config.get("mysqlDB", "db"),
        charset="utf8"
    )


def connect_serial():
    for i in range(6):  # 0 - 5
        port = f"/dev/ttyUSB{i}"
        try:
            ser = serial.Serial(port, 115200, timeout=1)
            print(f"Serial pripojený na {port}")
            return ser
        except Exception as e:
            pass
            # print(f"{port} does not working.")

    # print("Error: there is not enable USB port")
    print("Waiting for device...")
    return None


def read_serial():
    global last_data_time
    while True:
        if not RECEIVE_ENABLED:
            time.sleep(1)
            continue

        ser = connect_serial()
        if not ser:
            time.sleep(2)
            continue

        print("Serial connected")
        buffer = ""

        while True:
            try:
                chunk = ser.read(ser.in_waiting or 1).decode('utf-8', errors='ignore')
                buffer += chunk

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()

                    print("RAW:", line)

                    if line == "ERR":
                        continue

                    if line.startswith("T:"):
                        try:
                            parts = line.split(",")

                            t = float(parts[0].split(":")[1])
                            h = float(parts[1].split(":")[1])
                            m = int(parts[2].split(":")[1])

                            with lock:
                                data["temp"] = t
                                data["hum"] = h
                                data["motion"] = m
                                last_data_time = time.time()
                                batch.append({
                                    "time": time.time(),
                                    "temp": t,
                                    "hum": h,
                                    "motion": m
                                })

                        except Exception as e:
                            print("Parse error:", e)

            except Exception as e:
                print("Waiting for device...")
                ser.close()
                time.sleep(2)
                break  # reconnect

            # flush conditions
            should_flush = False
            with lock:
                should_flush = (
                    len(batch) >= MAX_BATCH or
                    (time.time() - last_insert_time > 30 and batch)
                )

            if should_flush:
                if flush_lock.acquire(blocking=False):
                    try:
                        save_batch()
                    finally:
                        flush_lock.release()
                


thread = threading.Thread(target=read_serial)
thread.daemon = True
thread.start()



def save_to_file(batch_copy):
    try:
        temps = [b["temp"] for b in batch_copy]
        hums = [b["hum"] for b in batch_copy]
        motions = [b["motion"] for b in batch_copy]

        from_time = batch_copy[0]["time"]
        to_time = batch_copy[-1]["time"]

        with open(FILE_PATH, "a") as f:
            f.write(
                f"{from_time},{to_time},"
                f"{round1(sum(temps)/len(temps))},"
                f"{round1(sum(hums)/len(hums))},"
                f"{round1(sum(motions)/len(motions))}\n"
            )

        print(f"Saved batch of {len(batch_copy)} rows to FILE (aggregated)")

    except Exception as e:
        print("FILE error:", e)


def save_to_db(batch_copy):
    global last_insert_time
    try:
        conn = get_db()
        cur = conn.cursor()

        temps = [b["temp"] for b in batch_copy]
        hums = [b["hum"] for b in batch_copy]
        motions = [b["motion"] for b in batch_copy]

        from_time = batch_copy[0]["time"]
        to_time = batch_copy[-1]["time"]

        query = """
        INSERT INTO sensor_data
        (from_time, to_time, temp_avg, hum_avg, motion_avg)
        VALUES (%s, %s, %s, %s, %s)
        """
        temp_avg = round1(sum(temps) / len(temps))
        hum_avg = round1(sum(hums) / len(hums))
        motion_avg = round1(sum(motions) / len(motions))
        cur.execute(query, (
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(from_time)),
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(to_time)),
            temp_avg,
            hum_avg,
            motion_avg
        ))

        conn.commit()

        print(f"Saved batch of {len(batch_copy)} rows to 1 row in the DB")

        with lock:
            last_insert_time = time.time()
    except Exception as e:
        print("DB error:", e)
    finally:
        try:
            cur.close()
        except: pass
        try:
            conn.close()
        except: pass


def save_batch():
    global batch, last_insert_time

    with lock:
        if not batch:
            return
        batch_copy = batch[:]
        batch.clear()

    try:
        save_to_db(batch_copy)
    except Exception as e:
        print("DB FAILED → fallback to FILE only:", e)
    save_to_file(batch_copy)

    with lock:
        last_insert_time = time.time()



def read_from_file(from_ts, to_ts):
    result = []
    try:
        with open(FILE_PATH, "r") as f:
            for line in f:
                parts = line.strip().split(",")

                if len(parts) != 5:
                    continue

                from_t, to_t, temp, hum, motion = parts

                from_t = float(from_t)
                to_t = float(to_t)

                # Include any record that overlaps requested window.
                if from_t <= to_ts and to_t >= from_ts:
                    result.append({
                        "from": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(from_t)),
                        "to": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(to_t)),
                        "temp": round1(temp),
                        "hum": round1(hum),
                        "motion": round1(motion)
                    })
    except Exception as e:
        print("FILE READ error:", e)

    return result




@app.route("/")
def index():
    with lock:
        current_data = data.copy()

    if time.time() - last_data_time > DATA_TIMEOUT:
        current_data = {"temp": "-", "hum": "-", "motion": "-"}

    return render_template("index.html", data=current_data, request=request)


@app.route("/api/current")
def api_current():
    with lock:
        current_data = data.copy()

    if time.time() - last_data_time > DATA_TIMEOUT:
        current_data = {"temp": None, "hum": None, "motion": None}

    return jsonify(current_data)


@app.route("/trigger", methods=["POST"])
def trigger():
    try:
        ser = connect_serial()
        if ser:
            ser.write(b"TRIGGER\n")
            ser.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})


@app.route("/history")
def history():
    return render_template("history.html", request=request)


@app.route("/api/history")
def api_history():
    try:
        from_str = request.args.get("from")
        to_str = request.args.get("to")
        source = request.args.get("source", "db")

        if not from_str or not to_str:
            return jsonify([])

        from_ts = time.mktime(time.strptime(from_str, '%Y-%m-%dT%H:%M'))
        to_ts = time.mktime(time.strptime(to_str, '%Y-%m-%dT%H:%M'))

        if from_ts > to_ts:
            from_ts, to_ts = to_ts, from_ts
            from_str, to_str = to_str, from_str

    except Exception as e:
        print("TIME PARSE ERROR:", e)
        return jsonify([])
    

    if source == "file":
        return jsonify(read_from_file(from_ts, to_ts))

    rows = []
    try:
        conn = get_db()
        cur = conn.cursor()

        query = """
        SELECT * FROM sensor_data
        WHERE from_time BETWEEN %s AND %s
        ORDER BY from_time ASC
        """
        cur.execute(query, (from_str, to_str))

        rows = cur.fetchall()
    except Exception as e:
        print("Error:", e)
    finally:
        try:
            cur.close()
        except: pass
        try:
            conn.close()
        except: pass

    result = []
    for r in rows:
        result.append({
            "from": str(r[1]),
            "to": str(r[2]),
            "temp": round1(r[3]),
            "hum": round1(r[4]),
            "motion": round1(r[5])
        })

    return jsonify(result)


@app.route("/toggle_receive", methods=["POST"])
def toggle_receive():
    global RECEIVE_ENABLED
    RECEIVE_ENABLED = not RECEIVE_ENABLED
    return jsonify({"enabled": RECEIVE_ENABLED})


@app.route("/status")
def status():
    return jsonify({
        "receive": RECEIVE_ENABLED
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)