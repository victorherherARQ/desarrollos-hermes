import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import type { AdrResponse } from '../types';

interface Props {
  result: AdrResponse | null;
}

export default function AdrPreview({ result }: Props) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>(
    'idle',
  );

  if (!result) {
    return (
      <div className="empty">
        Genera un ADR desde el formulario para ver aquí el resultado
        renderizado.
      </div>
    );
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(result!.content);
      setCopyState('copied');
      setTimeout(() => setCopyState('idle'), 1500);
    } catch {
      setCopyState('error');
      setTimeout(() => setCopyState('idle'), 1500);
    }
  }

  function handleDownload() {
    const blob = new Blob([result!.content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = result!.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="preview-meta">
        <span>
          <strong>#{result.adr_number}</strong>
        </span>
        <span>
          archivo: <code>{result.filename}</code>
        </span>
        <span>
          rama: <code>{result.branch}</code>
        </span>
        {result.commit_sha && (
          <span>
            commit:{' '}
            <code title={result.commit_sha}>
              {result.commit_sha.slice(0, 8)}
            </code>
          </span>
        )}
        {result.pr_url && (
          <span>
            🔗{' '}
            <a
              href={result.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--accent)' }}
            >
              Ver PR en GitHub
            </a>
          </span>
        )}
      </div>

      <div className="toolbar">
        <button
          type="button"
          className="button secondary"
          onClick={handleCopy}
        >
          {copyState === 'copied'
            ? '¡Copiado!'
            : copyState === 'error'
              ? 'Error al copiar'
              : 'Copiar Markdown'}
        </button>
        <button
          type="button"
          className="button secondary"
          onClick={handleDownload}
        >
          Descargar .md
        </button>
      </div>

      <div className="markdown">
        <ReactMarkdown rehypePlugins={[rehypeSanitize]}>
          {result.content}
        </ReactMarkdown>
      </div>
    </div>
  );
}