# Locking down customer-container egress

**Required before customer models run on a shared host.**

## The exposure

ORION runs customer-supplied Docker images. On Docker's default bridge those
containers have **unrestricted outbound network access** — this is measured, not
theoretical: a container on the default bridge reaches the public internet today.

On a cloud host that also means:

| address | what it is |
| --- | --- |
| `169.254.169.254` | instance metadata — hands out the host's cloud credentials |
| `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | your private network: database, Redis, internal APIs |
| `127.0.0.1` on the host | anything bound to loopback |

A customer image does not need an exploit for any of this. It just opens a socket.

For contrast, the **subprocess sandbox** (the cloudpickle path) has had network
blocked since Phase 0.2 — an empty network namespace plus an in-process socket
block. The Docker path, which is the one the pickle gate recommends customers
use *instead*, never had an equivalent.

## Why not `--internal`

Docker's `--internal` network blocks egress, and also breaks `--publish`.
ORION reaches the model over a published port, so `--internal` makes the model
unreachable. Measured both ways before choosing:

| network | published port | egress |
| --- | --- | --- |
| `--internal` | unreachable | blocked |
| named bridge | **HTTP 200** | open until filtered |

So: a named bridge, with egress filtered at the host.

## Setup

**1. Create the bridge** with a subnet you can write rules against:

```bash
docker network create --subnet 172.31.250.0/24 orion-models
```

**2. Drop egress from that subnet** toward everything private. `DOCKER-USER` is
the chain Docker leaves for exactly this, and it is evaluated before Docker's
own rules:

```bash
SUBNET=172.31.250.0/24
for DEST in 169.254.0.0/16 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 127.0.0.0/8; do
    iptables -I DOCKER-USER -s "$SUBNET" -d "$DEST" -j DROP
done
```

Persist them (`iptables-save`, or your configuration manager). Rules added by
hand vanish on reboot, and the failure is silent.

**3. Point ORION at it and make the requirement binding:**

```bash
ORION_CONTAINER_NETWORK=orion-models
ORION_REQUIRE_RESTRICTED_NETWORK=true
```

With the second set, `ContainerModelRunner` refuses to start a customer image
while no network is configured. The code cannot install firewall rules; it can
decline to run customer code until someone has.

## Verify it

From a container on that network:

```bash
docker run --rm --network orion-models python:3.11-slim python -c "
import socket; socket.setdefaulttimeout(3)
for label, host in (('metadata','169.254.169.254'), ('private','10.0.0.1')):
    try:
        socket.create_connection((host, 80), timeout=3).close()
        print(f'{label}: REACHABLE  <-- rules are not working')
    except OSError:
        print(f'{label}: blocked')
"
```

Then confirm the model is still reachable, because rules that break the product
get removed rather than fixed:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<published-port>/health
```

`200` means both halves hold.

## Outbound internet

The rules above still allow the public internet. Customer models generally do
not need it, and denying it outright is stricter and easy:

```bash
iptables -A DOCKER-USER -s 172.31.250.0/24 -j DROP
```

Do this if no customer model legitimately calls an external service. If some do
— a hosted inference API, say — allowlist those destinations rather than opening
the default route.

## What this does not cover

Egress filtering is a network control, not a sandbox. It does not stop a
container escape. `ORION_CONTAINER_RUNTIME=runsc` plus
`ORION_REQUIRE_HARDENED_RUNTIME=true` is the control for that, and the two are
independent — set both.
