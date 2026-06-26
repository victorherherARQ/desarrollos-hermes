import { useEffect, useState } from 'react';
import AdrForm from './components/AdrForm';
import AdrPreview from './components/AdrPreview';
import { generateAdr, health } from './api';
import type { AdrRequest, AdrResponse, HealthResponse } from './types';

export default function App() {
  const [result, setResult] = useState<AdrResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [healthInfo, setHealthInfo] = useState<HealthResponse | null>(null);

  useEffect(() => {
    health()
      .then(setHealthInfo)
      .catch(() =>
        setHealthInfo({ status: 'unreachable', model: '?', github_enabled: false }),
      );
  }, []);

  async function handleSubmit(req: AdrRequest) {
    setLoading(true);
    setError(null);
    try {
      const r = await generateAdr(req);
      setResult(r);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } }; message?: string })
          ?.response?.data?.detail ??
        (err as { message?: string })?.message ??
        'Error generando el ADR.';
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>ADR Generator — MADR 4.0</h1>
        <div className="meta">
          {healthInfo ? (
            <>
              backend: <strong>{healthInfo.status}</strong> · model:{' '}
              <code>{healthInfo.model}</code>
              {healthInfo.github_enabled ? ' · GitHub PR: on' : ' · GitHub PR: off'}
            </>
          ) : (
            'conectando…'
          )}
        </div>
      </header>

      <main className="layout">
        <aside className="panel">
          <h2>Formulario</h2>
          <AdrForm onSubmit={handleSubmit} loading={loading} error={error} />
        </aside>

        <section className="panel">
          <h2>Resultado</h2>
          <AdrPreview result={result} />
        </section>
      </main>
    </div>
  );
}