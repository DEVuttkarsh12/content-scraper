"""Lead data model and helpers."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ContactInfo:
    emails: list = field(default_factory=list)
    whatsapp_numbers: list = field(default_factory=list)
    instagram_handles: list = field(default_factory=list)
    linkedin_urls: list = field(default_factory=list)
    phones: list = field(default_factory=list)

    @property
    def has_anything(self) -> bool:
        return bool(
            self.emails
            or self.whatsapp_numbers
            or self.instagram_handles
            or self.linkedin_urls
            or self.phones
        )


@dataclass
class Lead:
    """A single collected lead."""

    business_name: str
    niche: str
    website: Optional[str] = None
    emails: list = field(default_factory=list)
    whatsapp_numbers: list = field(default_factory=list)
    instagram_handles: list = field(default_factory=list)
    linkedin_urls: list = field(default_factory=list)
    phones: list = field(default_factory=list)
    source_query: Optional[str] = None
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_contact(
        cls,
        business_name: str,
        niche: str,
        website: Optional[str],
        contact: ContactInfo,
        source_query: Optional[str] = None,
    ) -> "Lead":
        return cls(
            business_name=business_name,
            niche=niche,
            website=website,
            emails=contact.emails,
            whatsapp_numbers=contact.whatsapp_numbers,
            instagram_handles=contact.instagram_handles,
            linkedin_urls=contact.linkedin_urls,
            phones=contact.phones,
            source_query=source_query,
        )

    @property
    def has_contact(self) -> bool:
        info = ContactInfo(
            emails=self.emails,
            whatsapp_numbers=self.whatsapp_numbers,
            instagram_handles=self.instagram_handles,
            linkedin_urls=self.linkedin_urls,
            phones=self.phones,
        )
        return info.has_anything

    def to_dict(self) -> dict:
        return {
            "business_name": self.business_name,
            "niche": self.niche,
            "website": self.website or "",
            "emails": list(self.emails),
            "whatsapp_numbers": list(self.whatsapp_numbers),
            "instagram_handles": list(self.instagram_handles),
            "linkedin_urls": list(self.linkedin_urls),
            "phones": list(self.phones),
            "source_query": self.source_query or "",
            "scraped_at": self.scraped_at,
        }

    def flat_row(self) -> list:
        """Single-row flattening for CSV output."""
        return [
            self.business_name,
            self.niche,
            self.website or "",
            " | ".join(self.emails),
            " | ".join(self.whatsapp_numbers),
            " | ".join(self.instagram_handles),
            " | ".join(self.linkedin_urls),
            " | ".join(self.phones),
            self.source_query or "",
            self.scraped_at,
        ]


CSV_HEADERS = [
    "business_name",
    "niche",
    "website",
    "emails",
    "whatsapp_numbers",
    "instagram_handles",
    "linkedin_urls",
    "phones",
    "source_query",
    "scraped_at",
]