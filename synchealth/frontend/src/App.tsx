import { useEffect, useState } from 'react';

import { api } from './api';
import { HealthStatus } from './components/HealthStatus';
import { IngestCSV } from './components/IngestCSV';
import { MetricsTable } from './components/MetricsTable';
import { WeightChart } from './components/WeightChart';
import type { WeightPoint } from './types';

const RANGES = [7, 30, 90, 365] as const;
type Range = (typeof RANGES)[number];

export function App() {
  const [range, setRange] = useState<Range>(30);
  const [weight, setWeight] = useState<WeightPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = async (days: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.metricsWeight(days);
      setWeight(res.points);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload(range);
  }, [range]);

  return (
    <main className="container">
      <header>
        <h1>synchealth</h1>
        <p className="subtitle">
          MVP 1.0 — cimientos: CSV Zepp, SQLite, métricas.
        </p>
      </header>

      <HealthStatus />

      <section className="card">
        <IngestCSV />
      </section>

      <section className="card">
        <div className="range-selector">
          <label htmlFor="range">Rango:</label>
          <select
            id="range"
            value={range}
            onChange={(e) => setRange(Number(e.target.value) as Range)}
          >
            {RANGES.map((r) => (
              <option key={r} value={r}>
                Últimos {r} días
              </option>
            ))}
          </select>
          <button onClick={() => void reload(range)} disabled={loading}>
            {loading ? 'Cargando...' : 'Recargar'}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        <WeightChart data={weight} periodDays={range} />
        <MetricsTable data={weight} title="Peso (kg)" />
      </section>
    </main>
  );
}