// A row of mutually exclusive filter buttons. value=null shows none selected.
interface Props<T extends string> {
  value: T | null;
  onChange: (value: T) => void;
  options: readonly (readonly [T, string])[];
  className?: string;
}

export default function Segmented<T extends string>({ value, onChange, options, className }: Props<T>) {
  return (
    <div className={`filter-group${className ? ` ${className}` : ''}`} role="group">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          className={`filter-btn${value === v ? ' active' : ''}`}
          aria-pressed={value === v}
          onClick={() => onChange(v)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
