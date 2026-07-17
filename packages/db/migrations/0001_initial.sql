-- Trucho — schema inicial
-- PostgreSQL 16 + pgvector. Modelo normalizado: una campaña puede tener
-- N premios en N festivales sin duplicar el análisis.

create extension if not exists vector;
create extension if not exists pg_trgm;  -- fuzzy matching para dedupe

-- ---------------------------------------------------------------------------
-- Campañas: el corazón de la base. Cada registro debe ser útil por sí solo.
-- ---------------------------------------------------------------------------
create table campaigns (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique,
  title       text not null,           -- título en idioma original
  brand       text not null,
  year        int,
  country     text,                    -- ISO 3166-1 alpha-2 (CL, AR, ES...)
  industry    text,                    -- retail, fmcg, banking, ngo, telco...
  summary     text,                    -- 1-2 frases: qué es
  description text,                    -- análisis completo: qué se hizo y cómo
  insight     text,                    -- el insight humano/cultural detrás
  execution   text,                    -- mecánica: medio, formato, tech, activación
  results     text,                    -- resultados públicos reportados (nullable)
  language    text,                    -- idioma original de la campaña (es, pt, en...)
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  constraint campaigns_year_check check (year is null or year between 1950 and 2100)
);

-- Búsqueda BM25: tsvector generado sobre los campos de análisis.
-- Config 'spanish' porque el análisis se redacta en español.
alter table campaigns add column search_tsv tsvector
  generated always as (
    setweight(to_tsvector('spanish', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('spanish', coalesce(brand, '')), 'A') ||
    setweight(to_tsvector('spanish', coalesce(summary, '')), 'B') ||
    setweight(to_tsvector('spanish', coalesce(insight, '')), 'B') ||
    setweight(to_tsvector('spanish', coalesce(description, '')), 'C') ||
    setweight(to_tsvector('spanish', coalesce(execution, '')), 'C')
  ) stored;

create index campaigns_search_idx on campaigns using gin (search_tsv);
create index campaigns_brand_trgm_idx on campaigns using gin (brand gin_trgm_ops);
create index campaigns_title_trgm_idx on campaigns using gin (title gin_trgm_ops);
create index campaigns_year_idx on campaigns (year);
create index campaigns_country_idx on campaigns (country);
create index campaigns_industry_idx on campaigns (industry);

-- ---------------------------------------------------------------------------
-- Agencias
-- ---------------------------------------------------------------------------
create table agencies (
  id      uuid primary key default gen_random_uuid(),
  name    text not null unique,
  network text,                        -- Ogilvy, DDB, independiente...
  country text                         -- ISO 3166-1 alpha-2
);

create table campaign_agencies (
  campaign_id uuid not null references campaigns (id) on delete cascade,
  agency_id   uuid not null references agencies (id) on delete cascade,
  role        text not null default 'lead',  -- lead | media | prod | pr | other
  primary key (campaign_id, agency_id, role)
);

-- ---------------------------------------------------------------------------
-- Festivales y premios
-- ---------------------------------------------------------------------------
create table festivals (
  id     uuid primary key default gen_random_uuid(),
  slug   text not null unique,         -- cannes, el-ojo, fiap, el-sol, achap...
  name   text not null,
  region text                          -- global | iberoamerica | local
);

create table awards (
  id          uuid primary key default gen_random_uuid(),
  campaign_id uuid not null references campaigns (id) on delete cascade,
  festival_id uuid not null references festivals (id) on delete restrict,
  year        int not null,
  category    text,                    -- "Film — Alimentos y bebidas (FL1)"
  tier        text not null,

  constraint awards_tier_check check (
    tier in ('grand_prix', 'gold', 'silver', 'bronze', 'shortlist', 'winner')
  ),
  constraint awards_unique unique (campaign_id, festival_id, year, category, tier)
);

create index awards_festival_year_idx on awards (festival_id, year);
create index awards_campaign_idx on awards (campaign_id);

-- ---------------------------------------------------------------------------
-- Links externos (nunca guardamos assets, solo referencias)
-- ---------------------------------------------------------------------------
create table campaign_links (
  campaign_id uuid not null references campaigns (id) on delete cascade,
  kind        text not null,           -- case_film | coverage | festival_page
  url         text not null,
  primary key (campaign_id, kind, url)
);

-- ---------------------------------------------------------------------------
-- Tags temáticos
-- ---------------------------------------------------------------------------
create table tags (
  id   uuid primary key default gen_random_uuid(),
  name text not null unique            -- humor, ugc, real-time, data-driven...
);

create table campaign_tags (
  campaign_id uuid not null references campaigns (id) on delete cascade,
  tag_id      uuid not null references tags (id) on delete cascade,
  primary key (campaign_id, tag_id)
);

-- ---------------------------------------------------------------------------
-- Embeddings para búsqueda semántica (bge-m3, 1024 dims)
-- ---------------------------------------------------------------------------
create table campaign_embeddings (
  campaign_id uuid primary key references campaigns (id) on delete cascade,
  content     text not null,           -- texto embebido: summary + insight + execution
  embedding   vector(1024) not null,
  model       text not null default 'BAAI/bge-m3'
);

create index campaign_embeddings_hnsw_idx on campaign_embeddings
  using hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- Trazabilidad: de dónde salió cada dato
-- ---------------------------------------------------------------------------
create table sources (
  id          uuid primary key default gen_random_uuid(),
  campaign_id uuid not null references campaigns (id) on delete cascade,
  source_site text not null,           -- elojo, ltw, fiap...
  source_url  text not null,
  raw_text    text,                    -- texto crudo recolectado, insumo del enrichment
  scraped_at  timestamptz not null default now(),

  constraint sources_unique unique (campaign_id, source_site, source_url)
);

create index sources_campaign_idx on sources (campaign_id);

-- ---------------------------------------------------------------------------
-- updated_at automático
-- ---------------------------------------------------------------------------
create or replace function set_updated_at() returns trigger as $$
begin
  new.updated_at := now();
  return new;
end;
$$ language plpgsql;

create trigger campaigns_updated_at
  before update on campaigns
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Seed: festivales conocidos
-- ---------------------------------------------------------------------------
insert into festivals (slug, name, region) values
  ('cannes',   'Cannes Lions',                          'global'),
  ('el-ojo',   'El Ojo de Iberoamérica',                'iberoamerica'),
  ('fiap',     'FIAP — Festival Iberoamericano de la Publicidad', 'iberoamerica'),
  ('el-sol',   'El Sol — Festival Iberoamericano de la Comunicación Publicitaria', 'iberoamerica'),
  ('achap',    'ACHAP / CREA (Chile)',                  'local'),
  ('circulo-ar', 'Círculo de Creativos Argentinos',     'local'),
  ('dandad',   'D&AD',                                  'global'),
  ('one-show', 'The One Show',                          'global'),
  ('clio',     'Clio Awards',                           'global'),
  ('adce',     'ADC*E — Art Directors Club of Europe',  'global');
