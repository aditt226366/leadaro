"""
Create the LiveKit side of the SIP bridge.

    python infra/setup_sip.py

Plivo and LiveKit each need their own trunk record. The Plivo side is
configured in their console; this creates the matching LiveKit objects and
writes their IDs (ST_xxx) back to .env, which is what the dialer and worker
actually use.

Idempotent: existing trunks with the same name are reused, not duplicated.
"""
import asyncio
import os
import pathlib
import sys

from dotenv import load_dotenv
from livekit import api

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DOMAIN = os.environ.get("PLIVO_TERMINATION_DOMAIN", "")
NUMBER = os.environ.get("PLIVO_NUMBER", "")
USER = os.environ.get("PLIVO_SIP_USERNAME", "")
PASSWORD = os.environ.get("PLIVO_SIP_PASSWORD", "")

# India requires both call legs to stay inside the country — media anchored
# abroad fails with "Domestic Anchored Terms Not Met" / violates_media_anchoring.
# The LiveKit project itself lives in Dubai, so without this the SIP leg
# originates from AE and Plivo rejects every domestic Indian call.
# Two-letter ISO code; empty means LiveKit picks a region on its own.
DEST_COUNTRY = os.environ.get("SIP_DESTINATION_COUNTRY", "").lower()

OUT_NAME = "plivo-outbound"
IN_NAME = "plivo-inbound"

# Must match services/agent/worker.py AGENT_NAME and dialer.py AGENT_NAME. The
# inbound dispatch rule routes calls to a worker registered under this exact
# name — a mismatch means inbound calls ring with nobody to answer.
AGENT_NAME = "leadaro-voice"


def write_env(updates: dict[str, str]) -> None:
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines()
    seen = set()
    out = []
    for line in lines:
        s = line.strip()
        if "=" in s and not s.startswith("#"):
            k = s.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


async def main() -> int:
    missing = [n for n, v in [
        ("PLIVO_TERMINATION_DOMAIN", DOMAIN), ("PLIVO_NUMBER", NUMBER),
        ("PLIVO_SIP_USERNAME", USER), ("PLIVO_SIP_PASSWORD", PASSWORD),
    ] if not v]
    if missing:
        print("missing in .env: " + ", ".join(missing))
        return 2

    lk = api.LiveKitAPI()
    try:
        # ── outbound ────────────────────────────────────────────────────────
        existing = await lk.sip.list_sip_outbound_trunk(
            api.ListSIPOutboundTrunkRequest())
        out_trunk = next((t for t in existing.items if t.name == OUT_NAME), None)

        if out_trunk:
            print(f"outbound trunk already exists: {out_trunk.sip_trunk_id}")
            # Re-pin an existing trunk rather than making the user delete it —
            # destination_country is the field that decides which country the
            # SIP leg originates from, and it is routinely wrong on trunks
            # created before the anchoring requirement was understood.
            if out_trunk.destination_country != DEST_COUNTRY:
                # The update call replaces the trunk wholesale, so every field
                # has to be restated. auth_password is redacted in list
                # responses — take it from .env, not from the fetched trunk.
                out_trunk = await lk.sip.update_outbound_trunk(
                    out_trunk.sip_trunk_id,
                    api.SIPOutboundTrunkInfo(
                        name=OUT_NAME,
                        address=DOMAIN,
                        numbers=[NUMBER],
                        auth_username=USER,
                        auth_password=PASSWORD,
                        transport=api.SIPTransport.SIP_TRANSPORT_UDP,
                        destination_country=DEST_COUNTRY,
                    ),
                )
                print(f"   re-pinned destination_country: "
                      f"{out_trunk.destination_country or '(none)'}")
        else:
            out_trunk = await lk.sip.create_sip_outbound_trunk(
                api.CreateSIPOutboundTrunkRequest(
                    trunk=api.SIPOutboundTrunkInfo(
                        name=OUT_NAME,
                        address=DOMAIN,
                        numbers=[NUMBER],
                        auth_username=USER,
                        auth_password=PASSWORD,
                        transport=api.SIPTransport.SIP_TRANSPORT_UDP,
                        destination_country=DEST_COUNTRY,
                    )
                )
            )
            print(f"created outbound trunk: {out_trunk.sip_trunk_id}")
        print(f"   address : {DOMAIN}")
        print(f"   caller  : {NUMBER}")
        print(f"   origin  : {out_trunk.destination_country or 'unpinned'}")

        # ── inbound ─────────────────────────────────────────────────────────
        existing_in = await lk.sip.list_sip_inbound_trunk(
            api.ListSIPInboundTrunkRequest())
        in_trunk = next((t for t in existing_in.items if t.name == IN_NAME), None)

        if in_trunk:
            print(f"inbound trunk already exists: {in_trunk.sip_trunk_id}")
        else:
            in_trunk = await lk.sip.create_sip_inbound_trunk(
                api.CreateSIPInboundTrunkRequest(
                    trunk=api.SIPInboundTrunkInfo(
                        name=IN_NAME,
                        numbers=[NUMBER],
                        # Plivo authenticates by source IP on inbound, so no
                        # credentials here. Restrict by number instead.
                        krisp_enabled=True,
                    )
                )
            )
            print(f"created inbound trunk: {in_trunk.sip_trunk_id}")

        # ── dispatch rule ───────────────────────────────────────────────────
        # Every inbound call gets its own room, named call-<uuid> by the rule's
        # prefix. The worker is dispatched into it by agent name.
        rules = await lk.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
        rule = next((r for r in rules.items
                     if in_trunk.sip_trunk_id in list(r.trunk_ids)), None)
        if rule:
            print(f"dispatch rule already exists: {rule.sip_dispatch_rule_id}")
        else:
            rule = await lk.sip.create_sip_dispatch_rule(
                api.CreateSIPDispatchRuleRequest(
                    trunk_ids=[in_trunk.sip_trunk_id],
                    rule=api.SIPDispatchRule(
                        dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                            room_prefix="inbound",
                        )
                    ),
                    room_config=api.RoomConfiguration(
                        agents=[api.RoomAgentDispatch(
                            agent_name=AGENT_NAME,
                            metadata=f'{{"to_number":"{NUMBER}"}}',
                        )]
                    ),
                )
            )
            print(f"created dispatch rule: {rule.sip_dispatch_rule_id}")

        write_env({
            "SIP_OUTBOUND_TRUNK_ID": out_trunk.sip_trunk_id,
            "SIP_INBOUND_TRUNK_ID": in_trunk.sip_trunk_id,
        })
        print("\n.env updated with the LiveKit trunk IDs.")
        return 0

    except Exception as e:
        print(f"failed: {type(e).__name__}: {str(e)[:400]}")
        return 1
    finally:
        await lk.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
