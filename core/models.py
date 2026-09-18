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

    @property
    def quality_score(self) -> int:
        """Weighted lead quality: emails weigh most, phones least.

        Used to sort richer leads to the top of the export so you work the
        best prospects first. Score ranges roughly 0-100.
        """
        score = 0
        score += min(len(self.emails), 5) * 12        # verified outreach channel
        score += min(len(self.whatsapp_numbers), 3) * 8  # direct WhatsApp
        score += min(len(self.instagram_handles), 3) * 5
        score += min(len(self.linkedin_urls), 3) * 4
        score += min(len(self.phones), 3) * 2
        if self.emails:
            score += 5   # bonus for having an email at all
        if self.whatsapp_numbers:
            score += 5
        return min(score, 100)

    @property
    def quality_label(self) -> str:
        if self.quality_score >= 60:
            return "high"
        if self.quality_score >= 30:
            return "medium"
        return "low"

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
            "quality_score": self.quality_score,
            "quality_label": self.quality_label,
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
            self.quality_label,
            self.quality_score,
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
    "quality_label",
    "quality_score",
    "scraped_at",
]