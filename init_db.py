import MySQLdb
import configparser

config = configparser.ConfigParser()
config.read("config.cfg")


def get_db():
    return MySQLdb.connect(
        host=config.get("mysqlDB", "host"),
        user=config.get("mysqlDB", "user"),
        passwd=config.get("mysqlDB", "passwd"),
        db=config.get("mysqlDB", "db"),
        charset="utf8"
    )


def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()

        query = """
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            from_time DATETIME,
            to_time DATETIME,
            temp_avg DECIMAL(10,3),
            hum_avg DECIMAL(10,3),
            motion_avg DECIMAL(10,3)
        )
        """

        cur.execute(query)
        cur.execute("ALTER TABLE sensor_data MODIFY temp_avg DECIMAL(10,3)")
        cur.execute("ALTER TABLE sensor_data MODIFY hum_avg DECIMAL(10,3)")
        cur.execute("ALTER TABLE sensor_data MODIFY motion_avg DECIMAL(10,3)")
        conn.commit()

        print("Table 'sensor_data' is ready.")

    except Exception as e:
        print("Error:", e)

    finally:
        try:
            cur.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


if __name__ == "__main__":
    init_db()