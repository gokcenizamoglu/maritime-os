"use client";

export interface SearchableSelectOption {
  id: number;
  label: string;
}

interface SearchableSelectProps {
  id: string;
  name: string;
  value: string;
  searchValue: string;
  options: SearchableSelectOption[];
  placeholder: string;
  searchPlaceholder: string;
  emptyMessage: string;
  isLoading: boolean;
  error: string | null;
  invalid: boolean;
  onSearchChange: (value: string) => void;
  onChange: (value: string) => void;
}

export function SearchableSelect({
  id,
  name,
  value,
  searchValue,
  options,
  placeholder,
  searchPlaceholder,
  emptyMessage,
  isLoading,
  error,
  invalid,
  onSearchChange,
  onChange,
}: SearchableSelectProps) {
  return (
    <>
      <input
        type="search"
        value={searchValue}
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder={searchPlaceholder}
        aria-label={searchPlaceholder}
        className="mt-1 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
      />
      <select
        id={id}
        name={name}
        required
        value={value}
        aria-invalid={invalid}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
      {isLoading && <p className="mt-1 text-xs text-zinc-500">Searching...</p>}
      {!isLoading && error && <p className="mt-1 text-sm text-red-700" role="alert">{error}</p>}
      {!isLoading && !error && options.length === 0 && (
        <p className="mt-1 text-sm text-zinc-500">{emptyMessage}</p>
      )}
    </>
  );
}
