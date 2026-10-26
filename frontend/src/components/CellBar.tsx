// One stacked bar: live (green) / generated (amber) / missing (grey) variants.
interface Props {
  live: number;
  generated: number;
  missing: number;
}

export default function CellBar({ live, generated, missing }: Props) {
  const total = live + generated + missing;
  if (!total) return null;
  return (
    <div className="cell-bar" role="img" aria-label={`${live} live, ${generated} generated, ${missing} missing`}>
      {(
        [
          ['live', live],
          ['generated', generated],
          ['missing', missing],
        ] as const
      ).map(([kind, n]) =>
        n ? <span key={kind} className={`cell-bar-${kind}`} style={{ flexGrow: n }} /> : null,
      )}
    </div>
  );
}
