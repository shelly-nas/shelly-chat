# Production database image.
#
# The schema is baked in rather than bind-mounted: the deploy workflow copies
# only docker-compose.prod.yml to the host, so a host path like
# ./database/init.sql cannot resolve there - Docker would silently create an
# empty directory in its place and Postgres would start with no schema.
#
# Both files run on the first start of an empty data volume, in filename order.
# seed-demo.sql is deliberately left out: demo data is for local use only.
FROM postgres:16-alpine

# pgvector holds the document embeddings. Built from source so the image stays
# on postgres:16-alpine (postgres user uid/gid 70, which the data directory on
# the NAS is owned by). OPTFLAGS="" keeps the build portable instead of tuned
# to the build machine's CPU; with_llvm=no skips the JIT bitcode, which would
# need clang. Keep PGVECTOR_VERSION in step with the CI service image.
ARG PGVECTOR_VERSION=0.8.0
RUN apk add --no-cache --virtual .build-deps build-base \
    && wget -qO- "https://github.com/pgvector/pgvector/archive/refs/tags/v${PGVECTOR_VERSION}.tar.gz" | tar -xz -C /tmp \
    && cd "/tmp/pgvector-${PGVECTOR_VERSION}" \
    && make OPTFLAGS="" with_llvm=no \
    && make install with_llvm=no \
    && cd / && rm -rf "/tmp/pgvector-${PGVECTOR_VERSION}" \
    && apk del .build-deps

COPY init.sql /docker-entrypoint-initdb.d/01-init.sql
COPY seed.sql /docker-entrypoint-initdb.d/02-seed.sql
