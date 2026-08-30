"""Command-line interface for XK One Pro smart glasses."""

import argparse
import sys
import time
from .client import XkGlassesClient


def main():
    parser = argparse.ArgumentParser(description="XK One Pro Smart Glasses CLI")
    parser.add_argument("--mac", required=True, help="Bluetooth MAC address (e.g. FA:00:11:12:F7:73)")
    parser.add_argument("--channel", type=int, default=8, help="RFCOMM SPP channel (default: 8)")
    parser.add_argument(
        "action",
        choices=("capture", "download", "count", "battery", "watch", "ping"),
        help="Action to perform",
    )
    parser.add_argument("--out", default="photo.jpg", help="Output file path for photos")
    parser.add_argument("--index", type=int, default=1, help="Photo element index for download")
    args = parser.parse_args()

    client = XkGlassesClient(channel=args.channel)
    print(f"Connecting to {args.mac} on channel {args.channel}...")
    try:
        client.connect(args.mac)
        print("Binding session...")
        client.bind()
        print("Arming services (setup sequence)...")
        client.setup()

        if args.action == "ping":
            client.send_keepalive()
            print("Connected & setup complete.")

        elif args.action == "battery":
            level = client.get_battery()
            print(f"Battery: {level}%" if level is not None else "Battery query timed out.")

        elif args.action == "count":
            cnt = client.photo_count()
            print(f"Photo elements available: {cnt}")

        elif args.action == "capture":
            print("Triggering photo capture...")
            res = client.capture_photo(out_path=args.out)
            if res:
                print(f"Success: saved {len(res)} bytes to {args.out}")
            else:
                print("Failed to capture photo.", file=sys.stderr)
                sys.exit(1)

        elif args.action == "download":
            cnt = client.photo_count() or 6
            print(f"Downloading {cnt} elements...")
            res = client.download_photo(count=cnt, out_path=args.out)
            if res:
                print(f"Success: saved {len(res)} bytes to {args.out}")
            else:
                print("Failed to download photo.", file=sys.stderr)
                sys.exit(1)

        elif args.action == "watch":
            print("Watching events (press Ctrl+C to stop)...")
            client.on_battery = lambda lvl, chg: print(f"[EVENT] Battery: {lvl}% (charging={chg})")
            client.on_voice_button = lambda: print("[EVENT] Voice/touch button pressed!")
            client.on_photo_push = lambda cnt: print(f"[EVENT] Photo push: {cnt} elements")
            while True:
                client.send_keepalive()
                time.sleep(3)

    except KeyboardInterrupt:
        print("\nExiting.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
