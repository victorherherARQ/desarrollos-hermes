import type { WeightPoint } from '../types';

type Props = {
  data: WeightPoint[];
  title: string;
};

export function MetricsTable({ data, title }: Props) {
  if (data.length === 0) {
    return <p className="empty">Sin datos para {title}.</p>;
  }
  return (
    <div>
      <h3>{title}</h3>
      <table>
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Valor</th>
          </tr>
        </thead>
        <tbody>
          {data.map((p) => (
            <tr key={p.date}>
              <td>{p.date}</td>
              <td>{p.value.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}