"""Modelos Pydantic de Trucho.

IMPORTANTE: este archivo es el espejo Python de los schemas Zod en
`packages/schema/src/index.ts`. Cualquier cambio acá debe replicarse allá
(y viceversa).
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class AwardTier(StrEnum):
    """Nivel del premio, normalizado cross-festival."""

    GRAND_PRIX = "grand_prix"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"
    SHORTLIST = "shortlist"
    WINNER = "winner"


class LinkKind(StrEnum):
    """Tipo de link externo. Nunca guardamos assets, solo referencias."""

    CASE_FILM = "case_film"
    COVERAGE = "coverage"
    FESTIVAL_PAGE = "festival_page"


class AgencyRole(StrEnum):
    LEAD = "lead"
    MEDIA = "media"
    PROD = "prod"
    PR = "pr"
    OTHER = "other"


class Industry(StrEnum):
    """Industrias normalizadas (vocabulario controlado del enrichment)."""

    RETAIL = "retail"
    FMCG = "fmcg"
    FOOD_BEVERAGE = "food_beverage"
    BANKING_FINANCE = "banking_finance"
    INSURANCE = "insurance"
    TELCO = "telco"
    TECH = "tech"
    AUTOMOTIVE = "automotive"
    MEDIA_ENTERTAINMENT = "media_entertainment"
    TRAVEL_TOURISM = "travel_tourism"
    HEALTH_PHARMA = "health_pharma"
    NGO_PUBLIC_GOOD = "ngo_public_good"
    GOVERNMENT = "government"
    EDUCATION = "education"
    FASHION_BEAUTY = "fashion_beauty"
    SPORTS = "sports"
    UTILITIES = "utilities"
    OTHER = "other"


class Award(BaseModel):
    festival: str = Field(description="slug del festival: el-ojo, cannes, fiap...")
    year: int = Field(ge=1950, le=2100)
    category: str | None = None
    tier: AwardTier


class CampaignLink(BaseModel):
    kind: LinkKind
    url: str


class CampaignAgency(BaseModel):
    name: str = Field(min_length=1)
    role: AgencyRole = AgencyRole.LEAD
    country: str | None = Field(default=None, min_length=2, max_length=2)


class RawCampaign(BaseModel):
    """Campaña cruda tal como sale de un scraper, antes del enrichment.

    Solo hechos: sin análisis redactado.
    """

    title: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    year: int | None = None
    country: str | None = Field(default=None, description="ISO 3166-1 alpha-2")
    agencies: list[CampaignAgency] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)
    links: list[CampaignLink] = Field(default_factory=list)
    raw_text: str = Field(
        default="",
        description="todo el texto crudo recolectado, insumo del enrichment",
    )
    source_site: str = Field(min_length=1)
    source_url: str


class CampaignAnalysis(BaseModel):
    """Análisis generado por el LLM en el paso de enrichment.

    Redactado en palabras propias, en español.
    """

    summary: str = Field(min_length=1, description="1-2 frases: qué es la campaña")
    description: str = Field(
        min_length=1, description="análisis completo: qué se hizo y cómo funcionaba"
    )
    insight: str = Field(min_length=1, description="el insight humano/cultural detrás")
    execution: str = Field(
        min_length=1, description="mecánica: medio, formato, tecnología, activación"
    )
    results: str | None = Field(
        default=None, description="resultados públicos reportados; null si no hay"
    )
    industry: Industry
    tags: list[str] = Field(min_length=1, max_length=10)
    language: str = Field(
        min_length=2, max_length=5, description="idioma original de la campaña: es, pt, en..."
    )


class Campaign(BaseModel):
    """Campaña completa: hechos + análisis. Lo que expone el MCP server."""

    id: str
    slug: str
    title: str
    brand: str
    year: int | None = None
    country: str | None = None
    industry: Industry | None = None
    summary: str | None = None
    description: str | None = None
    insight: str | None = None
    execution: str | None = None
    results: str | None = None
    language: str | None = None
    agencies: list[CampaignAgency] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)
    links: list[CampaignLink] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
