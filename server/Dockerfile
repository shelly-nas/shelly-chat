FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /server

# Dependencies first, so a code change does not reinstall them.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# llama-index-core fetches NLTK data into its package directory on first
# import. Do that while building, so the NAS needs no internet at runtime.
RUN python -c "from llama_index.core.node_parser import HierarchicalNodeParser; HierarchicalNodeParser.from_defaults()"

COPY app ./app

# Migrations are read at runtime - they have to ship as files.
COPY migrations ./migrations

# Port 3000, same as the Node backend, so nginx, Traefik and compose stay identical.
EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
