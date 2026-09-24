CREATE TABLE IF NOT EXISTS ports (
    id SERIAL PRIMARY KEY,
    name TEXT,
    geom geography(Point, 4326)
);

CREATE INDEX IF NOT EXISTS ports_geom_idx ON ports USING GIST (geom);
