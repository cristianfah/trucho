/**
 * Schemas Zod de Trucho.
 *
 * IMPORTANTE: este archivo es el espejo TypeScript de los modelos Pydantic en
 * `apps/ingestion/trucho_ingest/models.py`. Cualquier cambio acá debe
 * replicarse allá (y viceversa).
 */
import { z } from "zod";

/** Nivel del premio, normalizado cross-festival. */
export const AwardTier = z.enum([
  "grand_prix",
  "gold",
  "silver",
  "bronze",
  "shortlist",
  "winner",
]);
export type AwardTier = z.infer<typeof AwardTier>;

/** Tipo de link externo. Nunca guardamos assets, solo referencias. */
export const LinkKind = z.enum(["case_film", "coverage", "festival_page"]);
export type LinkKind = z.infer<typeof LinkKind>;

/** Rol de una agencia en la campaña. */
export const AgencyRole = z.enum(["lead", "media", "prod", "pr", "other"]);
export type AgencyRole = z.infer<typeof AgencyRole>;

/** Industrias normalizadas (vocabulario controlado del enrichment). */
export const Industry = z.enum([
  "retail",
  "fmcg",
  "food_beverage",
  "banking_finance",
  "insurance",
  "telco",
  "tech",
  "automotive",
  "media_entertainment",
  "travel_tourism",
  "health_pharma",
  "ngo_public_good",
  "government",
  "education",
  "fashion_beauty",
  "sports",
  "utilities",
  "other",
]);
export type Industry = z.infer<typeof Industry>;

export const Award = z.object({
  festival: z.string().describe("slug del festival: el-ojo, cannes, fiap..."),
  year: z.number().int().min(1950).max(2100),
  category: z.string().nullable(),
  tier: AwardTier,
});
export type Award = z.infer<typeof Award>;

export const CampaignLink = z.object({
  kind: LinkKind,
  url: z.string().url(),
});
export type CampaignLink = z.infer<typeof CampaignLink>;

export const CampaignAgency = z.object({
  name: z.string().min(1),
  role: AgencyRole.default("lead"),
  country: z.string().length(2).nullable().optional(),
});
export type CampaignAgency = z.infer<typeof CampaignAgency>;

/**
 * Confianza en los datos de una fuente para este registro.
 * 'low' marca datos dudosos (ej: error de fechas conocido en el dataset de
 * Internet Archive para los ganadores 1999-2000).
 */
export const SourceConfidence = z.enum(["normal", "low"]);
export type SourceConfidence = z.infer<typeof SourceConfidence>;

/**
 * Campaña cruda tal como sale de un scraper, antes del enrichment.
 * Solo hechos: sin análisis redactado.
 */
export const RawCampaign = z.object({
  title: z.string().min(1),
  brand: z.string().min(1),
  year: z.number().int().nullable(),
  country: z.string().length(2).nullable().describe("ISO 3166-1 alpha-2"),
  agencies: z.array(CampaignAgency).default([]),
  awards: z.array(Award).default([]),
  links: z.array(CampaignLink).default([]),
  rawText: z
    .string()
    .default("")
    .describe("todo el texto crudo recolectado, insumo del enrichment"),
  sourceSite: z.string().min(1),
  sourceUrl: z.string().url(),
  confidence: SourceConfidence.default("normal"),
});
export type RawCampaign = z.infer<typeof RawCampaign>;

/**
 * Análisis generado por el LLM en el paso de enrichment.
 * Redactado en palabras propias, en español.
 */
export const CampaignAnalysis = z.object({
  summary: z.string().min(1).describe("1-2 frases: qué es la campaña"),
  description: z
    .string()
    .min(1)
    .describe("análisis completo: qué se hizo y cómo funcionaba"),
  insight: z.string().min(1).describe("el insight humano/cultural detrás"),
  execution: z
    .string()
    .min(1)
    .describe("mecánica: medio, formato, tecnología, activación"),
  results: z
    .string()
    .nullable()
    .describe("resultados públicos reportados; null si no hay"),
  industry: Industry,
  tags: z.array(z.string().min(1)).min(1).max(10),
  language: z
    .string()
    .min(2)
    .max(5)
    .describe("idioma original de la campaña: es, pt, en..."),
});
export type CampaignAnalysis = z.infer<typeof CampaignAnalysis>;

/** Campaña completa: hechos + análisis. Lo que expone el MCP server. */
export const Campaign = z.object({
  id: z.string().uuid(),
  slug: z.string().min(1),
  title: z.string().min(1),
  brand: z.string().min(1),
  year: z.number().int().nullable(),
  country: z.string().length(2).nullable(),
  industry: Industry.nullable(),
  summary: z.string().nullable(),
  description: z.string().nullable(),
  insight: z.string().nullable(),
  execution: z.string().nullable(),
  results: z.string().nullable(),
  language: z.string().nullable(),
  agencies: z.array(CampaignAgency).default([]),
  awards: z.array(Award).default([]),
  links: z.array(CampaignLink).default([]),
  tags: z.array(z.string()).default([]),
});
export type Campaign = z.infer<typeof Campaign>;
