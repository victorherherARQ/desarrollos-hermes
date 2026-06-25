-- Euromillones schema
CREATE TABLE IF NOT EXISTS sorteos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha           DATE NOT NULL UNIQUE,
    dia_semana      TEXT NOT NULL,
    n1              INTEGER NOT NULL,
    n2              INTEGER NOT NULL,
    n3              INTEGER NOT NULL,
    n4              INTEGER NOT NULL,
    n5              INTEGER NOT NULL,
    e1              INTEGER NOT NULL,
    e2              INTEGER NOT NULL,
    suma            INTEGER NOT NULL,
    fuente          TEXT NOT NULL DEFAULT 'github:daowa89',
    descargado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fecha ON sorteos(fecha);

-- Vista para frecuencias de numeros
CREATE VIEW IF NOT EXISTS v_freq_numeros AS
SELECT num, COUNT(*) AS frecuencia
FROM (
    SELECT n1 AS num FROM sorteos UNION ALL
    SELECT n2 FROM sorteos UNION ALL
    SELECT n3 FROM sorteos UNION ALL
    SELECT n4 FROM sorteos UNION ALL
    SELECT n5 FROM sorteos
)
GROUP BY num
ORDER BY num;

-- Vista para frecuencias de estrellas
CREATE VIEW IF NOT EXISTS v_freq_estrellas AS
SELECT num, COUNT(*) AS frecuencia
FROM (
    SELECT e1 AS num FROM sorteos UNION ALL
    SELECT e2 FROM sorteos
)
GROUP BY num
ORDER BY num;

-- Metadata para tracking
CREATE TABLE IF NOT EXISTS metadata (
    clave           TEXT PRIMARY KEY,
    valor           TEXT,
    actualizado_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
