"""Prepare an independent RTSP origin and render desktop receiver configuration.

Preparation only: this tool never restarts services or opens firewall ports.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import quote


NETWORKS = tuple(map(ipaddress.ip_network, ("100.64.0.0/10", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))


def private_host(value):
    address = ipaddress.ip_address(value)
    if not any(address in network for network in NETWORKS):
        raise ValueError("Se requiere una IPv4 privada o Tailscale")
    return str(address)


def read_env(path):
    result = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip("\"'")
    return result


def write_private(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf8", newline="\n") as output:
        output.write(text)
    os.replace(temporary, path)
    if os.name != "nt":
        path.chmod(0o600)


def validate_profile(profile):
    private_host(profile["host"])
    for key in ("path", "node", "user"):
        if not isinstance(profile.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_-]+", profile[key]):
            raise ValueError("Perfil de origen invalido")
    password = profile.get("password", "")
    if not isinstance(password, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", password):
        raise ValueError("Credencial del origen invalida")
    return profile


def receiver_config(template, values, env_path):
    host = private_host(values["BIRDMONITOR_SERVER_HOST"])
    output, count = re.subn(r"(?m)^rtspAddress: *:8554 *$", "rtspAddress: " + host + ":8554", template)
    if count != 1:
        raise ValueError("Plantilla RTSP inesperada")
    if values.get("BIRDMONITOR_STREAM_MODE", "push") != "pull":
        return output
    profile_path = Path(values["BIRDMONITOR_STREAM_SOURCE_FILE"])
    if not profile_path.is_absolute():
        profile_path = Path(env_path).parent / profile_path
    profile = validate_profile(json.loads(profile_path.read_text(encoding="utf8")))
    if values.get("BIRDMONITOR_STREAM_SOURCE_NODE") != profile["node"]:
        raise ValueError("El nodo del perfil no coincide con el configurado")
    if values.get("BIRDMONITOR_STREAM_PATH") != profile["path"]:
        raise ValueError("La ruta del perfil no coincide con la configurada")
    url = "rtsp://{}:{}@{}:8554/{}".format(quote(profile["user"], safe=""),
        quote(profile["password"], safe=""), profile["host"], profile["path"])
    output = output.replace("hlsAlwaysRemux: true", "hlsAlwaysRemux: false")
    if output.count("\npaths:") != 1:
        raise ValueError("Plantilla de rutas inesperada")
    # Explicit path only: never interpolate a user-selected stream path into a URL.
    output = output.split("\npaths:", 1)[0] + "\npaths:\n  " + json.dumps(profile["path"]) + ":\n"
    output += "    source: " + json.dumps(url) + "\n    rtspTransport: tcp\n    sourceOnDemand: true\n    sourceOnDemandStartTimeout: 15s\n    sourceOnDemandCloseAfter: 10s\n"
    return output


def prepare(directory, host, readers):
    host = private_host(host)
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("El directorio de preparacion debe estar vacio; no se rotan claves automaticamente")
    parsed = []
    for item in readers:
        name, address = item.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in [x[0] for x in parsed]:
            raise ValueError("Nombre de lector invalido o repetido")
        parsed.append((name, private_host(address)))
    publisher = secrets.token_urlsafe(32)
    users = [dict(user="publisher", **{"pass": publisher}, ips=[host],
                  permissions=[dict(action="publish", path="birdmonitor-audio")])]
    for name, address in parsed:
        password = secrets.token_urlsafe(32)
        users.append(dict(user=name, **{"pass": password}, ips=[address],
                          permissions=[dict(action="read", path="birdmonitor-audio")]))
        write_private(directory / (name + ".json"), json.dumps(dict(host=host, node="birdmonitor",
            path="birdmonitor-audio", user=name, password=password), indent=2))
    config = dict(logLevel="warn", authMethod="internal", authInternalUsers=users,
        rtsp=True, rtspAddress=host + ":8554", rtspTransports=["tcp"],
        rtmp=False, hls=False, webrtc=False, srt=False, moq=False, playback=False, api=False, metrics=False, pprof=False,
        paths={"birdmonitor-audio": dict(source="publisher", overridePublisher=False)})
    write_private(directory / "mediamtx-source.yml", json.dumps(config, indent=2))
    write_private(directory / "source.env", "BIRDMONITOR_STREAM_PUBLISH_URL=rtsp://publisher:" + publisher + "@" + host + ":8554/birdmonitor-audio\nBIRDMONITOR_CAPTURE_PCM=plug:micshared\n")


def configure_receiver(env_path, profile_path):
    env_path = Path(env_path)
    profile_path = Path(profile_path).resolve()
    profile = validate_profile(json.loads(profile_path.read_text(encoding="utf8")))
    if not env_path.is_file():
        raise ValueError("Configura antes la seguridad y red del backend")
    updates = dict(BIRDMONITOR_STREAM_MODE="pull", BIRDMONITOR_STREAM_SOURCE_FILE=str(profile_path),
        BIRDMONITOR_STREAM_SOURCE_NODE=profile["node"], BIRDMONITOR_STREAM_PATH=profile["path"])
    lines = env_path.read_text(encoding="utf8").splitlines()
    # Preserve a rollback copy without overwriting an earlier backup.
    backup = env_path.with_name(env_path.name + ".before-independent")
    if not backup.exists():
        write_private(backup, "\n".join(lines) + "\n")
    lines = [line for line in lines if line.split("=", 1)[0].strip() not in updates]
    lines.extend(key + "=" + value for key, value in updates.items())
    write_private(env_path, "\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    source = sub.add_parser("prepare")
    source.add_argument("--out", required=True)
    source.add_argument("--host", required=True)
    source.add_argument("--reader", action="append", required=True)
    receiver = sub.add_parser("configure-receiver")
    receiver.add_argument("--env", required=True)
    receiver.add_argument("--profile", required=True)
    render = sub.add_parser("render")
    render.add_argument("--env", required=True)
    render.add_argument("--template", required=True)
    render.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            prepare(args.out, args.host, args.reader)
        elif args.action == "configure-receiver":
            configure_receiver(args.env, args.profile)
        else:
            write_private(args.out, receiver_config(Path(args.template).read_text(encoding="utf8"), read_env(args.env), args.env))
    except (ValueError, KeyError, OSError):
        parser.exit(2, "Configuracion no valida o inaccesible; revisa rutas, IP y perfil.\n")
    print("Configuracion preparada; no se han reiniciado servicios ni mostrado credenciales.")


if __name__ == "__main__":
    main()
