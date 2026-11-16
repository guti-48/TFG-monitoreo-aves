"""Publish to the local RTSP origin, exiting when audio progress stops."""
import os
import selectors
import subprocess
import time


def run():
    url = os.environ["BIRDMONITOR_STREAM_PUBLISH_URL"]
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-progress", "pipe:1", "-nostats", "-f", "alsa", "-sample_rate", "48000",
        "-channels", "1", "-i", os.getenv("BIRDMONITOR_CAPTURE_PCM", "plug:micshared"),
        "-vn", "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "1",
        "-f", "rtsp", "-rtsp_transport", "tcp", url]
    # FFmpeg errors may contain the credential-bearing URL. Never forward them.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    last_change = time.monotonic()
    last_value = -1
    pending = b""
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while process.poll() is None:
            for key, _ in selector.select(timeout=1):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    continue
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if line.startswith(b"out_time_us="):
                        try:
                            value = int(line.split(b"=", 1)[1])
                        except ValueError:
                            continue
                        if value > last_value:
                            last_value = value
                            last_change = time.monotonic()
            if time.monotonic() - last_change > 20:
                print("Audio sin progreso durante 20 segundos; se reiniciara la captura", flush=True)
                return 1
        print("Publicador terminado; se reintentara sin revelar credenciales", flush=True)
        return 1
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        process.stdout.close()


if __name__ == "__main__":
    raise SystemExit(run())
