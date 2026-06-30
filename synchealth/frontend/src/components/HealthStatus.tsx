import { useEffect, useState } from 'react';

import { api } from '../api';
import type { HealthResponse } from '../types';

type BannerState = 'loading' | 'ok' | 'degraded' | 'error';

export function HealthStatus() {
  const [state, setState] = useState<BannerState>('loading');
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const data = await api.health();
        if (cancelled) {
          return;
        }
        setHealth(data);
        setState(data.status === 'ok' && data.db ? 'ok' : 'degraded');
      } catch {
        if (!cancelled) {
          setState('error');
        }
      }
    };
    tick();
    const id = window.setInterval(tick, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const label =
    state === 'loading'
      ? 'Comprobando backend...'
      : state === 'ok'
        ? `Backend OK — v${health?.version ?? '?'}`
        : state === 'degraded'
          ? 'Backend degradado (BD no accesible)'
          : 'Backend no responde';

  return <div className={`banner banner-${state}`}>{label}</div>;
}