-- Confianza por fuente: el dataset de Internet Archive (Cannes Film 1954-2000)
-- tiene un error de fechas conocido que se propaga en los ganadores de
-- 1999-2000, y el registro es incompleto por naturaleza. Los datos que llegan
-- de años/filas dudosas se marcan con confidence = 'low' para poder
-- priorizarlos en revisiones y para que el MCP server pueda advertirlo.

alter table sources add column confidence text not null default 'normal'
  check (confidence in ('normal', 'low'));
