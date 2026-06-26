import { useMemo, useState } from 'react';
import type { AdrRequest } from '../types';

interface Props {
  onSubmit: (req: AdrRequest) => Promise<void>;
  loading: boolean;
  error: string | null;
}

const STATUS_OPTIONS: Array<AdrRequest['status']> = [
  'proposed',
  'accepted',
  'rejected',
  'deprecated',
  'superseded',
];

const splitList = (raw: string): string[] =>
  raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

const joinList = (list: string[]): string => list.join(', ');

export default function AdrForm({ onSubmit, loading, error }: Props) {
  const [title, setTitle] = useState('');
  const [context, setContext] = useState('');
  const [technologiesRaw, setTechnologiesRaw] = useState('');
  const [preliminary, setPreliminary] = useState('');
  const [optionsRaw, setOptionsRaw] = useState('');
  const [status, setStatus] =
    useState<AdrRequest['status']>('proposed');

  const technologies = useMemo(
    () => splitList(technologiesRaw),
    [technologiesRaw],
  );

  const titleError =
    title.length > 0 && title.length < 5
      ? 'Mínimo 5 caracteres.'
      : null;
  const contextError =
    context.length > 0 && context.length < 20
      ? 'Mínimo 20 caracteres.'
      : null;
  const techsError =
    technologiesRaw.length > 0 && technologies.length === 0
      ? 'Introduce al menos una tecnología.'
      : null;
  const prelimError =
    preliminary.length > 0 && preliminary.length < 5
      ? 'Mínimo 5 caracteres.'
      : null;

  const isValid =
    title.length >= 5 &&
    context.length >= 20 &&
    technologies.length >= 1 &&
    preliminary.length >= 5;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid || loading) return;
    const req: AdrRequest = {
      title: title.trim(),
      context: context.trim(),
      technologies,
      preliminary_decision: preliminary.trim(),
      options_to_evaluate: splitList(optionsRaw),
      status,
    };
    await onSubmit(req);
  }

  function handleReset() {
    setTitle('');
    setContext('');
    setTechnologiesRaw('');
    setPreliminary('');
    setOptionsRaw('');
    setStatus('proposed');
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {error ? <div className="error">{error}</div> : null}

      <div className="field">
        <label htmlFor="title">Título del ADR</label>
        <input
          id="title"
          type="text"
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Ej: Adoptar PostgreSQL como base principal"
          required
        />
        <div className={`hint ${titleError ? 'error' : ''}`}>
          {titleError ?? `${title.length}/200 caracteres (mín. 5)`}
        </div>
      </div>

      <div className="field">
        <label htmlFor="context">Contexto y problema</label>
        <textarea
          id="context"
          value={context}
          rows={5}
          onChange={(e) => setContext(e.target.value)}
          placeholder="Describe el problema, restricciones y fuerzas en juego."
          required
        />
        <div className={`hint ${contextError ? 'error' : ''}`}>
          {contextError ?? `${context.length} caracteres (mín. 20)`}
        </div>
      </div>

      <div className="field">
        <label htmlFor="techs">Tecnologías involucradas</label>
        <input
          id="techs"
          type="text"
          value={technologiesRaw}
          onChange={(e) => setTechnologiesRaw(e.target.value)}
          placeholder="PostgreSQL, Redis, Kafka"
          required
        />
        <div className={`hint ${techsError ? 'error' : ''}`}>
          {techsError ?? 'Separadas por coma. Al menos una.'}
        </div>
        {technologies.length > 0 && (
          <div className="hint" style={{ marginTop: 4 }}>
            Detectadas:{' '}
            {technologies.map((t) => (
              <span
                key={t}
                style={{
                  display: 'inline-block',
                  background: '#0c0e13',
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  padding: '2px 6px',
                  marginRight: 4,
                }}
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="field">
        <label htmlFor="preliminary">Decisión preliminar</label>
        <textarea
          id="preliminary"
          value={preliminary}
          rows={2}
          onChange={(e) => setPreliminary(e.target.value)}
          placeholder="PostgreSQL gestionado en RDS"
          required
        />
        <div className={`hint ${prelimError ? 'error' : ''}`}>
          {prelimError ?? 'Mínimo 5 caracteres.'}
        </div>
      </div>

      <div className="field">
        <label htmlFor="options">Opciones adicionales a evaluar (opcional)</label>
        <input
          id="options"
          type="text"
          value={optionsRaw}
          onChange={(e) => setOptionsRaw(e.target.value)}
          placeholder="MySQL 8, CockroachDB, Aurora"
        />
        <div className="hint">
          Lista separada por comas. Si la dejas vacía, sólo se evalúa la
          decisión preliminar.
        </div>
      </div>

      <div className="field">
        <label htmlFor="status">Estado</label>
        <select
          id="status"
          value={status}
          onChange={(e) =>
            setStatus(e.target.value as AdrRequest['status'])
          }
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div className="toolbar">
        <button
          type="submit"
          className="button"
          disabled={!isValid || loading}
        >
          {loading ? 'Generando…' : 'Generar ADR'}
        </button>
        <button
          type="button"
          className="button secondary"
          onClick={handleReset}
          disabled={loading}
        >
          Limpiar
        </button>
        <span style={{ alignSelf: 'center', color: 'var(--muted)' }}>
          {technologies.length > 0 ? joinList(technologies) : ''}
        </span>
      </div>
    </form>
  );
}