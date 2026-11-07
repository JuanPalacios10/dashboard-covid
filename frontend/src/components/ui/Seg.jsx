export default function Seg({ value, onChange, options, label }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o[0]} aria-pressed={value === o[0]} onClick={() => onChange(o[0])}>
          {o[1]}
        </button>
      ))}
    </div>
  );
}
