-- Premier jalon : definir les espaces de travail, sans importer les fixtures.
-- L'image PostgreSQL execute ce fichier uniquement a la creation du volume.
BEGIN;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS meta;
COMMENT ON SCHEMA raw IS 'Sources brutes et preuves des imports';
COMMENT ON SCHEMA staging IS 'Champs normalises et donnees controlees';
COMMENT ON SCHEMA core IS 'Documents et allocations au niveau metier';
COMMENT ON SCHEMA marts IS 'Resultats de rapprochement pour les utilisateurs';
COMMENT ON SCHEMA app IS 'Suivi humain persistant et historique des decisions';
COMMENT ON SCHEMA meta IS 'Execution des imports et couverture des sources';
COMMIT;
