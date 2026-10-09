-- Demo data for local use and acc only; never part of the database image.
-- Skips itself when there are conversations already.
--
-- There is no demo index: embeddings depend on the model on the machine that
-- runs Ollama. Run the indexer (host/README.md) against the local or acc
-- stack to get documents to ask about.
DO $$
DECLARE
    demo_id uuid := '00000000-0000-4000-8000-000000000001';
BEGIN
    IF EXISTS (SELECT 1 FROM conversations) THEN
        RETURN;
    END IF;

    INSERT INTO conversations (id, title, created_at, updated_at)
    VALUES (demo_id, 'Voorbeeldgesprek', now() - interval '1 hour', now() - interval '1 hour');

    INSERT INTO messages (conversation_id, role, content, effective_query, created_at)
    VALUES (demo_id, 'user', 'Hoe werkt deze chat?', 'Hoe werkt deze chat?', now() - interval '1 hour');

    INSERT INTO messages (conversation_id, role, content, model, duration_ms, created_at)
    VALUES (
        demo_id,
        'assistant',
        E'De vraag wordt in je browser omgezet naar een embedding door **Ollama op je eigen computer**. '
        'De NAS zoekt daarmee de best passende stukken uit de geïndexeerde documenten, '
        'en Ollama schrijft daarna het antwoord.\n\n'
        'Dit gesprek is demodata en staat alleen lokaal en op acc.',
        'demo',
        1200,
        now() - interval '1 hour' + interval '2 seconds'
    );
END $$;
