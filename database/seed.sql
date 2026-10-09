-- Reference data. Runs on the first start of an empty volume and may run
-- again (CI does), so everything here must be idempotent.
--
-- shelly-chat has no reference data yet: the index is filled by the indexer
-- and conversations by the users. This file stays as the place for it.
SELECT 1;
