-- Statements are separated explicitly because the trigger body contains semicolons.
CREATE TABLE IF NOT EXISTS schedule_revision (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    revision BIGINT NOT NULL DEFAULT 0
);
-- next-statement
INSERT INTO schedule_revision (singleton, revision) VALUES (TRUE, 0)
ON CONFLICT (singleton) DO NOTHING;
-- next-statement
CREATE OR REPLACE FUNCTION bump_schedule_revision() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE schedule_revision SET revision = revision + 1 WHERE singleton;
    RETURN NULL;
END;
$$;
-- next-statement
DROP TRIGGER IF EXISTS schedule_revision_changed ON schedule_stops;
-- next-statement
CREATE TRIGGER schedule_revision_changed
AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON schedule_stops
FOR EACH STATEMENT EXECUTE FUNCTION bump_schedule_revision();
