import React from 'react';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: SelectOption[];
  error?: string;
  helperText?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className = '', id, label, options, error, helperText, disabled, required, ...props }, ref) => {
    const selectId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);
    const errorId = selectId ? `${selectId}-error` : undefined;

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={selectId} className="block text-sm font-semibold text-gray-900 mb-1">
            {label} {required && <span className="text-red-600" aria-hidden="true">*</span>}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          disabled={disabled}
          required={required}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          className={`block w-full rounded-md border text-gray-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-blue-600 sm:text-sm h-10 px-3 py-2 bg-white disabled:bg-gray-100 disabled:cursor-not-allowed ${
            error ? 'border-red-500 text-red-900' : 'border-gray-300'
          } ${className}`}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {error && (
          <p id={errorId} className="mt-1 text-sm text-red-600 font-medium" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }
);

Select.displayName = 'Select';
