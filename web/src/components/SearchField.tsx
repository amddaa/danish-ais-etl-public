import { Search } from "lucide-react";

export function SearchField({
  id,
  label,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="search-field">
      <label htmlFor={id} className="visually-hidden">
        {label}
      </label>
      <Search size={14} aria-hidden="true" className="search-field__icon" />
      <input
        id={id}
        name={id}
        type="search"
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
