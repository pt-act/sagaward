# Strix S0-v2 Containment Proof — Cloud Linux VM Runbook

> **Goal:** stand up a real-kernel Linux VM that can run the cross-container egress-gateway proof (the thing Docker Desktop's LinuxKit and Zo's gVisor could not).
> **Division of labor:** Steps 0–6 are **operator** (provision + validate + stage). Step 7 hands off to the **coder** for the proof itself.
> **The one hard requirement:** a *real* KVM Linux VM — not a gVisor/LinuxKit "sandbox" or "cloud computer" product.

---

## Before you start — what you need
- A provider account (Hetzner / DigitalOcean / Linode / AWS).
- An SSH keypair (`ssh-keygen -t ed25519` on your Mac if you don't have one).
- ~$5–15 of budget (hourly billing; a few days of testing is cheap if you destroy it after).
- Your LLM API key (the `naraya/minimax-m3` one you've been using).

---

## Step 0 · Pick and size the VM

**Spec (minimum → comfortable):**
- OS: **Ubuntu 22.04 or 24.04 LTS**
- vCPU: **4**
- RAM: **8 GB** (16 GB comfortable — the sandbox image build is heavy)
- Disk: **60 GB** (80 GB comfortable — the dev sandbox image alone is ~11 GB on disk)

**Concrete picks (verify current specs/price at signup):**
| Provider | Instance | Notes |
|---|---|---|
| **Hetzner** (cheapest) | `CPX31` (x86, 4/8/160) or `CAX31` (ARM, 8/16) | Best value. ARM reuses your Mac's arch. |
| **DigitalOcean** | 4 vCPU / 8 GB droplet | Simplest UI. |
| **Linode/Akamai** | 8 GB Dedicated/Shared | Fine. |
| **AWS EC2** | `t3.xlarge` (4/16) + Ubuntu AMI | More setup (security groups, key pairs). |

**Avoid** any "cloud computer" / agent-sandbox product — those are the gVisor/LinuxKit trap you already hit. You want plain Linux on KVM.

**Arch:** x86 is simplest (we rebuild images from source on the VM, so arch is a non-issue). ARM (Hetzner CAX / AWS Graviton) also works and matches your Mac.

At signup: choose the Ubuntu LTS image, attach your SSH key, create.

---

## Step 1 · Connect
```bash
ssh root@<VM_IP>          # or the provider's default user, then `sudo -i`
```
Key-based auth only (you added the key at signup). No further hardening needed for a short-lived test box.

---

## Step 2 · CONFIRM IT'S A REAL KERNEL (the gate — do this first)
```bash
systemd-detect-virt        # EXPECT: kvm  or  qemu
uname -a
```
- `kvm` / `qemu` → real VM, proceed.
- `gvisor` / `runsc` / `lxc` / `container` → **wrong product, stop.** Destroy it and pick a plain KVM VM.

---

## Step 3 · Install Docker (official)
```bash
apt update && apt -y upgrade
curl -fsSL https://get.docker.com | sh
docker run --rm hello-world
```
(Use `get.docker.com` — the distro's `docker.io` package is older.)

---

## Step 4 · THE DECISIVE PROBE — TPROXY + privileged Docker + custom network
This is the exact capability that failed on Docker Desktop and gVisor. **If this passes, the VM can host the proof.**
```bash
# TPROXY kernel module present?
modprobe xt_TPROXY nf_tproxy_ipv4 2>/dev/null; lsmod | grep -i tproxy || echo "(may be built-in)"

# Privileged container can install mangle TPROXY rule + policy route?
docker run --rm --privileged --cap-add NET_ADMIN alpine sh -c '
  apk add -q iptables iproute2 &&
  iptables -t mangle -A PREROUTING -p tcp -j TPROXY --on-port 48081 --tproxy-mark 0x1/0x1 &&
  ip rule add fwmark 0x1 lookup 100 &&
  echo TPROXY_OK'

# Custom internal network (cross-container topology)?
docker network create --internal testnet && echo NETWORK_OK && docker network rm testnet
```
**Expect `TPROXY_OK` and `NETWORK_OK`.** If `TPROXY_OK` doesn't print, the kernel lacks the module — stop and pick a different image/provider (rare on stock Ubuntu KVM). Do not proceed to the proof until this passes.

---

## Step 5 · Get strix + the Python toolchain
```bash
apt -y install git
git clone https://github.com/pt-act/strix.git
cd strix
git checkout sgl-s3.1        # the branch carrying the S0-v2 work (confirm with the coder)

# uv (bundled-runtime pattern strix uses)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env  # or restart the shell

# LLM provider config — set in the ENV, never in a tracked file
export STRIX_LLM="openai/minimax-m3"
export LLM_API_BASE="https://router.naraya.ai/v1"
export LLM_API_KEY="<your-key>"     # paste here in the shell only; do not commit
```

---

## Step 6 · Build the images on the VM (rebuild-on-target handles arch)
```bash
docker build -f containers/Dockerfile        -t strix-sandbox:dev .
docker build -f containers/Dockerfile.prod   --target prod -t strix-sandbox:prod .
docker build -f containers/Dockerfile.gateway -t strix-egress-gateway:latest .

# B-V2P fixtures (target for the proof's scan)
docker build -t strix-bv2p-idor benchmarks/bv2p/idor_memories
docker build -t strix-bv2p-ssrf benchmarks/bv2p/ssrf_fetch

docker image ls   # sanity-check they're all present
```
(The heavy one is the sandbox image — this is why ≥8 GB RAM / ≥60 GB disk matters. If a build OOMs, size up.)

---

## Step 7 · Hand off to the coder — run the containment proof
The environment is now ready. The coder runs the cross-container S0-v2 proof per **`pm-verdict-s0v2-partB-round3.md`**, with the **agent as ROOT**, and must show:
- empty-scope blocked via **TCP, DNS, raw-ICMP, IPv6, and the `127.0.0.1` adversarial case**;
- **in-scope reachable** (proxy relays to the B-V2P target);
- **C4 (the real test):** a root agent **cannot flush or reach the gateway's rules** (separate netns) and **cannot reach the Docker socket**;
- engine **completes the scan + reports the IDOR** under enforcement;
- full suite green + the **PRE-1** confirmation.

Then it comes back to me (PM) for line-by-line validation.

---

## Step 8 · Safety + cost (don't skip)
- **Scan only the local B-V2P fixtures on this VM.** Do **not** point strix at external/third-party targets from the cloud VM — that's the provider's AUP *and* the containment gate. The empty-scope test deliberately *attempts* egress; that's expected and stays inside the VM.
- **Stop the bleeding:** snapshot the VM if you want to pause, and **destroy it when done** to stop billing. (Provider console → Destroy/Terminate.)
- Keep the LLM key out of any committed file — env var only, as in Step 5.

---

### One-line summary of the gate
`systemd-detect-virt = kvm` **and** `TPROXY_OK` → green to build and prove. Anything else → wrong box.
