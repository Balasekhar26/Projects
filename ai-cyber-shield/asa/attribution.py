from __future__ import annotations

import ipaddress
from dataclasses import dataclass


@dataclass(frozen=True)
class AttributionHint:
    remote_ip: str
    scope: str
    confidence: str
    message: str
    report_to: str

    def to_dict(self) -> dict[str, str]:
        return {
            "remote_ip": self.remote_ip,
            "scope": self.scope,
            "confidence": self.confidence,
            "message": self.message,
            "report_to": self.report_to,
        }


def build_attribution_hint(remote_ip: str) -> AttributionHint:
    try:
        address = ipaddress.ip_address(remote_ip)
    except ValueError:
        return AttributionHint(
            remote_ip=remote_ip,
            scope="invalid",
            confidence="low",
            message="Remote address is not a valid IP. Preserve logs and inspect DNS/application context.",
            report_to="application or DNS provider abuse contact",
        )

    if address.is_private or address.is_loopback or address.is_link_local:
        return AttributionHint(
            remote_ip=remote_ip,
            scope="local_or_private_network",
            confidence="medium",
            message="Address is local/private; inspect router, LAN devices, VPNs, and local services.",
            report_to="local network owner or device admin",
        )

    return AttributionHint(
        remote_ip=remote_ip,
        scope="public_internet",
        confidence="low",
        message=(
            "Public IP identifies infrastructure, not a person. Use logs, timestamps, ports, and provider "
            "abuse channels for reporting."
        ),
        report_to="ISP/cloud hosting abuse contact",
    )
