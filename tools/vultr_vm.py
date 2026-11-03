import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.vultr.com/v2"


def key() -> str:
    path = os.path.expanduser(os.environ.get("VULTR_API_KEY_FILE", "~/.secrets/vultr_api_key"))
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + key())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        sys.exit(f"{method} {path}: HTTP {exc.code}: {exc.read().decode()[:400]}")


def ubuntu_2404() -> int:
    for os_ in call("GET", "/os?per_page=500")["os"]:
        if os_["name"].startswith("Ubuntu 24.04") and os_["arch"] == "x64":
            return os_["id"]
    sys.exit("Ubuntu 24.04 x64 not found")


def ensure_ssh_key(name: str, pub_path: str) -> str:
    pub = open(os.path.expanduser(pub_path), encoding="utf-8").read().strip()
    for k in call("GET", "/ssh-keys?per_page=100")["ssh_keys"]:
        if k["name"] == name:
            return k["id"]
    return call("POST", "/ssh-keys", {"name": name, "ssh_key": pub})["ssh_key"]["id"]


def ensure_firewall(name: str) -> str:
    for g in call("GET", "/firewalls?per_page=100")["firewall_groups"]:
        if g["description"] == name:
            return g["id"]
    gid = call("POST", "/firewalls", {"description": name})["firewall_group"]["id"]
    for port in ("22", "80", "443"):
        for ip_type, subnet, size in (("v4", "0.0.0.0", 0), ("v6", "::", 0)):
            call("POST", f"/firewalls/{gid}/rules", {"ip_type": ip_type, "protocol": "tcp", "subnet": subnet,
                                                     "subnet_size": size, "port": port, "notes": f"repro {port}"})
    return gid


def find_instance(label: str) -> dict | None:
    for inst in call("GET", "/instances?per_page=100")["instances"]:
        if inst["label"] == label:
            return inst
    return None


def create(args) -> None:
    existing = find_instance(args.label)
    if existing:
        print(json.dumps({"exists": True, "id": existing["id"], "ip": existing["main_ip"], "status": existing["status"]}))
        return
    body = {
        "region": args.region,
        "plan": args.plan,
        "os_id": ubuntu_2404(),
        "label": args.label,
        "hostname": args.label,
        "sshkey_id": [ensure_ssh_key(args.label + "-key", args.ssh_pub)],
        "firewall_group_id": ensure_firewall(args.label + "-fw"),
        "enable_ipv6": True,
        "backups": "disabled",
        "tags": ["repro", "agent-rush"],
    }
    inst = call("POST", "/instances", body)["instance"]
    for _ in range(90):
        cur = call("GET", f"/instances/{inst['id']}")["instance"]
        if cur["status"] == "active" and cur["main_ip"] not in ("", "0.0.0.0") and cur["server_status"] == "ok":
            print(json.dumps({"id": cur["id"], "ip": cur["main_ip"], "v6": cur.get("v6_main_ip"), "plan": cur["plan"],
                              "region": cur["region"]}))
            return
        time.sleep(10)
    sys.exit("instance did not become ready in 15 minutes")


def status(args) -> None:
    inst = find_instance(args.label)
    print(json.dumps(inst and {k: inst[k] for k in ("id", "main_ip", "status", "server_status", "plan", "region")}))


def destroy(args) -> None:
    inst = find_instance(args.label)
    if not inst:
        print("no instance")
        return
    call("DELETE", f"/instances/{inst['id']}")
    print("deleted", inst["id"])


def account(args) -> None:
    acct = call("GET", "/account")["account"]
    print(json.dumps({k: acct.get(k) for k in ("balance", "pending_charges", "last_payment_date")}))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["create", "status", "destroy", "account"])
    p.add_argument("--label", default="repro")
    p.add_argument("--region", default="fra")
    p.add_argument("--plan", default="vhp-4c-8gb-amd")
    p.add_argument("--ssh-pub", default="~/.ssh/id_ed25519_personal.pub")
    args = p.parse_args()
    {"create": create, "status": status, "destroy": destroy, "account": account}[args.action](args)


if __name__ == "__main__":
    main()
