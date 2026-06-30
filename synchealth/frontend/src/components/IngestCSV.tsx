import { useState } from 'react';

import { api } from '../api';
import type { IngestResponse } from '../types';

type Status = 'idle' | 'uploading' | 'success' | 'error';

export function IngestCSV() {
  const [status, setStatus] = useState<Status>('idle');
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) {
      return;
    }
    setStatus('uploading');
    setErrorMessage(null);
    try {
      const data = await api.ingestCsv(file);
      setResult(data);
      setStatus('success');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Error desconocido');
      setStatus('error');
    }
  };

  return (
    <div>
      <h3>Subir CSV de Zepp Life</h3>
      <input type="file" accept=".csv" onChange={handleFile} />
      {status === 'uploading' && <p>Subiendo y procesando...</p>}
      {status === 'success' && result && (
        <p>
          Insertadas: <strong>{result.inserted}</strong>, actualizadas:{' '}
          <strong>{result.updated}</strong>, omitidas:{' '}
          <strong>{result.skipped}</strong>
        </p>
      )}
      {status === 'error' && (
        <p className="error">Error al procesar CSV: {errorMessage}</p>
      )}
    </div>
  );
}