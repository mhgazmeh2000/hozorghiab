from zk import ZK

DEVICES = [
    "172.16.0.20",
    "172.16.32.21",
]

for ip in DEVICES:
    print("\n" + "=" * 80)
    print(f"DEVICE: {ip}")
    print("=" * 80)

    conn = None

    try:
        zk = ZK(
            ip,
            port=4370,
            timeout=10,
            password=0,
            force_udp=False,
            ommit_ping=False
        )

        conn = zk.connect()

        print("\n[DEVICE INFO]")

        read_tests = [
            ("Firmware", conn.get_firmware_version),
            ("Serial", conn.get_serialnumber),
            ("Platform", conn.get_platform),
            ("Device Name", conn.get_device_name),
            ("MAC", conn.get_mac),
            ("Device Time", conn.get_time),
            ("Network Params", conn.get_network_params),
            ("FP Version", conn.get_fp_version),
            ("Face Version", conn.get_face_version),
            ("PIN Width", conn.get_pin_width),
        ]

        for name, func in read_tests:
            try:
                value = func()
                print(f"{name:<20}: {value}")
            except Exception as e:
                print(f"{name:<20}: ERROR -> {e}")

        print("\n[USERS]")

        try:
            users = conn.get_users()

            print("User count:", len(users))

            for user in users[:20]:
                print({
                    "uid": getattr(user, "uid", None),
                    "user_id": getattr(user, "user_id", None),
                    "name": getattr(user, "name", None),
                    "privilege": getattr(user, "privilege", None),
                    "password": bool(getattr(user, "password", "")),
                    "card": getattr(user, "card", None),
                    "group_id": getattr(user, "group_id", None),
                })

        except Exception as e:
            print("Users ERROR:", e)

        print("\n[ATTENDANCE]")

        try:
            logs = conn.get_attendance()

            print("Attendance count:", len(logs))

            if logs:
                print("\nFirst 10:")
                for log in logs[:10]:
                    print(log)

                print("\nLast 10:")
                for log in logs[-10:]:
                    print(log)

        except Exception as e:
            print("Attendance ERROR:", e)

        print("\n[CAPABILITIES / INTERNAL STATE]")

        attrs = [
            "users_av",
            "users_cap",
            "fingers_av",
            "fingers_cap",
            "faces_cap",
            "cards",
            "records",
            "rec_av",
            "rec_cap",
            "fingers",
            "faces",
            "is_enabled",
            "is_connect",
        ]

        for attr in attrs:
            try:
                print(f"{attr:<20}: {getattr(conn, attr)}")
            except Exception as e:
                print(f"{attr:<20}: ERROR -> {e}")

    except Exception as e:
        print("\nCONNECTION ERROR:", repr(e))

    finally:
        if conn:
            try:
                conn.disconnect()
            except:
                pass

        print("\nDisconnected")